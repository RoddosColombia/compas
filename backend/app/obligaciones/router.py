# backend/app/obligaciones/router.py
"""/api/v1/obligaciones — obligaciones genéricas + facturas (D2 §2, CR-D2).

RBAC: GET con `dashboard:leer`; mutaciones con `proyeccion:gestionar` (las obligaciones
alimentan la proyección; mismo permiso que impactos/escenarios) + `verify_origin`.
Montos y tasas como string (regla 1); se parsean a Decimal en el borde."""

from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.auth.deps import require_permission
from app.auth.models import User
from app.auth.router import verify_origin
from app.core.money import money_str
from app.domain.obligacion import (
    FacturaObligacion,
    NaturalezaObligacion,
    Obligacion,
    OrigenPago,
)
from app.obligaciones import service

router = APIRouter(prefix="/obligaciones", tags=["obligaciones"])


def _dec(s: str, campo: str) -> Decimal:
    try:
        v = Decimal(s)
        if not v.is_finite():
            raise InvalidOperation
        return v
    except (InvalidOperation, ValueError) as e:
        raise HTTPException(422, f"{campo} no es un decimal válido: {s}") from e


class ObligacionCrearBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    nombre: str = Field(min_length=1, max_length=120)
    acreedor: str = Field(min_length=1, max_length=120)
    naturaleza: NaturalezaObligacion
    # cuotas
    monto_total: str | None = None
    n_cuotas: int | None = Field(default=None, ge=1)
    periodicidad_meses: int | None = Field(default=None, ge=1)
    tasa_mensual: str | None = None
    fecha_inicio: str | None = None
    meses_gracia: int | None = Field(default=None, ge=0)
    # facturacion
    plazo_base_dias: int | None = Field(default=None, ge=0)
    plazo_max_dias: int | None = Field(default=None, ge=0)
    tasa_excedente_mensual: str | None = None


class ObligacionEditarBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    nombre: str | None = Field(default=None, min_length=1, max_length=120)
    acreedor: str | None = Field(default=None, min_length=1, max_length=120)
    monto_total: str | None = None
    n_cuotas: int | None = Field(default=None, ge=1)
    periodicidad_meses: int | None = Field(default=None, ge=1)
    tasa_mensual: str | None = None
    fecha_inicio: str | None = None
    meses_gracia: int | None = Field(default=None, ge=0)
    plazo_base_dias: int | None = Field(default=None, ge=0)
    plazo_max_dias: int | None = Field(default=None, ge=0)
    tasa_excedente_mensual: str | None = None
    activo: bool | None = None


class FacturaCrearBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    numero: str | None = Field(default=None, max_length=60)
    fecha_factura: str
    valor: str
    plazo_elegido_dias: int = Field(ge=0)
    nota: str | None = Field(default=None, max_length=500)


class PagarBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    fecha: str
    valor: str
    pagada_desde: OrigenPago
    nota: str | None = Field(default=None, max_length=500)


_MONEY = {"monto_total", "tasa_mensual", "tasa_excedente_mensual"}


def _campos(body: BaseModel) -> dict:
    """Campos presentes (model_fields_set), con los money convertidos a Decimal."""
    out: dict = {}
    for campo in body.model_fields_set:
        if campo == "activo":
            continue
        valor = getattr(body, campo)
        if valor is None:
            continue
        out[campo] = _dec(valor, campo) if campo in _MONEY else valor
    return out


def _ser_obligacion(o: Obligacion, saldo: object = None) -> dict:
    d = {
        "id": str(o.id),
        "nombre": o.nombre,
        "acreedor": o.acreedor,
        "naturaleza": o.naturaleza,
        "activo": o.activo,
        "es_sistema": o.es_sistema,
        "actualizado_at": o.actualizado_at.isoformat(),
        "saldo_pendiente": money_str(saldo) if saldo is not None else None,
    }
    if o.naturaleza == "cuotas":
        d.update(
            monto_total=money_str(o.monto_total) if o.monto_total is not None else None,
            n_cuotas=o.n_cuotas,
            periodicidad_meses=o.periodicidad_meses,
            tasa_mensual=str(o.tasa_mensual) if o.tasa_mensual is not None else None,
            fecha_inicio=o.fecha_inicio,
            meses_gracia=o.meses_gracia,
        )
    else:
        d.update(
            plazo_base_dias=o.plazo_base_dias,
            plazo_max_dias=o.plazo_max_dias,
            tasa_excedente_mensual=(
                str(o.tasa_excedente_mensual)
                if o.tasa_excedente_mensual is not None
                else None
            ),
        )
    return d


