# backend/tests/test_e1_pipeline.py
"""E1 · P3 — composición en `_resultado_con` (integración: motor → E1 → D2 → IMPACTOS).

Verifica el ORDEN efectivo y la no-colisión E1×D2 leyendo `_resultado_con`, con
`anclas_override`/`facturas_override` para determinismo. Tres corridas sobre el mismo
motor:

    A = anclar 2026-10 + facturas que pagan 2026-10 y 2026-12
    B = anclar 2026-10 + SIN facturas   (Auteco de 2026-10 = paramétrico del motor)
    C = SIN anclaje    + las mismas facturas

B8  — orden efectivo: en A, 2026-10 lo fija E1 y D2 lo SALTA (≠ C, que lo reconcilia).
B11 — E1 no toca Auteco (A[2026-10] == B[2026-10], el paramétrico), y D2 solo toca los
      NO anclados (A[2026-12] = pago real).
Candado — sin anclaje (C) D2 reconcilia todo como hoy (2026-10 con su pago real)."""

from decimal import Decimal

import pytest
import pytest_asyncio
from app.domain import DOMAIN_DOCUMENTS
from app.domain.modelo_moto import ModeloMoto
from app.domain.parametros_proyeccion import ParametrosProyeccion
from app.obligaciones.calculadora import pago_factura
from app.obligaciones.reconciliacion import FacturaReconciliar
from app.proyeccion.ejecucion.lectura import RubroInfo
from app.proyeccion.ejecucion.service import AnclaMes
from app.proyeccion.service import _resultado_con
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient

_MES_INICIO = (2026, 7)
_HORIZONTE = 12

# Plan con los 9 códigos del mapeo presentes (B12 no dispara). Sin ejecutado, E1 solo
# ancla ingreso_real y CONSERVA el Auteco del motor — justo lo que B11 mide.
_PLAN = [
    ("0110", "ingresos_operativos", "Recaudo de cartera"),
    ("1010", "costo_producto", "Producto"),
    ("1020", "costo_producto", "SOAT/Matrículas"),
    ("1030", "costo_producto", "Seguros"),
    ("4010", "deudas_obligaciones", "Préstamos"),
    ("4020", "deudas_obligaciones", "Tarjetas"),
    ("4030", "deudas_obligaciones", "Garantía cupo"),
    ("4050", "deudas_obligaciones", "Proveedores"),
    ("5060", "otros", "Impuestos"),
]


def _rubros() -> list[RubroInfo]:
    return [
        RubroInfo(id=cod, codigo=cod, grupo=gr, nombre=nom, es_sistema=False)
        for (cod, gr, nom) in _PLAN
    ]


def _params() -> ParametrosProyeccion:
    return ParametrosProyeccion(
        vigente_desde="2026-07-01",
        caja_inicial=Decimal("500000"),
        caja_minima=Decimal("10000"),
        motos_base=2,
        crec_pct_mensual=Decimal("0"),
        horizonte_meses=_HORIZONTE,
        adelanto_auteco=Decimal("0"),
        plazo_auteco_dias=60,
        base_auteco_dias=30,
        tasa_auteco=Decimal("0.016"),
        gastos_fijos=Decimal("1000"),
        gps_moto=Decimal("0"),
        costo_moto_nueva=Decimal("0"),
        deuda=Decimal("0"),
        tasa_deuda=Decimal("0"),
        mes_inicio_deuda=0,
        meses_deuda=0,
        pct_mora=Decimal("0"),
        pct_recuperacion=Decimal("0"),
        pct_default=Decimal("0"),
        pct_provision=Decimal("0"),
    )


def _modelos() -> list[ModeloMoto]:
    return [
        ModeloMoto(
            nombre="Raider",
            costo_auteco=Decimal("5000"),
            precio_venta_con_iva=Decimal("6000"),
            cuota_inicial=Decimal("1000"),
            cuota_semanal=Decimal("100"),
            plazo_semanas=6,
            matricula=Decimal("0"),
            participacion_mix=Decimal("1"),
            orden=1,
        )
    ]


def _facturas() -> list[FacturaReconciliar]:
    # pagan 2026-10 (plazo 60) y 2026-12 (plazo 120)
    return [
        FacturaReconciliar(
            fecha_factura="2026-08-15",
            valor=Decimal("1000000"),
            plazo_elegido_dias=60,
            plazo_base_dias=30,
            tasa_excedente_mensual=Decimal("0.016"),
        ),
        FacturaReconciliar(
            fecha_factura="2026-08-15",
            valor=Decimal("2000000"),
            plazo_elegido_dias=120,
            plazo_base_dias=30,
            tasa_excedente_mensual=Decimal("0.016"),
        ),
    ]


def _anclas_oct():
    """Ancla 2026-10 como CERRADO con solo ingreso_real (ejecutado vacío) → E1 conserva
    el Auteco del motor en ese mes."""
    anclas = {
        "2026-10": AnclaMes(
            estado="cerrado",
            ejecutado_por_rubro_id={},
            definido_por_rubro_id={},
            ingreso_real=Decimal("123456.00"),
        )
    }
    return anclas, _rubros(), set()


@pytest_asyncio.fixture
async def db():
    c = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
    yield c


async def _correr(anclas_override, facturas_override):
    r, _cm, _fondo, _rec = await _resultado_con(
        _params(),
        _modelos(),
        escenario="base",
        mes_inicio=_MES_INICIO,
        horizonte_meses=_HORIZONTE,
        anclas_override=anclas_override,
        facturas_override=facturas_override,
    )
    return {m.mes: m for m in r.meses}


