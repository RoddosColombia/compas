# backend/app/cargas/service.py
"""Servicio de carga bancaria (Spec §1.6, PRD M7).

MARCADO PARA AUDITORÍA KIMI (flujo crítico: cargas bancarias).

Contrato: inserción idempotente con dedup por índice único parcial (banco, id_banco)
+ **transacción multi-documento** en la finalización (regla 8).

Sobre §1.6 vs regla 8 (Kimi M-02, corregido): la nota original decía que eran
incompatibles; NO lo son, pero la vía literal de Kimi (`insertMany ordered=False` +
capturar `BulkWriteError` + commit DENTRO de la transacción) **no funciona**: se
verificó contra Mongo real que un dup-key (11000) marca la transacción como
`TransientTransactionError` y la aborta (nInserted=0). La forma correcta —y la que se
implementa— es **pre-filtrar** los duplicados con la sesión y luego insertar SOLO los
nuevos dentro de la transacción (sin dups → no aborta) junto al update de la carga.
El ordinal de ocurrencia (Kimi A-01) garantiza ids únicos por archivo, así que el
único duplicado posible es cross-archivo, que el pre-filtro detecta. `with_transaction`
reintenta ante errores transitorios (TOCTOU con una carga concurrente).

F-02 (reproceso): se rechaza solo si ya hay una carga 'completada' con el mismo hash.
M-04: el original debe quedar re-procesable (Spec §1.6); sin S3 (diferido) se conserva
una copia local (`dir_originales`); sin ningún destino se rechaza (regla dura).
"""

import hashlib
import shutil
from pathlib import Path

from anyio import to_thread
from beanie import PydanticObjectId
from beanie.operators import In

from app.audit.events import AuditEvento
from app.audit.service import emit_audit
from app.cargas.mapper import _TIPO_A_FLUJO, movimiento_a_transaccion
from app.domain.bancos import Banco
from app.domain.carga import CargaBancaria, ErrorCarga, EstadoCarga
from app.domain.mes_control import MesControl
from app.domain.rubro import Rubro
from app.domain.transaccion import Transaccion
from app.reglas.service import (
    elegir_regla,
    reglas_activas_por_tipo,
    rubros_activos_ids,
)

RUBRO_POR_CLASIFICAR = "Por clasificar"


class CargaError(Exception):
    """Error de negocio del flujo de carga."""


class CargaDuplicadaError(CargaError):
    """El archivo ya fue cargado con éxito (misma huella, estado completada)."""


class RubroPorClasificarAusenteError(CargaError):
    """Falta el rubro de sistema 'Por clasificar' (no se corrieron las semillas)."""


class OriginalNoPreservableError(CargaError):
    """No hay dónde preservar el original (ni S3 ni dir local) — regla dura M-04."""


def _mes_de(fecha_iso: str) -> str:
    return fecha_iso[:7] + "-01"