def _ser_factura(f: FacturaObligacion) -> dict:
    return {
        "id": str(f.id),
        "obligacion_id": str(f.obligacion_id),
        "numero": f.numero,
        "fecha_factura": f.fecha_factura,
        "valor": money_str(f.valor),
        "plazo_elegido_dias": f.plazo_elegido_dias,
        "nota": f.nota,
        "activo": f.activo,
        "estado": "pendiente" if f.pagada_desde is None else "pagada",
        "pagada_desde": f.pagada_desde,
        "pagada_at": f.pagada_at,
        "pagada_valor": (
            money_str(f.pagada_valor) if f.pagada_valor is not None else None
        ),
        "pagada_nota": f.pagada_nota,
    }


@router.get("")
async def listar(
    activo: bool | None = Query(default=None),
    _: User = Depends(require_permission("dashboard:leer")),
):
    from decimal import Decimal

    obligaciones = await service.listar_obligaciones(activo=activo)
    saldos = await service.saldos_pendientes()
    # facturación: saldo = pendiente (0.00 si no hay); cuotas: no aplica (None).
    items = [
        _ser_obligacion(
            o,
            saldo=(
                saldos.get(str(o.id), Decimal("0"))
                if o.naturaleza == "facturacion"
                else None
            ),
        )
        for o in obligaciones
    ]
    return {"items": items}


@router.post("", status_code=201)
async def crear(
    body: ObligacionCrearBody,
    user: User = Depends(require_permission("proyeccion:gestionar")),
    _: None = Depends(verify_origin),
):
    try:
        o = await service.crear_obligacion(
            campos={
                "nombre": body.nombre,
                "acreedor": body.acreedor,
                "naturaleza": body.naturaleza,
                **_campos_naturaleza(body),
            },
            usuario_id=user.id,
        )
    except service.ObligacionesError as e:
        raise HTTPException(e.status, e.detalle) from e
    return _ser_obligacion(o)


def _campos_naturaleza(body: ObligacionCrearBody) -> dict:
    campos = _campos(body)
    for k in ("nombre", "acreedor", "naturaleza"):
        campos.pop(k, None)
    return campos


@router.patch("/{obligacion_id}")
async def editar(
    obligacion_id: str,
    body: ObligacionEditarBody,
    user: User = Depends(require_permission("proyeccion:gestionar")),
    _: None = Depends(verify_origin),
):
    try:
        o = await service.editar_obligacion(
            obligacion_id=obligacion_id,
            usuario_id=user.id,
            campos=_campos(body),
            activo=body.activo,
        )
    except service.ObligacionesError as e:
        raise HTTPException(e.status, e.detalle) from e
    return _ser_obligacion(o)


@router.delete("/{obligacion_id}", status_code=204)
async def eliminar(
    obligacion_id: str,
    user: User = Depends(require_permission("proyeccion:gestionar")),
    _: None = Depends(verify_origin),
):
    try:
        await service.eliminar_obligacion(
            obligacion_id=obligacion_id, usuario_id=user.id
        )
    except service.ObligacionesError as e:
        raise HTTPException(e.status, e.detalle) from e


@router.get("/{obligacion_id}/facturas")
async def listar_facturas(
    obligacion_id: str,
    _: User = Depends(require_permission("dashboard:leer")),
):
    try:
        facturas = await service.listar_facturas(obligacion_id=obligacion_id)
    except service.ObligacionesError as e:
        raise HTTPException(e.status, e.detalle) from e
    return {"items": [_ser_factura(f) for f in facturas]}