@pytest.mark.asyncio
async def test_b8_b11_candado_composicion(db):
    a = await _correr(_anclas_oct(), _facturas())  # A
    b = await _correr(_anclas_oct(), [])  # B
    c = await _correr(({}, [], set()), _facturas())  # C

    cap_oct = pago_factura(
        fecha_factura="2026-08-15",
        valor=Decimal("1000000"),
        plazo_elegido_dias=60,
        plazo_base_dias=30,
        tasa_excedente_mensual=Decimal("0.016"),
    )
    cap_dic = pago_factura(
        fecha_factura="2026-08-15",
        valor=Decimal("2000000"),
        plazo_elegido_dias=120,
        plazo_base_dias=30,
        tasa_excedente_mensual=Decimal("0.016"),
    )

    # B11 — E1 no toca Auteco: 2026-10 anclado conserva el paramétrico (A == B), aun
    # cuando una factura paga ahí (D2 lo excluyó).
    assert a["2026-10"].pago_inventario == b["2026-10"].pago_inventario
    assert a["2026-10"].fondeo == b["2026-10"].fondeo

    # B11 — D2 solo toca los NO anclados: 2026-12 lleva el pago real.
    assert a["2026-12"].pago_inventario == Decimal(f"-{cap_dic.capital}")
    assert a["2026-12"].fondeo == Decimal(f"-{cap_dic.interes}")

    # B8 — orden efectivo: sin anclaje (C) D2 SÍ reconcilia 2026-10; con anclaje (A) NO.
    assert c["2026-10"].pago_inventario == Decimal(f"-{cap_oct.capital}")
    assert c["2026-10"].pago_inventario != a["2026-10"].pago_inventario

    # E1 corrió: el mes anclado tomó el ingreso real anclado.
    assert a["2026-10"].neto == Decimal("123456.00")


def _anclas_no_cerrado(estado):
    """Ancla 2026-10 en un régimen NO cerrado con un egreso NO-Auteco (int_deuda vía
    4010). en_ejecucion usa Regla A (ejec+max(0,def-ejec)); presupuesto solo definido.
    Ambos → int_deuda anclado = 800 (→ -800.00). E1 NO toca Auteco en ningún caso."""
    if estado == "en_ejecucion":
        ancla = AnclaMes(
            estado="en_ejecucion",
            ejecutado_por_rubro_id={"4010": Decimal("500")},
            definido_por_rubro_id={"4010": Decimal("800")},
            ingreso_real=None,
        )
    else:  # presupuesto
        ancla = AnclaMes(
            estado="presupuesto",
            ejecutado_por_rubro_id={},
            definido_por_rubro_id={"4010": Decimal("800")},
            ingreso_real=None,
        )
    return {"2026-10": ancla}, _rubros(), set()


@pytest.mark.asyncio
@pytest.mark.parametrize("estado", ["en_ejecucion", "presupuesto"])
async def test_c1_d2_aplica_pago_real_en_mes_anclado_no_cerrado(db, estado):
    """C-1 (gate PR3-I): E1 no ancla Auteco, así que en un mes anclado NO cerrado D2 SÍ
    debe aplicar el pago real de la factura (sin doble conteo — campos disjuntos) y
    conservar los campos que E1 ancló. Antes del fix, meses_anclados=frozenset(anclas)
    excluía estos meses y el pago real de FIX-K desaparecía de la proyección."""
    a = await _correr(_anclas_no_cerrado(estado), _facturas())  # con facturas
    b = await _correr(_anclas_no_cerrado(estado), [])  # sin facturas (referencia)
    cap_oct = pago_factura(
        fecha_factura="2026-08-15",
        valor=Decimal("1000000"),
        plazo_elegido_dias=60,
        plazo_base_dias=30,
        tasa_excedente_mensual=Decimal("0.016"),
    )
    cap_dic = pago_factura(
        fecha_factura="2026-08-15",
        valor=Decimal("2000000"),
        plazo_elegido_dias=120,
        plazo_base_dias=30,
        tasa_excedente_mensual=Decimal("0.016"),
    )

    # EL FIX — D2 aplica el pago REAL en el mes anclado no-cerrado (antes: excluido).
    assert a["2026-10"].pago_inventario == Decimal(f"-{cap_oct.capital}")
    assert a["2026-10"].fondeo == Decimal(f"-{cap_oct.interes}")

    # E1 ancló int_deuda (=800 → -800.00) y D2 NO lo tocó (campos disjuntos).
    assert a["2026-10"].int_deuda == Decimal("-800.00")
    assert a["2026-10"].int_deuda == b["2026-10"].int_deuda

    # 2026-12 (no anclado) reconcilia normal.
    assert a["2026-12"].pago_inventario == Decimal(f"-{cap_dic.capital}")


@pytest.mark.asyncio
async def test_b10_loguea_mes_cerrado_sospechoso(db, caplog):
    """P4/B10: un mes CERRADO con ejecutado << definido se ancla igual (no se bloquea)
    pero se registra en log estructurado. La marca no cambia el régimen (sigue anclado y
    excluido de D2 por ser cerrado)."""
    import logging

    anclas = {
        "2026-10": AnclaMes(
            estado="cerrado",
            ejecutado_por_rubro_id={"4010": Decimal("40")},  # E=40
            definido_por_rubro_id={"4010": Decimal("100")},  # D=100 → 40<50 sospechoso
            ingreso_real=Decimal("0"),
        )
    }
    with caplog.at_level(logging.WARNING):
        res = await _correr((anclas, _rubros(), set()), [])
    assert "2026-10" in res  # se ancla igual (no se bloquea)
    assert any("B10" in r.getMessage() for r in caplog.records)
