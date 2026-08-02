# backend/app/presupuesto/router.py
"""POST /api/v1/meses/{mes}/sugerido (generar) + GET /api/v1/meses/{mes}/presupuesto.

MARCADO PARA AUDITORÍA KIMI (motor del sugerido).

RBAC §2.4: generar = `ciclo:abrir` (fila "Abrir mes / generar sugerido"); leer =
`dashboard:leer`. `crec_pct` viaja como string (Decimal exacto). `mes` en la ruta es
YYYY-MM (se normaliza al día 1)."""

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from pymongo.errors import DuplicateKeyError

from app.auth.deps import require_permission
from app.auth.models import User
from app.auth.router import verify_origin
from app.core.money import money_str
from app.domain.idempotency import IdempotencyKey, intentar_adquirir_huerfana
from app.domain.mes_control import MesControl
from app.domain.presupuesto import PresupuestoLinea
from app.presupuesto import service

router = APIRouter(prefix="/meses", tags=["presupuesto"])

_MES = re.compile(r"^\d{4}-\d{2}$")
_ENDPOINT_APROBAR = "POST /meses/{mes}/presupuesto/aprobar"


class GenerarSugeridoBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    crec_pct: str = "0"  # tasa como string (p. ej. "0.15"); Decimal exacto


class AcotarBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    monto_definido: str  # monto COP como string (regla 1)
    comentario: str | None = Field(default=None, max_length=300)


def _mes_key(mes: str) -> str:
    if not _MES.match(mes):
        raise HTTPException(422, "mes debe ser 'YYYY-MM'")
    return f"{mes}-01"


def _serializar(ln: PresupuestoLinea) -> dict:
    return {
        "id": str(ln.id),
        "rubro_id": str(ln.rubro_id),
        "version": ln.version,
        "monto_sugerido": money_str(ln.monto_sugerido),
        "prom_3m": money_str(ln.prom_3m),
        "tendencia_mes": money_str(ln.tendencia_mes),
        "crec_pct": str(ln.crec_pct),
        "compromisos_programados": money_str(ln.compromisos_programados),
        "monto_definido": (
            money_str(ln.monto_definido) if ln.monto_definido is not None else None
        ),
        "historia_incompleta": ln.historia_incompleta,
        "modo_calculo": ln.modo_calculo.value,
        "vigente": ln.vigente,
    }


@router.post("/{mes}/sugerido", status_code=201)
async def generar_sugerido(
    mes: str,
    body: GenerarSugeridoBody,
    user: User = Depends(require_permission("ciclo:abrir")),
    _: None = Depends(verify_origin),
):
    try:
        crec = Decimal(body.crec_pct)
        if not crec.is_finite():
            raise InvalidOperation
    except InvalidOperation:
        raise HTTPException(422, "crec_pct no es un decimal válido") from None
    if crec < 0:
        raise HTTPException(422, "crec_pct no puede ser negativo")
    try:
        lineas = await service.generar_sugerido(
            mes=_mes_key(mes), usuario_id=user.id, crec_pct=crec
        )
    except service.SugeridoError as e:
        raise HTTPException(e.status, e.detalle) from e
    return {"mes": mes, "lineas": [_serializar(x) for x in lineas]}


@router.get("/{mes}/presupuesto")
async def listar_presupuesto(
    mes: str,
    user: User = Depends(require_permission("dashboard:leer")),
):
    mc = await MesControl.find_one(MesControl.mes == _mes_key(mes))
    if mc is None:
        raise HTTPException(404, "mes no encontrado")
    lineas = await PresupuestoLinea.find(
        PresupuestoLinea.mes_id == mc.id,
        PresupuestoLinea.vigente == True,  # noqa: E712
    ).to_list()
    return {"mes": mes, "lineas": [_serializar(x) for x in lineas]}


