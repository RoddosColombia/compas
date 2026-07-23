# backend/app/caja/service.py
"""C4 — reporte diario de saldos por banco (CR-S6, GO Kimi PLAN-I 9.3).

MARCADO PARA AUDITORÍA KIMI (B-1 atomicidad posicional + D2 guardas de fecha +
saga O1 + regla 2/regla 1).

El norte del producto define DOS entradas diarias: los movimientos del banco (C2/C3)
y **el valor de la caja disponible** — este servicio es el segundo. `reportar_saldos`
hace UPSERT del saldo reportado por banco sobre `mc.saldos_banco` (la estructura que
la conciliación §M-3 y el cierre §M-2 ya consumen: cero cambios en superficie
crítica) y devuelve la conciliación al instante (D4, "que la información siempre
cuadre").

- **B-1 (Kimi):** el upsert es un update ATÓMICO POSICIONAL por banco
  (`saldos_banco.$` para existente, `$push` con filtro `$ne` para nuevo), NO un
  read-modify-write de la lista entera — dos reportes concurrentes sobre bancos
  distintos no se pisan (lost update imposible).
- **D2:** `fecha_reporte` en `YYYY-MM-DD`, dentro de `[mc.mes, hoy(Bogotá)]` y
  **sin retroceso por banco** (retrasarla re-incluiría movimientos viejos como
  "posteriores" en `calculado(b)` sin rastro — fail-loud, regla 7).
- **D3:** solo meses `en_ejecucion` (el reporte es del mes OPERANDO; regla 4 congela
  los cerrados; los futuros reciben su saldo por apertura/arrastre F-14).
- **O1:** un evento `saldo_banco.reportado` por banco (metadata con valores y fechas
  anterior→nuevo). Fail-closed: write→emit por banco; si el emit cae, se restaura el
  estado previo de ESE banco (posicional o `$pull` si era nuevo) y propaga."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from bson import Decimal128

from app.audit.events import AuditEvento
from app.audit.service import emit_audit
from app.cierre.service import conciliacion
from app.core.money import money_str
from app.core.time import today_bogota
from app.domain.bancos import Banco
from app.domain.mes_control import EstadoMes, MesControl, SaldoBanco

_FECHA_LEN = 10  # 'YYYY-MM-DD'
_MAX_REINTENTOS = 3  # contención posicional↔push (carrera del banco nuevo)


class CajaError(Exception):
    def __init__(self, detalle: str, status: int = 422) -> None:
        super().__init__(detalle)
        self.detalle = detalle
        self.status = status


@dataclass(frozen=True)
class ReporteBanco:
    """Un reporte de saldo para un banco (el router ya validó banco y Decimal)."""

    banco: Banco
    saldo: Decimal
    fecha_reporte: str


def _valida_fecha_formato(v: str) -> None:
    if len(v) != _FECHA_LEN:
        raise CajaError(f"fecha_reporte debe ser 'YYYY-MM-DD': {v}", 422)
    try:
        datetime.strptime(v, "%Y-%m-%d")
    except ValueError as e:
        raise CajaError(f"fecha_reporte inválida: {v}", 422) from e


async def _upsert_saldo(col, mes: str, r: ReporteBanco) -> None:
    """Update atómico posicional por banco (B-1): sin read-modify-write de la lista."""
    dec = Decimal128(r.saldo)
    for _ in range(_MAX_REINTENTOS):
        res = await col.update_one(
            {"mes": mes, "saldos_banco.banco": r.banco.value},
            {
                "$set": {
                    "saldos_banco.$.saldo": dec,
                    "saldos_banco.$.fecha_reporte": r.fecha_reporte,
                }
            },
        )
        if res.matched_count == 1:
            return
        # el banco no está aún → push SOLO si sigue ausente (filtro $ne)
        res2 = await col.update_one(
            {"mes": mes, "saldos_banco.banco": {"$ne": r.banco.value}},
            {
                "$push": {
                    "saldos_banco": {
                        "banco": r.banco.value,
                        "saldo": dec,
                        "fecha_reporte": r.fecha_reporte,
                    }
                }
            },
        )
        if res2.matched_count == 1:
            return
        # matched_count==0: el banco apareció concurrentemente → reintentar posicional
    raise CajaError(
        "no se pudo aplicar el reporte de saldo (contención); reintentar", 409
    )


async def _restaurar(col, mes: str, banco: Banco, previo: SaldoBanco | None) -> None:
    """Compensación O1 POR BANCO (B-1): restaura el saldo previo o retira el nuevo."""
    if previo is None:
        await col.update_one(
            {"mes": mes}, {"$pull": {"saldos_banco": {"banco": banco.value}}}
        )
    else:
        await col.update_one(
            {"mes": mes, "saldos_banco.banco": banco.value},
            {
                "$set": {
                    "saldos_banco.$.saldo": Decimal128(previo.saldo),
                    "saldos_banco.$.fecha_reporte": previo.fecha_reporte,
                }
            },
        )


async def reportar_saldos(
    *, mes: str, reportes: list[ReporteBanco], usuario_id: str
) -> dict:
    mc = await MesControl.find_one(MesControl.mes == mes)
    if mc is None:
        raise CajaError(f"el mes {mes[:7]} no existe", 404)
    if mc.estado is not EstadoMes.EN_EJECUCION:  # D3
        raise CajaError(
            f"solo se reportan saldos de un mes en ejecución "
            f"(está en '{mc.estado.value}')",
            409,
        )

    vigentes = {sb.banco: sb for sb in mc.saldos_banco}
    hoy = today_bogota().isoformat()
    # D2: validar TODO antes de escribir (todo-o-nada en validación).
    for r in reportes:
        _valida_fecha_formato(r.fecha_reporte)
        if r.fecha_reporte < mc.mes:
            raise CajaError(
                f"fecha_reporte {r.fecha_reporte} es anterior al mes {mes[:7]} "
                "(contaría todo el mes como posterior)",
                422,
            )
        if r.fecha_reporte > hoy:
            raise CajaError(
                f"fecha_reporte {r.fecha_reporte} está en el futuro (hoy {hoy})", 422
            )
        prev = vigentes.get(r.banco)
        if prev is not None and r.fecha_reporte < prev.fecha_reporte:
            raise CajaError(
                f"no-retroceso: {r.banco.value} ya reportó {prev.fecha_reporte}; "
                f"{r.fecha_reporte} es anterior (regla 7)",
                422,
            )

    col = MesControl.get_pymongo_collection()
    # write→emit POR BANCO: cada banco queda con su escritura Y su evento consistentes;
    # si el emit de un banco cae, se restaura ESE banco (los previos quedan íntegros).
    for r in reportes:
        prev = vigentes.get(r.banco)
        await _upsert_saldo(col, mc.mes, r)
        try:
            await emit_audit(
                AuditEvento.saldo_banco_reportado,
                entidad="mes",
                entidad_id=str(mc.id),
                actor_id=usuario_id,
                metadata={
                    "mes": mes[:7],
                    "banco": r.banco.value,
                    "saldo_anterior": money_str(prev.saldo) if prev else None,
                    "saldo_nuevo": money_str(r.saldo),
                    "fecha_reporte_anterior": prev.fecha_reporte if prev else None,
                    "fecha_reporte_nueva": r.fecha_reporte,
                },
            )
        except Exception:
            await _restaurar(col, mc.mes, r.banco, prev)
            raise

    mc = await MesControl.get(mc.id)
    return {
        "mes": mes[:7],
        "saldos_banco": [
            {
                "banco": sb.banco.value,
                "saldo": money_str(sb.saldo),
                "fecha_reporte": sb.fecha_reporte,
            }
            for sb in mc.saldos_banco
        ],
        # D4: la conciliación al instante, misma función que el GET (misma verdad).
        "conciliacion": await conciliacion(mes),
    }
