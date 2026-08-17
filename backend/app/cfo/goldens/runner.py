"""FABS · runner de evaluación. Corre cada golden contra su concepto de cfo/calc y
compara dentro de tolerancia. Los goldens con valor_esperado=None son de ABSTENCIÓN:
pasan solo si el concepto devuelve disponible=False. No imprime: devuelve un reporte."""

from decimal import Decimal

from app.cfo.calc.caja import caja_hoy
from app.cfo.calc.iva import iva_cuatrimestre
from app.cfo.calc.runway import runway
from app.cfo.goldens.modelo import CFOGolden

CONCEPTOS = {
    "caja_hoy": caja_hoy,
    "runway": runway,
    "iva_cuatrimestre": iva_cuatrimestre,
}


async def correr_goldens() -> dict:
    total = ok = abst_ok = 0
    fallos: list[dict] = []
    async for g in CFOGolden.find_all():
        fn = CONCEPTOS.get(g.concepto)
        if fn is None:
            fallos.append(
                {
                    "concepto": g.concepto,
                    "esperado": None,
                    "obtenido": None,
                    "delta": "concepto desconocido",
                }
            )
            total += 1
            continue
        r = await fn()
        total += 1
        if g.valor_esperado is None:  # caso de abstención
            if r.disponible is False and r.valor is None:
                abst_ok += 1
            else:
                fallos.append(
                    {
                        "concepto": g.concepto,
                        "esperado": "abstención",
                        "obtenido": str(r.valor),
                        "delta": "no abstuvo",
                    }
                )
            continue
        if r.valor is None:
            fallos.append(
                {
                    "concepto": g.concepto,
                    "esperado": str(g.valor_esperado),
                    "obtenido": None,
                    "delta": "sin dato",
                }
            )
            continue
        delta = (Decimal(r.valor) - Decimal(g.valor_esperado)).copy_abs()
        if delta <= Decimal(g.tolerancia):
            ok += 1
        else:
            fallos.append(
                {
                    "concepto": g.concepto,
                    "esperado": str(g.valor_esperado),
                    "obtenido": str(r.valor),
                    "delta": str(delta),
                }
            )
    return {"total": total, "ok": ok, "fallos": fallos, "abstenciones_ok": abst_ok}