@router.post("/{obligacion_id}/facturas", status_code=201)
async def registrar_factura(
    obligacion_id: str,
    body: FacturaCrearBody,
    user: User = Depends(require_permission("proyeccion:gestionar")),
    _: None = Depends(verify_origin),
):
    try:
        f = await service.registrar_factura(
            obligacion_id=obligacion_id,
            numero=body.numero,
            fecha_factura=body.fecha_factura,
            valor=_dec(body.valor, "valor"),
            plazo_elegido_dias=body.plazo_elegido_dias,
            nota=body.nota,
            usuario_id=user.id,
        )
    except service.ObligacionesError as e:
        raise HTTPException(e.status, e.detalle) from e
    return _ser_factura(f)


@router.delete("/facturas/{factura_id}", status_code=204)
async def anular_factura(
    factura_id: str,
    user: User = Depends(require_permission("proyeccion:gestionar")),
    _: None = Depends(verify_origin),
):
    try:
        await service.anular_factura(factura_id=factura_id, usuario_id=user.id)
    except service.ObligacionesError as e:
        raise HTTPException(e.status, e.detalle) from e


@router.post("/{obligacion_id}/facturas/{factura_id}/pagar")
async def pagar_factura(
    obligacion_id: str,  # noqa: ARG001 (ruta anidada por claridad; la factura basta)
    factura_id: str,
    body: PagarBody,
    user: User = Depends(require_permission("proyeccion:gestionar")),
    _: None = Depends(verify_origin),
):
    try:
        f = await service.registrar_pago(
            factura_id=factura_id,
            fecha=body.fecha,
            valor=_dec(body.valor, "valor"),
            pagada_desde=body.pagada_desde,
            nota=body.nota,
            usuario_id=user.id,
        )
    except service.ObligacionesError as e:
        raise HTTPException(e.status, e.detalle) from e
    return _ser_factura(f)


class SimularNegociacionBody(BaseModel):
    """RF-F8 · Fundacional §2 — "Negocia esta deuda" (simulación compute-only).

    Al menos uno de los dos campos debe venir; sin ambos el servicio devuelve 422.
    No hay lista blanca de otros campos por diseño: la simulación solo mueve
    fecha/plazo (los términos que RODDOS negocia con el proveedor)."""

    model_config = ConfigDict(strict=True, extra="forbid")

    plazo_elegido_dias_nuevo: int | None = Field(default=None, ge=0)
    fecha_factura_nueva: str | None = None


@router.post("/{obligacion_id}/facturas/{factura_id}/simular")
async def simular_negociacion_factura(
    obligacion_id: str,  # noqa: ARG001 (ruta anidada por claridad; la factura basta)
    factura_id: str,
    body: SimularNegociacionBody,
    _: User = Depends(require_permission("dashboard:leer")),
):
    """RF-F8 — Simula "¿qué pasaría si negocio esta factura a X días / fecha Y?".

    Compute-only: NO escribe Mongo, NO emite audit. Devuelve piso actual vs.
    negociado, delta, mes de pago actual vs. negociado y valles antes/después.
    RBAC `dashboard:leer` — es lectura simulada, sin verify_origin (no muta)."""
    try:
        return await service.simular_negociacion_factura(
            factura_id=factura_id,
            plazo_elegido_dias_nuevo=body.plazo_elegido_dias_nuevo,
            fecha_factura_nueva=body.fecha_factura_nueva,
        )
    except service.ObligacionesError as e:
        raise HTTPException(e.status, e.detalle) from e


@router.delete("/{obligacion_id}/facturas/{factura_id}/pagar")
async def anular_pago(
    obligacion_id: str,  # noqa: ARG001
    factura_id: str,
    user: User = Depends(require_permission("proyeccion:gestionar")),
    _: None = Depends(verify_origin),
):
    try:
        f = await service.anular_pago(factura_id=factura_id, usuario_id=user.id)
    except service.ObligacionesError as e:
        raise HTTPException(e.status, e.detalle) from e
    return _ser_factura(f)
