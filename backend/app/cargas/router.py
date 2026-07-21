# backend/app/cargas/router.py
"""Endpoints de cargas (Spec §1.6, F-22, PRD M7).

MARCADO PARA AUDITORÍA KIMI (flujo crítico: cargas bancarias).

F-22: solo .xlsx/.xls; .xlsm (macros) rechazado SIEMPRE; límite 10 MB verificado
ANTES de procesar. El archivo se escribe a un temp y `procesar_carga` corre el
parseo en threadpool. La preservación del original (M-04) usa `ORIGINALES_DIR`
(interim local hasta S3); sin destino → 409 con mensaje accionable."""

import os
import tempfile

from anyio import to_thread
from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile

from app.auth.deps import require_permission
from app.auth.models import User
from app.auth.router import verify_origin
from app.cargas import service
from app.config import get_settings
from app.domain.bancos import Banco
from app.domain.carga import CargaBancaria
from app.parsers.bank_parsers import detectar_banco

router = APIRouter(prefix="/cargas", tags=["cargas"])

_MAX_BYTES = 10 * 1024 * 1024  # F-22
_EXT_OK = {".xlsx", ".xls"}


def _serializar(c: CargaBancaria, *, detalle: bool = False) -> dict:
    d = {
        "id": str(c.id),
        "banco": c.banco.value,
        "archivo_nombre": c.archivo_nombre,
        "estado": c.estado.value,
        "total_filas": c.total_filas,
        "nuevas": c.nuevas,
        "duplicadas": c.duplicadas,
        "errores": c.errores,
        "motivo_fallo": c.motivo_fallo,
        "created_at": c.created_at.isoformat(),
    }
    if detalle:
        d["errores_detalle"] = [e.model_dump() for e in c.errores_detalle]
    return d


@router.post("", status_code=201)
async def subir_extracto(
    archivo: UploadFile,
    user: User = Depends(require_permission("cargas:gestionar")),
    _: None = Depends(verify_origin),
):
    nombre = archivo.filename or "extracto"
    ext = os.path.splitext(nombre)[1].lower()
    if ext == ".xlsm":
        raise HTTPException(422, "archivos .xlsm (macros) no se aceptan (F-22)")
    if ext not in _EXT_OK:
        raise HTTPException(
            422, f"extensión '{ext}' no soportada; solo .xlsx/.xls (F-22)"
        )
    contenido = await archivo.read(_MAX_BYTES + 1)
    if len(contenido) > _MAX_BYTES:
        raise HTTPException(413, "el extracto supera el límite de 10 MB (F-22)")

    fd, tmp = tempfile.mkstemp(suffix=ext)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(contenido)
        try:
            banco: Banco = await to_thread.run_sync(detectar_banco, tmp)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e

        settings = get_settings()
        try:
            carga = await service.procesar_carga(
                banco=banco,
                archivo_path=tmp,
                archivo_nombre=nombre,
                usuario_id=PydanticObjectId(user.id),
                dir_originales=settings.originales_dir,
            )
        except service.CargaDuplicadaError as e:
            raise HTTPException(409, str(e)) from e
        except service.OriginalNoPreservableError as e:
            raise HTTPException(409, str(e)) from e
        except service.CargaError as e:
            raise HTTPException(422, str(e)) from e
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    return _serializar(carga, detalle=True)


@router.get("")
async def listar_cargas(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
    user: User = Depends(require_permission("cargas:gestionar")),
):
    q = CargaBancaria.find_all()
    if cursor:
        try:
            q = CargaBancaria.find(CargaBancaria.id < PydanticObjectId(cursor))
        except Exception:
            raise HTTPException(422, "cursor inválido") from None
    filas = await q.sort(-CargaBancaria.id).limit(limit + 1).to_list()
    next_cursor = str(filas[limit - 1].id) if len(filas) > limit else None
    return {
        "items": [_serializar(c) for c in filas[:limit]],
        "next_cursor": next_cursor,
    }


@router.get("/{carga_id}")
async def detalle_carga(
    carga_id: str,
    user: User = Depends(require_permission("cargas:gestionar")),
):
    try:
        carga = await CargaBancaria.get(PydanticObjectId(carga_id))
    except Exception:
        raise HTTPException(422, "id inválido") from None
    if carga is None:
        raise HTTPException(404, "carga no encontrada")
    return _serializar(carga, detalle=True)
