# backend/app/metas_ingreso/service.py
"""Metas de ingreso (D2 §6, CR-D2) — INFORMATIVAS: no alimentan el motor ni la caja.

Meta por mes (con líneas opcionales) vs. ingreso real ejecutado (suma de las
transacciones de INGRESO del mes) → % de cumplimiento. CRUD auditado (saga O1). Una
meta activa por mes."""

from decimal import Decimal

from beanie import PydanticObjectId

from app.audit.events import AuditEvento
from app.audit.service import emit_audit
from app.core.money import Money
from app.core.time import now_bogota
from app.domain.mes_control import MesControl
from app.domain.transaccion import pares_clasificacion
from app.domain.obligacion import LineaMeta, MetaIngreso

# El set de neutros Y su resolver nombre→id viven en `app.domain.rubros_neutros` (E1 lo
# comparte — una verdad, un lugar); se re-exportan aquí para no romper los importadores
# existentes (metas_ingreso.service._ids_rubros_neutros sigue disponible).
from app.domain.rubros_neutros import (
    RUBROS_NEUTROS_INGRESO_REAL as RUBROS_NEUTROS_INGRESO_REAL,
)
from app.domain.rubros_neutros import (
    _ids_rubros_neutros as _ids_rubros_neutros,
)
from app.domain.transaccion import TipoFlujo, Transaccion


class MetasError(Exception):
    def __init__(self, detalle: str, status: int = 422) -> None:
        super().__init__(detalle)
        self.detalle = detalle
        self.status = status


async def _obtener(meta_id: str) -> MetaIngreso:
    try:
        mid = PydanticObjectId(meta_id)
    except Exception:
        raise MetasError("meta_id inválido", 422) from None
    m = await MetaIngreso.get(mid)
    if m is None:
        raise MetasError("la meta no existe", 404)
    return m


async def listar_metas(*, activo: bool | None = True) -> list[MetaIngreso]:
    filtros = []
    if activo is not None:
        filtros.append(MetaIngreso.activo == activo)
    return await MetaIngreso.find(*filtros).sort(+MetaIngreso.mes).to_list()


async def crear_meta(
    *, mes: str, valor: Money, lineas: list[LineaMeta], usuario_id: str
) -> MetaIngreso:
    existe = await MetaIngreso.find_one(
        MetaIngreso.mes == mes,
        MetaIngreso.activo == True,  # noqa: E712
    )
    if existe is not None:
        raise MetasError(f"ya hay una meta activa para {mes}", 409)
    meta = MetaIngreso(
        mes=mes,
        valor=valor,
        lineas=lineas,
        activo=True,
        creado_por=usuario_id,
        actualizado_at=now_bogota(),
    )
    await meta.insert()
    try:
        await emit_audit(
            AuditEvento.meta_ingreso_creada,
            entidad="meta_ingreso",
            entidad_id=str(meta.id),
            actor_id=usuario_id,
            metadata={"mes": mes},
        )
    except Exception:
        await meta.delete()
        raise
    return meta


async def editar_meta(
    *,
    meta_id: str,
    usuario_id: str,
    valor: Money | None = None,
    lineas: list[LineaMeta] | None = None,
) -> MetaIngreso:
    meta = await _obtener(meta_id)
    cambios: dict[str, dict] = {}
    previos: dict[str, object] = {}
    if valor is not None and valor != meta.valor:
        previos["valor"] = meta.valor
        cambios["valor"] = {"anterior": str(meta.valor), "nuevo": str(valor)}
        meta.valor = valor
    if lineas is not None:
        previos["lineas"] = meta.lineas
        cambios["lineas"] = {"anterior": len(meta.lineas), "nuevo": len(lineas)}
        meta.lineas = lineas
    if not cambios:
        raise MetasError("nada que editar", 422)
    meta.actualizado_at = now_bogota()
    await meta.save()
    try:
        await emit_audit(
            AuditEvento.meta_ingreso_editada,
            entidad="meta_ingreso",
            entidad_id=str(meta.id),
            actor_id=usuario_id,
            metadata={"cambios": cambios},
        )
    except Exception:
        for campo, val in previos.items():
            setattr(meta, campo, val)
        await meta.save()
        raise
    return meta


async def eliminar_meta(*, meta_id: str, usuario_id: str) -> None:
    meta = await _obtener(meta_id)
    if not meta.activo:
        raise MetasError("la meta ya está inactiva", 409)
    meta.activo = False
    meta.actualizado_at = now_bogota()
    await meta.save()
    try:
        await emit_audit(
            AuditEvento.meta_ingreso_eliminada,
            entidad="meta_ingreso",
            entidad_id=str(meta.id),
            actor_id=usuario_id,
            metadata={"mes": meta.mes},
        )
    except Exception:
        meta.activo = True
        await meta.save()
        raise


async def ingreso_real(mes: str) -> Decimal | None:
    """Ingreso ejecutado del mes = Σ de las transacciones de INGRESO, EXCLUIDOS los
    rubros neutros (reversas/devoluciones; a futuro tránsito Wava y ajuste). None si el
    mes no tiene MesControl (aún no se abrió el ciclo)."""
    mc = await MesControl.find_one(MesControl.mes == f"{mes[:7]}-01")
    if mc is None:
        return None
    neutros = await _ids_rubros_neutros()
    total = Decimal("0")
    async for t in Transaccion.find(Transaccion.mes_id == mc.id):
        if t.tipo_flujo is not TipoFlujo.INGRESO:
            continue
        # PTS6-B: expande partes; la exclusión de neutros aplica POR PARTE (una
        # consignación mixta suma solo sus partes no-neutras).
        for rid, val in pares_clasificacion(t):
            if rid not in neutros:
                total += val
    return total


# PTS6-E: el ingreso real, SEPARADO en cuota inicial vs. cuotas semanales, por el
# código del rubro (taxonomía canónica de COMPAS, igual que E1 lectura.py):
#   inicial  ← 0120 Cuotas iniciales   (rubro dormido hasta que se clasifique)
#   semanal  ← 0110 Recaudo de cartera (hoy TODO el ingreso cae aquí)
# Devuelve magnitudes por concepto (Decimal); los rubros de ingreso que no sean
# 0110/0120 (ni neutros) quedan fuera de esta partición pero SÍ cuentan en el total
# de `ingreso_real` — la partición es de los dos conceptos que el CEO pidió ver.
_COD_INICIAL = "0120"
_COD_SEMANAL = "0110"


async def ingreso_real_por_concepto(mes: str) -> dict[str, Decimal] | None:
    """{'inicial': Σ0120, 'semanal': Σ0110} del mes (INGRESO, expande partes,
    excluye neutros). None si el mes aún no tiene MesControl."""
    from app.domain.rubro import Rubro

    mc = await MesControl.find_one(MesControl.mes == f"{mes[:7]}-01")
    if mc is None:
        return None
    neutros = await _ids_rubros_neutros()
    concepto_por_id: dict[PydanticObjectId, str] = {}
    async for r in Rubro.find(Rubro.codigo == _COD_INICIAL):
        concepto_por_id[r.id] = "inicial"
    async for r in Rubro.find(Rubro.codigo == _COD_SEMANAL):
        concepto_por_id[r.id] = "semanal"
    out = {"inicial": Decimal("0"), "semanal": Decimal("0")}
    async for t in Transaccion.find(Transaccion.mes_id == mc.id):
        if t.tipo_flujo is not TipoFlujo.INGRESO:
            continue
        for rid, val in pares_clasificacion(t):
            if rid in neutros:
                continue
            concepto = concepto_por_id.get(rid)
            if concepto is not None:
                out[concepto] += val
    return out
