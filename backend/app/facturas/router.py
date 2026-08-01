# backend/app/facturas/router.py
"""/api/v1/facturas — carga de facturas (compra/venta) para IVA + liquidación
cuatrimestral (C11, CR "Fidelidad de caja").

RBAC: GET con `dashboard:leer`; mutaciones con `iva:gestionar` = {financiero, admin}
+ `verify_origin` (anti-CSRF). Montos como string (regla 1): el body los parsea a
Decimal antes de construir la factura; la respuesta los serializa con `money_str`. Sin
Idempotency-Key: no es un movimiento de dinero; el índice único (tercero_nit, numero)
hace inocuo el replay (→ 409). La liquidación se calcula en el backend."""

from datetime import date
from decimal import Decimal, InvalidOperation

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from app.auth.deps import require_permission
from app.auth.models import User
from app.auth.permissions import has_permission
from app.auth.router import verify_origin
from app.core.money import money_str
from app.core.time import today_bogota
from app.domain.factura import (
    TARIFAS_IVA_VALIDAS,
    Factura,
    OrigenFactura,
    TipoFactura,
)
from app.facturas import ingesta, service
from app.facturas.extraccion import PERSONA_JURIDICA
from app.iva.liquidacion import Periodicidad, clave_dian, liquidar, periodo_de

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
    # Pieza 2 (D-13): si viene `iva_valor`, MANDA y base/tarifa quedan opcionales
    # (misma precedencia que la ruta DIAN). Sin él, base+tarifa son obligatorias.
    base_gravable: str | None = None
    tarifa_iva: str | None = None
    iva_valor: str | None = None
    deducible: bool = False


class FacturaEditarBody(BaseModel):
    # CR-E2-EDITAR: SOLO los campos no fiscales. `extra=forbid` → un intento de tocar
    # un monto/fecha/tipo (factura inmutable en lo fiscal) responde 422.
    model_config = ConfigDict(strict=True, extra="forbid")

    deducible: bool | None = None
    origen: str | None = None


def _etiqueta_periodo(anio: int, idx: int, periodicidad: Periodicidad) -> str:
    # 'C' cuatrimestral (2026-C1) · 'B' bimestral (2026-B1)
    prefijo = "C" if periodicidad == Periodicidad.cuatrimestral else "B"
    return f"{anio}-{prefijo}{idx}"


def _proximo_pago(
    anio: int, idx: int, periodicidad: Periodicidad, calendario: dict
) -> dict | None:
    """Fecha DIAN del período (de `CALENDARIO_DIAN`) + días desde hoy (Bogotá). Sin
    fecha en el calendario → None: la UI omite la línea, no se inventa (R5, §3③)."""
    anio_cal = calendario.get(str(anio))
    fecha = anio_cal.get(clave_dian(idx, periodicidad)) if anio_cal else None
    if not fecha:
        return None
    y, m, d = (int(x) for x in fecha.split("-"))
    return {"fecha": fecha, "dias": (date(y, m, d) - today_bogota()).days}