def _hash_archivo(archivo_path: str) -> str:
    with open(archivo_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _clave_ocurrencia(mov) -> tuple:
    """Identidad de la huella para contar ocurrencias dentro del archivo (A-01).

    - Global66 trae un `ID transaccion` nativo que identifica la OPERACIÓN lógica,
      no la línea de ledger: un pago PSE y su reversa comparten ese ID como dos
      movimientos opuestos (caso real del extracto mar–jul). La clave agrupa por
      `(banco, referencia)` → el ordinal les asigna 1 y 2 y sus id_banco quedan
      distintos (ambos son caja: salió y volvió), sin colapsar en el índice único.
    - Bancolombia/BBVA no traen ID → se discrimina por fecha/tipo/desc/monto."""
    if mov.referencia:
        return (mov.banco.value, mov.referencia)
    return (mov.fecha.isoformat(), mov.tipo.value, mov.descripcion, f"{mov.monto:.2f}")


def _parse(archivo_path: str, banco: Banco):
    from app.parsers.bank_parsers import parse_extracto

    return parse_extracto(archivo_path, banco)


def _finalizar_carga_doc(
    carga, resultado, errores, nuevas, duplicadas, nuevos_docs=()
) -> None:
    carga.total_filas = len(resultado.movimientos) + len(resultado.errores)
    carga.nuevas = nuevas
    carga.duplicadas = duplicadas
    carga.errores = len(errores)
    carga.errores_detalle = errores
    # C3 (D3): agregado de clasificación sobre las NUEVAS insertadas — el rastro
    # por documento es regla_id.
    carga.clasificadas = sum(1 for d in nuevos_docs if d.regla_id is not None)
    carga.por_clasificar = len(nuevos_docs) - carga.clasificadas
    carga.estado = EstadoCarga.COMPLETADA


async def procesar_carga(
    *,
    banco: Banco,
    archivo_path: str,
    archivo_nombre: str,
    usuario_id: PydanticObjectId,
    archivo_s3_key: str | None = None,
    s3_bucket: str | None = None,
    s3_client=None,
    dir_originales: str | None = None,
    permitir_sin_preservar: bool = False,
) -> CargaBancaria:
    """Parsea un extracto y persiste sus movimientos como Transaccion 'Por
    clasificar', idempotentemente. Devuelve la CargaBancaria con los conteos."""
    if banco is Banco.MANUAL:
        raise CargaError("una carga proviene de un banco real, no 'manual'")

    # M-04 (regla dura): el original debe quedar re-procesable.
    if (
        archivo_s3_key is None
        and s3_bucket is None
        and dir_originales is None
        and not permitir_sin_preservar
    ):
        raise OriginalNoPreservableError(
            "sin S3 ni dir_originales no se puede preservar el original (Spec §1.6, "
            "Kimi M-04). Configurar S3_BUCKET (prod), pasar dir_originales (dev), o "
            "permitir_sin_preservar=True (solo dev)."
        )

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

    # Preservar el original (M-04). S3 gana (prod, Object Lock COMPLIANCE);
    # dir_originales es solo puente de DEV. La subida corre ANTES de insertar nada
    # → un fallo de put_object aborta la carga sin persistir (fail-closed).
    if archivo_s3_key is None:
        ext = Path(archivo_nombre).suffix or ".bin"
        if s3_bucket is not None:
            from app.cargas import storage

            client = s3_client if s3_client is not None else storage.get_s3_client()
            key = storage.clave_original(archivo_hash, ext)
            archivo_s3_key = await to_thread.run_sync(
                lambda: storage.subir_original(
                    client=client,
                    bucket=s3_bucket,
                    key=key,
                    archivo_path=archivo_path,
                )
            )
        elif dir_originales is not None:
            destino = Path(dir_originales) / f"{archivo_hash}{ext}"
            await to_thread.run_sync(_preservar, archivo_path, destino)
            archivo_s3_key = f"local://{destino}"

    carga = CargaBancaria(
        banco=banco,
        archivo_nombre=archivo_nombre,
        archivo_hash=archivo_hash,
        archivo_s3_key=archivo_s3_key,
        usuario_id=usuario_id,
    )
    await carga.insert()

    try:
        resultado = await to_thread.run_sync(_parse, archivo_path, banco)
        errores = [
            ErrorCarga(fila=e.fila, motivo=e.motivo, valor_crudo=e.valor_crudo)
            for e in resultado.errores
        ]

        # C3 (GO Kimi 9.3): reglas activas particionadas por tipo (D1-ii) +
        # rubros activos, UNA vez por carga. D2: las reglas cuyo rubro esté
        # inactivo se saltan al clasificar y se reportan (fail-loud B-4).
        por_tipo = await reglas_activas_por_tipo()
        activos = await rubros_activos_ids()
        carga.reglas_con_rubro_inactivo = sorted(
            r.patron
            for reglas in por_tipo.values()
            for r in reglas
            if r.rubro_id not in activos
        )

        docs: list[Transaccion] = []
        mes_cache: dict[str, object] = {}  # M-03: 1 lookup por mes, no por fila
        conteo: dict[tuple, int] = {}  # A-01: ordinal de ocurrencia por huella
        for mov in resultado.movimientos:
            mes = _mes_de(mov.fecha.isoformat())
            if mes not in mes_cache:
                mes_cache[mes] = await MesControl.find_one(MesControl.mes == mes)
            mc = mes_cache[mes]
            if mc is None:
                errores.append(
                    ErrorCarga(
                        fila=-1,
                        motivo=f"mes {mes[:7]} sin MesControl abierto; omitido",
                    )
                )
                continue
            clave = _clave_ocurrencia(mov)
            conteo[clave] = conteo.get(clave, 0) + 1
            # C3: primera regla que matchea (prioridad asc, _id) clasifica;
            # sin match → 'Por clasificar' (regla 7: jamás se adivina).
            regla = elegir_regla(
                mov.descripcion, por_tipo[_TIPO_A_FLUJO[mov.tipo]], activos
            )
            docs.append(
                movimiento_a_transaccion(
                    mov,
                    rubro_id=regla.rubro_id if regla is not None else rubro.id,
                    mes_id=mc.id,
                    carga_id=carga.id,
                    ocurrencia=conteo[clave],
                    regla_id=regla.id if regla is not None else None,
                )
            )

        holder = {"nuevas": 0, "duplicadas": 0}
        if docs:
            ids = [d.id_banco for d in docs]
            client = Transaccion.get_pymongo_collection().database.client

            async def _finalizar(session):
                # Pre-filtro dentro de la sesión (M-02): ids ya presentes de OTRAS
                # cargas (el ordinal hace únicos los de ESTE archivo).
                existentes = set()
                async for t in Transaccion.find(
                    Transaccion.banco == banco,
                    In(Transaccion.id_banco, ids),
                    session=session,
                ):
                    existentes.add(t.id_banco)
                nuevos = [d for d in docs if d.id_banco not in existentes]
                if nuevos:
                    await Transaccion.insert_many(nuevos, session=session)
                holder["nuevas"] = len(nuevos)
                holder["duplicadas"] = len(docs) - len(nuevos)
                _finalizar_carga_doc(
                    carga,
                    resultado,
                    errores,
                    holder["nuevas"],
                    holder["duplicadas"],
                    nuevos_docs=nuevos,
                )
                await carga.save(session=session)

            async with await client.start_session() as session:
                await session.with_transaction(_finalizar)
        else:
            _finalizar_carga_doc(carga, resultado, errores, 0, 0)
            await carga.save()

        await emit_audit(
            AuditEvento.carga_completada,
            entidad="carga",
            entidad_id=str(carga.id),
            actor_id=str(usuario_id),
            metadata={
                "banco": banco.value,
                "nuevas": holder["nuevas"],
                "duplicadas": holder["duplicadas"],
                "errores": len(errores),
                # C3 (D3): ancla agregada de la clasificación automática.
                "clasificadas": carga.clasificadas,
                "por_clasificar": carga.por_clasificar,
                "reglas_con_rubro_inactivo": carga.reglas_con_rubro_inactivo,
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
        except Exception:  # noqa: BLE001 — no enmascarar el error original
            pass
        raise


def _preservar(origen: str, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(origen, destino)
