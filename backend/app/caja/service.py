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
from app.caja.diaria import serie_diaria
from app.cierre.service import conciliacion
from app.cierre.transito import transito_heredado
from app.core.money import money_str
from app.core.time import today_bogota
from app.domain.bancos import Banco
from app.domain.mes_control import EstadoMes, MesControl, SaldoBanco
from app.domain.transaccion import Transaccion

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
    """Update atómico posicional por banco (B-1) con no-retroceso y estado ATÓMICOS
    (A-6, cierre del TOCTOU). Las guardas de `reportar_saldos` (estado en_ejecucion,
    no-retroceso por banco) corren FUERA sobre un snapshot leído antes de escribir;
    aquí se REAFIRMAN dentro de la propia escritura para que una carrera no cuele un
    retroceso ni escriba sobre un mes que se cerró concurrentemente:

    - `$set` posicional SOLO si el mes sigue `en_ejecucion` Y el elemento del banco
      existe con `fecha_reporte <= la nueva` (mismo elemento, vía `$elemMatch` — el
      `$` apunta al elemento que casó, no a otro banco).
    - `$push` SOLO si el banco sigue ausente (`$ne`) y el mes sigue en ejecución.
    Si ninguno casa, relee para DISTINGUIR la causa: retroceso real → 422; mes ya no
    en ejecución → 409; contención transitoria (el banco apareció con fecha <= la
    nueva) → reintenta el posicional."""
    dec = Decimal128(r.saldo)
    en_ejec = EstadoMes.EN_EJECUCION.value
    for _ in range(_MAX_REINTENTOS):
        res = await col.update_one(
            {
                "mes": mes,
                "estado": en_ejec,
                "saldos_banco": {
                    "$elemMatch": {
                        "banco": r.banco.value,
                        "fecha_reporte": {"$lte": r.fecha_reporte},
                    }
                },
            },
            {
                "$set": {
                    "saldos_banco.$.saldo": dec,
                    "saldos_banco.$.fecha_reporte": r.fecha_reporte,
                }
            },
        )
        if res.matched_count == 1:
            return
        # el banco no está aún → push SOLO si sigue ausente ($ne) y el mes en ejecución
        res2 = await col.update_one(
            {
                "mes": mes,
                "estado": en_ejec,
                "saldos_banco.banco": {"$ne": r.banco.value},
            },
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
        # ni $set ni $push casaron → releer y distinguir la causa (no adivinar).
        doc = await col.find_one({"mes": mes}, {"estado": 1, "saldos_banco": 1})
        if doc is None:
            raise CajaError(f"el mes {mes[:7]} no existe", 404)
        if doc.get("estado") != en_ejec:
            raise CajaError(
                f"el mes {mes[:7]} dejó de estar en ejecución durante el reporte "
                "(concurrencia); reintentar",
                409,
            )
        actual = next(
            (sb for sb in doc.get("saldos_banco", []) if sb["banco"] == r.banco.value),
            None,
        )
        if actual is not None and actual["fecha_reporte"] > r.fecha_reporte:
            raise CajaError(
                f"no-retroceso: {r.banco.value} ya reportó {actual['fecha_reporte']}; "
                f"{r.fecha_reporte} es anterior (regla 7)",
                422,
            )
        # el banco apareció concurrentemente con fecha <= la nueva → reintentar $set
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


async def caja_diaria(*, desde: str, hasta: str, caja_inicial: Decimal) -> dict:
    """Evolución DIARIA de la caja en [desde, hasta] (YYYY-MM-DD). Lee las
    transacciones reales (todos los bancos), corre el saldo desde `caja_inicial`.
    No depende del motor ni del ciclo presupuestal — sirve para administrar el flujo
    de caja con la data ya cargada. Devuelve montos como string (regla 1)."""
    movs: list[dict] = []
    async for t in Transaccion.find(
        Transaccion.fecha >= desde, Transaccion.fecha <= hasta
    ):
        movs.append({"fecha": t.fecha, "tipo_flujo": t.tipo_flujo, "valor": t.valor})
    serie = serie_diaria(movs, caja_inicial)
    total_ing = sum((d["ingresos"] for d in serie), Decimal("0"))
    total_egr = sum((d["egresos"] for d in serie), Decimal("0"))
    return {
        "desde": desde,
        "hasta": hasta,
        "caja_inicial": money_str(caja_inicial),
        "total_ingresos": money_str(total_ing),
        "total_egresos": money_str(total_egr),
        "flujo_neto": money_str(total_ing - total_egr),
        "caja_final": money_str(caja_inicial + total_ing - total_egr),
        "dias": [
            {
                "fecha": d["fecha"],
                "ingresos": money_str(d["ingresos"]),
                "egresos": money_str(d["egresos"]),
                "flujo": money_str(d["flujo"]),
                "caja": money_str(d["caja"]),
                "n": d["n"],
            }
            for d in serie
        ],
    }


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


async def saldo_disponible() -> dict:
    """Saldo disponible EN VIVO (CEO 2026-08-24) — el número fijo que el CEO quiere ver
    siempre, actualizado cada vez que se cargan movimientos.

    Lectura pura (no toca el motor ni escribe estado). REUSA `conciliacion` del cierre:
    el saldo del widget es EXACTAMENTE el `calculado` de la conciliación, para que nunca
    existan dos "saldos" distintos en la app (un test lo blinda). Le agrega:
      - el TOTAL = saldo en banco + tránsito Wava heredado (la misma definición que el
        arranque del ciclo, `caja_inicial_total`, y que «Banco + Wava» del Excel);
      - la FRESCURA por banco: fecha del último movimiento y días sin registrar, para
        que el CEO sepa si el número está al día (atrasado ⇒ ámbar en la UI)."""
    mc = await MesControl.find_one(MesControl.estado == EstadoMes.EN_EJECUCION)
    if mc is None:
        # Regla 7: sin mes operando no se inventa un saldo; se dice.
        return {"disponible": False, "motivo": "sin_mes_en_ejecucion"}

    conc = await conciliacion(mc.mes)
    transito = await transito_heredado(mc.mes)

    # Frescura: fecha del último movimiento POR BANCO (una sola pasada; MANUAL no es un
    # banco reportable — se omite, igual que en la conciliación).
    ultimo_por_banco: dict[str, str] = {}
    async for t in Transaccion.find(Transaccion.mes_id == mc.id):
        if t.banco is Banco.MANUAL:
            continue
        b = t.banco.value
        if b not in ultimo_por_banco or t.fecha > ultimo_por_banco[b]:
            ultimo_por_banco[b] = t.fecha

    hoy = today_bogota()

    def _dias(fecha: str | None) -> int | None:
        if fecha is None:
            return None
        return (hoy - datetime.strptime(fecha, "%Y-%m-%d").date()).days

    por_banco = []
    for b in conc["por_banco"]:
        fecha_ult = ultimo_por_banco.get(b["banco"])
        por_banco.append(
            {
                "banco": b["banco"],
                "saldo": b["calculado"],  # == la conciliación, sin divergencia
                "reportado": b["reportado"],
                "ultimo_movimiento": fecha_ult,
                "dias_sin_registrar": _dias(fecha_ult),
            }
        )

    # Frescura global: el movimiento más reciente de cualquier banco.
    ultimo_global = max(ultimo_por_banco.values(), default=None)
    dias = _dias(ultimo_global)
    # Al día si el último movimiento es de hoy o ayer; atrasado si ya pasaron ≥2 días.
    estado = (
        "sin_movimientos" if dias is None else "al_dia" if dias <= 1 else "atrasado"
    )

    saldo_banco = Decimal(conc["consolidado_reportado"])
    return {
        "disponible": True,
        "mes": mc.mes[:7],
        "corte": hoy.isoformat(),
        "saldo_en_banco": conc["consolidado_reportado"],
        "transito_wava": money_str(transito),
        "total": money_str(saldo_banco + transito),
        "por_banco": por_banco,
        # Regla 7: bancos con movimientos pero sin saldo reportado (no se calculan a 0).
        "sin_dato": conc["sin_dato"],
        "frescura": {
            "ultimo_movimiento": ultimo_global,
            "dias": dias,
            "estado": estado,
        },
    }
