# backend/app/facturas/router.py
"""/api/v1/facturas — carga de facturas (compra/venta) para IVA + liquidación
cuatrimestral (C11, CR "Fidelidad de caja").

RBAC: GET con `dashboard:leer`; mutaciones con `iva:gestionar` = {financiero, admin}
+ `verify_origin` (anti-CSRF). Montos como string (regla 1): el body los parsea a
Decimal antes de construir la factura; la respuesta los serializa con `money_str`. Sin
Idempotency-Key: no es un movimiento de dinero; el índice único (tercero_nit, numero)
hace inocuo el replay (→ 409). La liquidación se calcula en el backend."""

from decimal import Decimal, InvalidOperation

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from app.auth.deps import require_permission
from app.auth.models import User
from app.auth.permissions import has_permission
from app.auth.router import verify_origin
from app.core.money import money_str
from app.domain.factura import (
    TARIFAS_IVA_VALIDAS,
    Factura,
    OrigenFactura,
    TipoFactura,
)
from app.facturas import ingesta, service
from app.iva.liquidacion import Periodicidad, liquidar, periodo_de

router = APIRouter(prefix="/facturas", tags=["facturas"])


def _dec(valor: str, campo: str) -> Decimal:
    try:
        return Decimal(valor)
    except (InvalidOperation, ValueError):
        raise HTTPException(422, f"{campo} debe ser un decimal en string") from None


class FacturaCrearBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    tipo: str  # validado contra TipoFactura en el handler (strict rechaza el enum)
    origen: str  # validado contra OrigenFactura en el handler
    numero: str = Field(min_length=1, max_length=60)
    tercero_nombre: str = Field(min_length=1, max_length=200)
    tercero_nit: str = Field(min_length=1, max_length=30)
    fecha: str
    base_gravable: str
    tarifa_iva: str
    deducible: bool = False


def _etiqueta_periodo(anio: int, idx: int, periodicidad: Periodicidad) -> str:
    # 'C' cuatrimestral (2026-C1) · 'B' bimestral (2026-B1)
    prefijo = "C" if periodicidad == Periodicidad.cuatrimestral else "B"
    return f"{anio}-{prefijo}{idx}"


def _serializar(
    f: Factura, periodicidad: Periodicidad, *, ver_pii: bool = True
) -> dict:
    anio, idx = periodo_de(f.fecha, periodicidad)
    return {
        "id": str(f.id),
        "tipo": f.tipo.value,
        "origen": f.origen.value,
        "numero": f.numero,
        # A17 (Ley 1581): la contraparte es PII (persona natural en emitidas). Se
        # oculta a quien no tiene facturas:ver_detalle; el resto queda visible.
        "tercero_nombre": f.tercero_nombre if ver_pii else None,
        "tercero_nit": f.tercero_nit if ver_pii else None,
        "fecha": f.fecha,
        # None (DIAN) → "—" en la UI, nunca un valor prestado (R5)
        "base_gravable": money_str(f.base_gravable)
        if f.base_gravable is not None
        else None,
        "total_bruto": money_str(f.total_bruto) if f.total_bruto is not None else None,
        # None = ingesta DIAN (tarifas mezcladas; manda iva_valor, D-13)
        "tarifa_iva": str(f.tarifa_iva) if f.tarifa_iva is not None else None,
        "iva_valor": money_str(f.iva_valor),
        "total": money_str(f.total),
        "deducible": f.deducible,
        "activo": f.activo,
        "periodo": _etiqueta_periodo(anio, idx, periodicidad),  # derivado de la fecha
    }


@router.get("")
async def listar(
    activo: bool | None = Query(default=None),
    user: User = Depends(require_permission("dashboard:leer")),
):
    periodicidad = await service.obtener_periodicidad()
    facturas = await service.listar_facturas(activo=activo)
    ver_pii = has_permission(user.rol, "facturas:ver_detalle")
    return [_serializar(f, periodicidad, ver_pii=ver_pii) for f in facturas]


