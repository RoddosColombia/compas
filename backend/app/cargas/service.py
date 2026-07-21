# backend/app/cargas/service.py
"""Servicio de carga bancaria (Spec §1.6, PRD M7).

MARCADO PARA AUDITORÍA KIMI (flujo crítico: cargas bancarias).

Contrato seguido (§1.6, el data dictionary manda): inserción idempotente por lotes
`insertMany ordered=False`; los duplicados se cuentan por DuplicateKeyError contra el
índice único parcial (banco, id_banco). Esto NO es una transacción multi-documento
(la regla 8 la pide para 'finalización de carga', pero es incompatible con el
conteo-y-continúa del §1.6 → nota/CR pendiente, se resuelve en el gate Kimi).

F-02 (reproceso): se rechaza solo si ya hay una carga 'completada' con el mismo
archivo_hash; si la previa quedó 'fallida', la re-carga se permite y la dedup por
(banco, id_banco) evita duplicar lo ya insertado.
"""

import hashlib

from anyio import to_thread
from beanie import PydanticObjectId
from pymongo.errors import BulkWriteError

from app.audit.events import AuditEvento
from app.audit.service import emit_audit
from app.cargas.mapper import movimiento_a_transaccion
from app.domain.bancos import Banco
from app.domain.carga import CargaBancaria, ErrorCarga, EstadoCarga
from app.domain.mes_control import MesControl
from app.domain.rubro import Rubro
from app.domain.transaccion import Transaccion

RUBRO_POR_CLASIFICAR = "Por clasificar"


class CargaError(Exception):
    """Error de negocio del flujo de carga."""


class CargaDuplicadaError(CargaError):
    """El archivo ya fue cargado con éxito (misma huella, estado completada)."""


class RubroPorClasificarAusenteError(CargaError):
    """Falta el rubro de sistema 'Por clasificar' (no se corrieron las semillas)."""


def _mes_de(fecha_iso: str) -> str:
    """Mes-llave (YYYY-MM-01) derivado de la fecha 'YYYY-MM-DD'."""
    return fecha_iso[:7] + "-01"


def _hash_archivo(archivo_path: str) -> str:
    """SHA-256 del archivo. Bloqueante → se corre en threadpool (§1.6)."""
    with open(archivo_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


async def procesar_carga(
    *,
    banco: Banco,
    archivo_path: str,
    archivo_nombre: str,
    usuario_id: PydanticObjectId,
    archivo_s3_key: str | None = None,
) -> CargaBancaria:
    """Parsea un extracto y persiste sus movimientos como Transaccion 'Por
    clasificar', idempotentemente. Devuelve la CargaBancaria con los conteos."""
    if banco is Banco.MANUAL:
        raise CargaError("una carga proviene de un banco real, no 'manual'")

    archivo_hash = await to_thread.run_sync(_hash_archivo, archivo_path)

    # F-02: solo bloquea una carga PREVIA COMPLETADA con el mismo hash.
    previa = await CargaBancaria.find_one(
        CargaBancaria.archivo_hash == archivo_hash,
        CargaBancaria.estado == EstadoCarga.COMPLETADA,
    )
    if previa is not None:
        raise CargaDuplicadaError(
            f"el archivo ya fue cargado (hash {archivo_hash[:8]}…, carga {previa.id})"
        )

    rubro = await Rubro.find_one(Rubro.nombre == RUBRO_POR_CLASIFICAR)
    if rubro is None:
        raise RubroPorClasificarAusenteError(
            "falta el rubro de sistema 'Por clasificar' (correr semillas de rubros)"
        )

    carga = CargaBancaria(
        banco=banco,
        archivo_nombre=archivo_nombre,
        archivo_hash=archivo_hash,
        archivo_s3_key=archivo_s3_key,
        usuario_id=usuario_id,
    )
    await carga.insert()

    try:
        # Parseo en threadpool para no bloquear el event loop (§1.6).
        resultado = await to_thread.run_sync(parse_extracto_seguro, archivo_path, banco)
        errores = [ErrorCarga(fila=e.fila, motivo=e.motivo) for e in resultado.errores]

        docs: list[Transaccion] = []
        for mov in resultado.movimientos:
            mes = _mes_de(mov.fecha.isoformat())
            mc = await MesControl.find_one(MesControl.mes == mes)
            if mc is None:
                errores.append(
                    ErrorCarga(
                        fila=-1,
                        motivo=f"mes {mes[:7]} sin MesControl abierto; omitido",
                    )
                )
                continue
            docs.append(
                movimiento_a_transaccion(
                    mov, rubro_id=rubro.id, mes_id=mc.id, carga_id=carga.id
                )
            )

        nuevas = duplicadas = 0
        if docs:
            try:
                res = await Transaccion.insert_many(docs, ordered=False)
                nuevas = len(res.inserted_ids)
            except BulkWriteError as bwe:
                write_errors = bwe.details.get("writeErrors", [])
                otros = [e for e in write_errors if e.get("code") != 11000]
                if otros:
                    raise  # error real (no un duplicado) → carga fallida
                duplicadas = len(write_errors)
                nuevas = bwe.details.get("nInserted", len(docs) - duplicadas)

        carga.total_filas = len(resultado.movimientos) + len(resultado.errores)
        carga.nuevas = nuevas
        carga.duplicadas = duplicadas
        carga.errores = len(errores)
        carga.errores_detalle = errores
        carga.estado = EstadoCarga.COMPLETADA
        await carga.save()

        await emit_audit(
            AuditEvento.carga_completada,
            entidad="carga",
            entidad_id=str(carga.id),
            actor_id=str(usuario_id),
            metadata={
                "banco": banco.value,
                "nuevas": nuevas,
                "duplicadas": duplicadas,
                "errores": len(errores),
            },
        )
        return carga

    except CargaError:
        raise
    except Exception as exc:
        carga.estado = EstadoCarga.FALLIDA
        carga.motivo_fallo = str(exc)[:500]
        await carga.save()
        try:
            await emit_audit(
                AuditEvento.carga_fallida,
                entidad="carga",
                entidad_id=str(carga.id),
                actor_id=str(usuario_id),
                metadata={"motivo": carga.motivo_fallo},
            )
        except Exception:  # noqa: BLE001 — no enmascarar el error original de la carga
            pass
        raise


def parse_extracto_seguro(archivo_path: str, banco: Banco):
    """Wrapper síncrono para el threadpool (import perezoso del parser)."""
    from app.parsers.bank_parsers import parse_extracto

    return parse_extracto(archivo_path, banco)