def _parse_monto(s: str) -> Decimal:
    try:
        v = Decimal(s)
        if not v.is_finite():
            raise InvalidOperation
    except InvalidOperation:
        raise HTTPException(422, "monto_definido no es un decimal válido") from None
    if v < 0:
        raise HTTPException(422, "monto_definido no puede ser negativo")
    return v


@router.patch("/{mes}/presupuesto/{rubro_id}")
async def acotar_linea(
    mes: str,
    rubro_id: str,
    body: AcotarBody,
    user: User = Depends(require_permission("presupuesto:acotar")),
    _: None = Depends(verify_origin),
):
    monto = _parse_monto(body.monto_definido)
    try:
        ln = await service.acotar_linea(
            mes=_mes_key(mes),
            rubro_id=rubro_id,
            monto_definido=monto,
            comentario=body.comentario,
            usuario_id=user.id,
        )
    except service.AcotarError as e:
        raise HTTPException(e.status, e.detalle) from e
    return _serializar(ln)


@router.post("/{mes}/presupuesto/aprobar")
async def aprobar_presupuesto(
    mes: str,
    idempotency_key: str = Header(
        alias="Idempotency-Key", min_length=1, max_length=128
    ),
    user: User = Depends(require_permission("ciclo:aprobar")),
    _: None = Depends(verify_origin),
):
    # §1.12 replay seguro (aprobaciones): scope (usuario, endpoint, key). Reusado
    # además para CONVERGER si el proceso cae entre el commit y el emit de auditoría.
    req_hash = hashlib.sha256(
        json.dumps({"mes": mes}, sort_keys=True).encode()
    ).hexdigest()
    previa = await IdempotencyKey.find_one(
        IdempotencyKey.usuario_id == user.id,
        IdempotencyKey.endpoint == _ENDPOINT_APROBAR,
        IdempotencyKey.key == idempotency_key,
    )
    es_huerfana = False
    if previa is not None:
        if previa.request_hash != req_hash:
            raise HTTPException(422, "Idempotency-Key ya usada con un payload distinto")
        estado = previa.response_status
        if estado is not None and estado > 0:
            return JSONResponse(previa.response_body, status_code=estado)
        # A-4.2 (P1-10): marca en curso (None) o re-ejecutándose (-1). Si es huérfana
        # (>5 min) se adquiere y re-ejecuta convergente; si no, 409.
        if estado is None and await intentar_adquirir_huerfana(previa):
            marca = previa
            es_huerfana = True
        else:
            raise HTTPException(409, "petición con esta Idempotency-Key en curso")
    else:
        marca = IdempotencyKey(
            usuario_id=user.id,
            endpoint=_ENDPOINT_APROBAR,
            key=idempotency_key,
            request_hash=req_hash,
        )
        try:
            await marca.insert()
        except DuplicateKeyError:
            raise HTTPException(
                409, "petición con esta Idempotency-Key en curso"
            ) from None

    try:
        resultado = await service.aprobar_presupuesto(
            mes=_mes_key(mes), usuario_id=user.id
        )
    except service.AprobarError as e:
        # A-4.2: en re-ejecución de huérfana el error de negocio ES la respuesta
        # convergente (se persiste); en flujo normal, no quemar la key (se borra).
        if es_huerfana:
            marca.response_status = e.status
            marca.response_body = {"detail": e.detalle}
            await marca.save()
        else:
            await marca.delete()
        raise HTTPException(e.status, e.detalle) from e
    except Exception:
        # A-4.2 (cierre del residual): muerte durante la RE-EJECUCIÓN de una huérfana
        # (excepción NO de negocio) → devolver la marca a 'en curso' (None), no
        # dejarla clavada en el centinela -1 (la bloquearía las 24h del TTL). Su
        # created_at ya es viejo → el próximo retry la readquiere y converge. En flujo
        # normal (no huérfana) se borra como antes.
        if es_huerfana:
            marca.response_status = None
            await marca.save()
        else:
            await marca.delete()
        raise

    marca.response_status = 200
    marca.response_body = resultado
    await marca.save()
    return resultado
