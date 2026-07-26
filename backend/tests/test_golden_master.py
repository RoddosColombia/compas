# backend/tests/test_golden_master.py
"""GOLDEN-MASTER del motor de proyección C7 (PR-3, CR "Fidelidad de caja", tarea #21).

Compara el motor Python contra la GOLDEN = salida de la función `simular()` REAL del
artefacto de referencia (backend/tests/golden/golden_simular.json, generada por
gen_golden.mjs corriendo el JSX verbatim en Node). Escenario: el `p` por defecto del
artefacto (rampa real MAY/JUN-26, 50 motos/mes @1%, cartera previa de 111 créditos).

Dos divergencias INTENCIONALES, aisladas para que el resto calce AL PESO:
  1. Provisión NIIF 9: el motor la excluye del flujo (caja veraz); la golden se genera
     con pctProvision=0. (La exclusión se prueba en test_proyeccion_motor.)
  2. Distribución nwSimulador: el artefacto reparte la colocación con un patrón fijo de
     "semanas en mes" que se DESFASA del calendario real desde MAY-28 (m>=24). El motor
     usa miércoles reales (más preciso; decisión de diseño). Por eso los campos que
     dependen de la distribución de cohortes (cartera, recaudo, gps, bruto, neto,
     egresos, flujo, caja) se validan EXACTO solo en los meses 0-23 (MAY-26 -> ABR-28,
     que cubre el umbral de mayo-2027 con margen); los campos independientes de la
     distribución se validan en los 176 meses.

Tolerancia en dinero: float (JS) vs Decimal (Python) — diferencia sub-peso por mes.
"""

import json
from decimal import Decimal
from pathlib import Path

from app.domain.cartera_previa_semilla import SEMILLA_CARTERA_PREVIA
from app.proyeccion.motor import ModeloProyeccion, ParametrosMotor, proyectar

GOLDEN = json.loads(
    (Path(__file__).parent / "golden" / "golden_simular.json").read_text(
        encoding="utf-8"
    )
)

# meses 0..23 (MAY-26 → ABR-28): nwSimulador == miércoles reales → paridad exacta.
VENTANA_EXACTA = 24
TOL = Decimal("2")  # COP; float(JS) vs Decimal

# golden_key, atributo del motor, es_entero, depende_de_distribucion_de_cohortes
CAMPOS = [
    ("motos", "motos", True, False),
    ("cartera", "cartera", True, True),
    ("recaudo", "recaudo_credito", False, True),
    ("iniciales", "cuotas_iniciales", False, False),
    ("bruto", "ingreso_bruto", False, True),
    ("neto", "neto", False, True),
    ("gastosFijos", "gastos_fijos", False, False),
    ("gps", "gps", False, True),
    ("costoNueva", "costo_nueva", False, False),
    ("adelanto", "adelanto", False, False),
    ("pagoInv", "pago_inventario", False, False),
    ("fondeo", "fondeo", False, False),
    ("intDeuda", "int_deuda", False, False),
    ("egresos", "egresos", False, True),
    ("flujo", "flujo", False, True),
    ("caja", "caja", False, True),
]


def _escenario_default() -> ParametrosMotor:
    """El `p` por defecto del artefacto (Dashboard_Artefacto.jsx), traducido a
    ParametrosMotor + la cartera previa de la semilla."""
    raider = ModeloProyeccion(
        nombre="Raider",
        cuota_semanal=Decimal("164900"),
        cuota_inicial=Decimal("1070000"),
        plazo_semanas=78,
        mix=Decimal("0.70"),
        costo_moto=Decimal("5638974"),
    )
    apache = ModeloProyeccion(
        nombre="Apache",
        cuota_semanal=Decimal("209900"),
        cuota_inicial=Decimal("1401000"),
        plazo_semanas=78,
        mix=Decimal("0.30"),
        costo_moto=Decimal("6818517"),
    )
    previa_recaudo = {s["semana_global"]: s["recaudo"] for s in SEMILLA_CARTERA_PREVIA}
    previa_activos = {
        s["semana_global"]: s["n_activos"] for s in SEMILLA_CARTERA_PREVIA
    }
    return ParametrosMotor(
        mes_inicio=(2026, 5),
        horizonte_meses=176,
        modelos=[raider, apache],
        motos_base=50,
        crec_pct_mensual=Decimal("0.01"),
        rampa=[20, 48],
        adelanto_auteco=Decimal("970000"),
        plazo_auteco_dias=150,
        base_auteco_dias=90,
        tasa_auteco=Decimal("0.016"),
        gastos_fijos=Decimal("125206342.23178737"),
        gps_moto=Decimal("33201"),
        costo_moto_nueva=Decimal("692005"),
        deuda=Decimal("28527080"),
        tasa_deuda=Decimal("0.115679557809632"),
        mes_inicio_deuda=2,
        meses_deuda=14,
        pct_mora=Decimal("0.03"),
        pct_recuperacion=Decimal("0.40"),
        pct_default=Decimal("0.03"),
        pct_provision=Decimal("0"),  # golden generada con pctProvision=0
        overrides_mora=None,
        overrides_default=None,
        caja_inicial=Decimal("24000000"),
        caja_minima=Decimal("125000000"),
        recaudo_previo_por_semana=previa_recaudo,
        activos_previos_por_semana=previa_activos,
        apache_por_mes={0: 0, 1: 17},
        en_cartera_meses={0, 1},
        meses_rampa={0, 1},
        iniciales_override={0: Decimal("26110000"), 1: Decimal("80810000")},
        adelanto_override={1: Decimal("-80810000")},
        lote_override={0: Decimal("109816454")},
    )


def test_golden_master_paridad_por_mes():
    r = proyectar(_escenario_default())
    assert len(r.meses) == len(GOLDEN["meses"]) == 176
    fallos: list[str] = []
    for i, m in enumerate(r.meses):
        g = GOLDEN["meses"][i]
        for gk, attr, es_int, dep in CAMPOS:
            if dep and i >= VENTANA_EXACTA:
                continue  # divergencia nwSim documentada (2028+)
            actual = getattr(m, attr)
            esperado = g[gk]
            if es_int:
                if actual != esperado:
                    fallos.append(f"{m.mes} {gk}: {actual} != {esperado}")
            else:
                dif = abs(actual - Decimal(str(esperado)))
                if dif > TOL:
                    fallos.append(f"{m.mes} {gk}: {actual} vs {esperado} (dif {dif})")
    assert not fallos, f"{len(fallos)} discrepancias:\n" + "\n".join(fallos[:40])


_MESES_ABBR = [
    "ENE",
    "FEB",
    "MAR",
    "ABR",
    "MAY",
    "JUN",
    "JUL",
    "AGO",
    "SEP",
    "OCT",
    "NOV",
    "DIC",
]


def _a_yyyy_mm(mmm_yy: str) -> str:
    """'MAY-27' (formato del artefacto) → '2027-05' (formato del motor)."""
    mmm, yy = mmm_yy.split("-")
    return f"20{yy}-{_MESES_ABBR.index(mmm) + 1:02d}"


def test_golden_master_kpis():
    # el piso de caja cae en MAY-27 (m=12, dentro de la ventana exacta) → comparable.
    r = proyectar(_escenario_default())
    k = GOLDEN["kpis"]
    assert r.mes_mas_ajustado == _a_yyyy_mm(k["minCajaMes"])
    assert abs(r.piso_caja - Decimal(str(k["minCaja"]))) <= TOL
    assert abs(r.capital_requerido - Decimal(str(k["capitalRequerido"]))) <= TOL
