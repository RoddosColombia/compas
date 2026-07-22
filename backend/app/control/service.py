# backend/app/control/service.py
"""Vista Control (Sprint 4, GO PLAN I 9.3): presupuesto vs ejecutado vs disponible.

MARCADO PARA AUDITORÍA KIMI (% ejecutado — DoD #3).

READ-ONLY: sin escrituras, sin transacciones, sin eventos. Por rubro (línea vigente
del mes) agrupado en los 5 grupos: `definido` (monto_definido), `ejecutado` (Σ egresos
del rubro en el mes, misma E(i) del motor §1.4.1), `disponible` (=definido−ejecutado),
`pct_ejecutado` (Decimal 2 dec HALF_EVEN, string; null si definido==0), `semaforo`
(verde ≤90 · amarillo 90–100 · rojo >100, calculado sobre el pct CUANTIZADO — B-1).
`caja` = saldo_inicial + Σ signo(tx) excluyendo SOLO el rubro 'Ajuste de conciliación'
('Por clasificar' SÍ cuenta: es dinero bancario real). `sin_presupuesto`: egresos en
rubros NO de sistema sin línea vigente (informativo, B-3)."""

from decimal import ROUND_HALF_EVEN, Decimal

from beanie import PydanticObjectId
from bson.decimal128 import Decimal128

from app.cierre.service import _RUBRO_AJUSTE, _caja_libro
from app.core.money import money_str
from app.domain.mes_control import EstadoMes, MesControl
from app.domain.presupuesto import PresupuestoLinea
from app.domain.rubro import Rubro, RubroGrupo, TipoFlujo
from app.domain.transaccion import Transaccion

_CENTAVO = Decimal("0.01")
_ABIERTO = (EstadoMes.EN_EJECUCION, EstadoMes.CERRADO)
_GRUPOS_ORDEN = list(RubroGrupo)  # orden de declaración (§1.2)


class ControlError(Exception):
    def __init__(self, detalle: str, status: int = 422) -> None:
        super().__init__(detalle)
        self.detalle = detalle
        self.status = status


def _pct(ejecutado: Decimal, definido: Decimal) -> Decimal | None:
    """% ejecutado cuantizado a 2 dec HALF_EVEN. None si definido==0 (regla 7)."""
    if definido == 0:
        return None
    return (ejecutado / definido * 100).quantize(_CENTAVO, rounding=ROUND_HALF_EVEN)


def _semaforo(pct: Decimal | None, ejecutado: Decimal) -> str:
    """Sobre el pct CUANTIZADO (B-1). definido==0: gasto→rojo, sin gasto→verde."""
    if pct is None:
        return "rojo" if ejecutado > 0 else "verde"
    if pct <= 90:
        return "verde"
    if pct <= 100:
        return "amarillo"
    return "rojo"


async def _egresos_por_rubro(mes_id: PydanticObjectId) -> dict[str, Decimal]:
    """$group: Σ egresos por rubro del mes (1 agregación; equivalente a la suma
    directa, mismo patrón del motor)."""
    col = Transaccion.get_pymongo_collection()
    pipeline = [
        {"$match": {"mes_id": mes_id, "tipo_flujo": TipoFlujo.EGRESO.value}},
        {"$group": {"_id": "$rubro_id", "total": {"$sum": "$valor"}}},
    ]
    out: dict[str, Decimal] = {}
    async for d in col.aggregate(pipeline):
        t = d["total"]
        dec = t.to_decimal() if isinstance(t, Decimal128) else Decimal(str(t))
        out[str(d["_id"])] = dec
    return out


async def control(mes: str) -> dict:
    mc = await MesControl.find_one(MesControl.mes == mes)
    if mc is None:
        raise ControlError(f"el mes {mes[:7]} no existe", 404)
    if mc.estado not in _ABIERTO:
        raise ControlError(
            f"la Vista Control aplica a meses en ejecución o cerrados "
            f"(está en '{mc.estado.value}')",
            409,
        )

    lineas = await PresupuestoLinea.find(
        PresupuestoLinea.mes_id == mc.id,
        PresupuestoLinea.vigente == True,  # noqa: E712
    ).to_list()
    rubros = {r.id: r for r in await Rubro.find_all().to_list()}
    egresos = await _egresos_por_rubro(mc.id)
    rubro_aj = next(
        (r for r in rubros.values() if r.nombre == _RUBRO_AJUSTE and r.es_sistema), None
    )

    por_grupo: dict[str, list[dict]] = {}
    con_linea: set[str] = set()
    for ln in lineas:
        r = rubros.get(ln.rubro_id)
        if r is None:
            continue
        con_linea.add(str(r.id))
        definido = ln.monto_definido if ln.monto_definido is not None else Decimal("0")
        ejec = egresos.get(str(r.id), Decimal("0"))
        disp = definido - ejec
        pct = _pct(ejec, definido)
        por_grupo.setdefault(r.grupo.value, []).append(
            {
                "rubro_id": str(r.id),
                "rubro": r.nombre,
                "orden": r.orden,
                "definido": definido,
                "ejecutado": ejec,
                "disponible": disp,
                "pct_ejecutado": str(pct) if pct is not None else None,
                "semaforo": _semaforo(pct, ejec),
            }
        )

    grupos_out = []
    tot_d = tot_e = tot_disp = Decimal("0")
    for g in _GRUPOS_ORDEN:
        filas = sorted(por_grupo.get(g.value, []), key=lambda f: f["orden"])
        if not filas:
            continue
        sd = sum((f["definido"] for f in filas), Decimal("0"))
        se = sum((f["ejecutado"] for f in filas), Decimal("0"))
        tot_d += sd
        tot_e += se
        tot_disp += sd - se
        grupos_out.append(
            {
                "grupo": g.value,
                "lineas": [
                    {
                        "rubro_id": f["rubro_id"],
                        "rubro": f["rubro"],
                        "definido": money_str(f["definido"]),
                        "ejecutado": money_str(f["ejecutado"]),
                        "disponible": money_str(f["disponible"]),
                        "pct_ejecutado": f["pct_ejecutado"],
                        "semaforo": f["semaforo"],
                    }
                    for f in filas
                ],
                "subtotal": {
                    "definido": money_str(sd),
                    "ejecutado": money_str(se),
                    "disponible": money_str(sd - se),
                },
            }
        )

    # B-3: egresos en rubros NO de sistema y sin línea vigente (informativo, regla 7).
    sin_presupuesto = []
    for rid, total in egresos.items():
        r = rubros.get(PydanticObjectId(rid))
        if r is None or r.es_sistema or rid in con_linea:
            continue
        sin_presupuesto.append({"rubro": r.nombre, "ejecutado": money_str(total)})

    caja = await _caja_libro(
        mc.id, rubro_aj.id if rubro_aj else None, mc.saldo_inicial_caja
    )
    return {
        "mes": mes[:7],
        "estado": mc.estado.value,
        "grupos": grupos_out,
        "total": {
            "definido": money_str(tot_d),
            "ejecutado": money_str(tot_e),
            "disponible": money_str(tot_disp),
        },
        "caja_disponible": money_str(caja),
        "sin_presupuesto": sin_presupuesto,
    }