def _serializar(
    f: Factura, periodicidad: Periodicidad, *, ver_pii: bool = True
) -> dict:
    anio, idx = periodo_de(f.fecha, periodicidad)
    # A17 (Ley 1581): la Ley protege a la PERSONA NATURAL. La razón social de una
    # persona jurídica (Auteco, Éxito, Hunter) NO es PII y debe verla el directivo.
    # Se enmascara SOLO si la contraparte es natural o su tipo es desconocido
    # (manual / PDF sin dato → por precaución) y el usuario no tiene ver_detalle.
    es_juridica = f.tipo_contribuyente == PERSONA_JURIDICA
    ver_contraparte = ver_pii or es_juridica
    return {
        "id": str(f.id),
        "tipo": f.tipo.value,
        "origen": f.origen.value,
        "numero": f.numero,
        "tercero_nombre": f.tercero_nombre if ver_contraparte else None,
        "tercero_nit": f.tercero_nit if ver_contraparte else None,
        "tipo_contribuyente": f.tipo_contribuyente,
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
        # 3 estados en la UI: decidido+True=Sí, decidido+False=No, no decidido=Sin
        # decidir. El §2 cuenta las compras activas con deducible_decidido=False.
        "deducible_decidido": f.deducible_decidido,
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
    calendario = await service.obtener_calendario_dian()
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
                "proximo_pago": _proximo_pago(
                    c.anio, c.periodo, periodicidad, calendario
                ),
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

    iva_valor = _dec(body.iva_valor, "iva_valor") if body.iva_valor else None
    base = _dec(body.base_gravable, "base_gravable") if body.base_gravable else None
    tarifa = _dec(body.tarifa_iva, "tarifa_iva") if body.tarifa_iva else None
    if iva_valor is None:
        # captura manual clásica: base + tarifa obligatorias (tarifa endurecida)
        if base is None or tarifa is None:
            raise HTTPException(
                422, "sin iva_valor, base_gravable y tarifa_iva son obligatorias"
            )
    if tarifa is not None and tarifa not in TARIFAS_IVA_VALIDAS:
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
            base_gravable=base,
            tarifa_iva=tarifa,
            iva_valor=iva_valor,
            deducible=body.deducible,
        )
    except service.FacturasError as e:
        raise HTTPException(e.status, e.detalle) from e
    return _serializar(factura, await service.obtener_periodicidad())


class IvaGeneradoBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    mes: str  # 'YYYY-MM' del mes vencido
    iva_valor: str  # monto COP como string (regla 1)


@router.post("/iva-generado", status_code=201)
async def registrar_iva_generado(
    body: IvaGeneradoBody,
    user: User = Depends(require_permission("iva:gestionar")),
    _: None = Depends(verify_origin),
):
    """Pieza 2 (decisión CEO): registra el IVA generado de un mes vencido (captura
    manual AGREGADA). Crea la venta `VENTAS-YYYY-MM` a nombre de RODDOS (NIT de
    Configuracion). El monto del IVA MANDA (D-13); no se inventa base. Dedup por
    (NIT, numero) → 409. Reusa `factura.creada` (sin evento nuevo)."""
    try:
        factura = await service.registrar_iva_generado(
            usuario_id=user.id,
            mes=body.mes,
            iva_valor=_dec(body.iva_valor, "iva_valor"),
        )
    except service.FacturasError as e:
        raise HTTPException(e.status, e.detalle) from e
    return _serializar(factura, await service.obtener_periodicidad())


class DeducibilidadLoteBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    ids: list[str] = Field(min_length=1, max_length=500)
    deducible: bool


@router.patch("/deducibilidad")
async def marcar_deducibilidad_lote(
    body: DeducibilidadLoteBody,
    user: User = Depends(require_permission("iva:gestionar")),
    _: None = Depends(verify_origin),
):
    """Marca la deducibilidad de un LOTE (spec de diseño §4). Resultado POR ID,
    tolerante a fallos parciales y fail-closed por factura. Va ANTES de PATCH
    /{factura_id} para que el literal no caiga en el path param."""
    resultados = await service.actualizar_deducibilidad_lote(
        ids=body.ids, deducible=body.deducible, usuario_id=user.id
    )
    resumen = {"actualizadas": 0, "sin_cambio": 0, "errores": 0}
    _clave = {
        "actualizada": "actualizadas",
        "sin_cambio": "sin_cambio",
        "error": "errores",
    }
    for r in resultados:
        resumen[_clave[r["estado"]]] += 1
    return {"resultados": resultados, "resumen": resumen}


@router.patch("/{factura_id}")
async def editar(
    factura_id: str,
    body: FacturaEditarBody,
    user: User = Depends(require_permission("iva:gestionar")),
    _: None = Depends(verify_origin),
):
    """CR-E2-EDITAR: edita SOLO deducible/origen (la factura es inmutable en lo
    fiscal). `origen` se valida contra el enum; `deducible` en venta → 422. Emite
    `factura.actualizada` con autor."""
    if body.origen is not None and body.origen not in OrigenFactura._value2member_map_:
        raise HTTPException(422, f"origen inválido: {body.origen}")
    try:
        factura, _ = await service.actualizar_factura(
            factura_id=factura_id,
            usuario_id=user.id,
            deducible=body.deducible,
            origen=body.origen,
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