@router.get("/liquidacion")
async def liquidacion(_: User = Depends(require_permission("dashboard:leer"))):
    """Liquidación por período (cuatrimestral o bimestral, según `PERIODICIDAD_IVA`) de
    las facturas activas: generado − descontable con arrastre de saldo a favor. Montos
    como string (regla 1)."""
    periodicidad = await service.obtener_periodicidad()
    items = await service.obtener_facturas_iva()
    return {
        "periodicidad": periodicidad.value,
        "periodos": [
            {
                "anio": c.anio,
                "periodo": c.periodo,
                "etiqueta": _etiqueta_periodo(c.anio, c.periodo, periodicidad),
                "generado": money_str(c.generado),
                "descontable": money_str(c.descontable),
                "saldo": money_str(c.saldo),
                "saldo_favor_previo": money_str(c.saldo_favor_previo),
                "neto_a_pagar": money_str(c.neto_a_pagar),
                "saldo_favor_nuevo": money_str(c.saldo_favor_nuevo),
            }
            for c in liquidar(items, periodicidad)
        ],
    }


@router.get("/{factura_id}")
async def detalle(
    factura_id: str,
    _: User = Depends(require_permission("facturas:ver_detalle")),
):
    """Detalle de una factura con PII completa (A17 / Ley 1581): solo
    facturas:ver_detalle = {financiero, admin}. La ruta va DESPUÉS de /liquidacion
    para que ese literal no caiga en {factura_id}."""
    try:
        fid = PydanticObjectId(factura_id)
    except Exception:
        raise HTTPException(422, "factura_id inválido") from None
    f = await Factura.get(fid)
    if f is None:
        raise HTTPException(404, "la factura no existe")
    return _serializar(f, await service.obtener_periodicidad(), ver_pii=True)


@router.post("/cargar")
async def cargar(
    archivos: list[UploadFile],
    user: User = Depends(require_permission("iva:gestionar")),
    _: None = Depends(verify_origin),
):
    """Ingesta por documento (E2 §3.3): lote de PDFs DIAN → resultado POR ARCHIVO
    (creada | duplicada | rechazada_no_dian | rechazada_tipo_no_soportado |
    requiere_confirmacion | error) + resumen. Parseo fuera del event loop (A16);
    tope de 20 archivos y 10 MB por archivo (coherente con POST /api/v1/cargas).
    RBAC iva:gestionar: cargar es una mutación fiscal, no una lectura."""
    if len(archivos) > ingesta.MAX_ARCHIVOS_LOTE:
        raise HTTPException(
            413,
            f"máximo {ingesta.MAX_ARCHIVOS_LOTE} archivos por lote; "
            f"recibidos {len(archivos)}",
        )
    try:
        return await ingesta.procesar_lote(archivos, usuario_id=user.id)
    except ingesta.ConfigFaltanteError as e:
        raise HTTPException(409, str(e)) from e


@router.post("", status_code=201)
async def crear(
    body: FacturaCrearBody,
    user: User = Depends(require_permission("iva:gestionar")),
    _: None = Depends(verify_origin),
):
    if body.tipo not in TipoFactura._value2member_map_:
        raise HTTPException(422, f"tipo inválido: {body.tipo}")
    if body.origen not in OrigenFactura._value2member_map_:
        raise HTTPException(422, f"origen inválido: {body.origen}")
    tarifa = _dec(body.tarifa_iva, "tarifa_iva")
    if tarifa not in TARIFAS_IVA_VALIDAS:
        raise HTTPException(
            422,
            f"tarifa_iva inválida: {body.tarifa_iva}. Tarifas IVA legales en "
            "Colombia: 0, 0.05, 0.19 (pieza 6)",
        )
    try:
        factura = await service.crear_factura(
            usuario_id=user.id,
            tipo=body.tipo,
            origen=body.origen,
            numero=body.numero,
            tercero_nombre=body.tercero_nombre,
            tercero_nit=body.tercero_nit,
            fecha=body.fecha,
            base_gravable=_dec(body.base_gravable, "base_gravable"),
            tarifa_iva=tarifa,
            deducible=body.deducible,
        )
    except service.FacturasError as e:
        raise HTTPException(e.status, e.detalle) from e
    return _serializar(factura, await service.obtener_periodicidad())


@router.post("/{factura_id}/anular")
async def anular(
    factura_id: str,
    user: User = Depends(require_permission("iva:gestionar")),
    _: None = Depends(verify_origin),
):
    try:
        factura = await service.anular_factura(
            factura_id=factura_id, usuario_id=user.id
        )
    except service.FacturasError as e:
        raise HTTPException(e.status, e.detalle) from e
    return _serializar(factura, await service.obtener_periodicidad())
