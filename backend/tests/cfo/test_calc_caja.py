# backend/tests/cfo/test_calc_caja.py
"""Task 3 FABS inc1 — concepto `caja_hoy`: lee la serie diaria real de COMPAS
(`caja.service.caja_diaria`) desde el ancla `caja_inicial`/`vigente_desde` de los
parámetros de proyección vigentes hasta hoy (Bogotá), y toma el último saldo con
su fecha de corte. Abstención sin parámetros vigentes; cae al ancla sin
movimientos en el rango. mongomock; patrón de la suite: init_beanie con
DOMAIN_DOCUMENTS (ver tests/test_control.py, tests/test_facturas.py)."""

from datetime import date
from decimal import Decimal

import pytest_asyncio
from app.domain import DOMAIN_DOCUMENTS
from app.domain.mes_control import MesControl
from app.domain.parametros_proyeccion import ParametrosProyeccion
from app.domain.rubro import Rubro
from app.domain.transaccion import Transaccion
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient


def _parametros_completos(**overrides) -> ParametrosProyeccion:
    """Fixture COMPLETA y válida del modelo real (todos los campos obligatorios
    de `app/domain/parametros_proyeccion.py`), en cero salvo lo que el test
    necesite — mismo patrón que `tests/test_facturas.py`."""
    campos = {
        "vigente_desde": "2026-08-01",
        "caja_inicial": Decimal("0"),
        "caja_minima": Decimal("0"),
        "motos_base": 0,
        "crec_pct_mensual": Decimal("0"),
        "horizonte_meses": 8,
        "adelanto_auteco": Decimal("0"),
        "plazo_auteco_dias": 0,
        "base_auteco_dias": 0,
        "tasa_auteco": Decimal("0"),
        "gastos_fijos": Decimal("0"),
        "gps_moto": Decimal("0"),
        "costo_moto_nueva": Decimal("0"),
        "deuda": Decimal("0"),
        "tasa_deuda": Decimal("0"),
        "mes_inicio_deuda": 0,
        "meses_deuda": 0,
        "pct_mora": Decimal("0"),
        "pct_recuperacion": Decimal("0"),
        "pct_default": Decimal("0"),
        "pct_provision": Decimal("0"),
    }
    campos.update(overrides)
    return ParametrosProyeccion(**campos)


@pytest_asyncio.fixture
async def db():
    """DB con parámetros vigentes (caja_inicial=700M desde 2026-08-01) + un
    MesControl y un Rubro reales para poder insertar Transaccion válidas."""
    c = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
    mc = MesControl(mes="2026-08-01", saldo_inicial_caja=Decimal("0"))
    await mc.insert()
    rubro = Rubro(grupo="ingresos_operativos", nombre="Cuotas iniciales", orden=1)
    await rubro.insert()
    await _parametros_completos(caja_inicial=Decimal("700000000")).insert()
    yield {"mc_id": mc.id, "rubro_id": rubro.id}


async def _tx(ids: dict, fecha: str, valor: str, tipo: str = "ingreso") -> None:
    await Transaccion(
        fecha=fecha,
        descripcion="ingreso real",
        valor=Decimal(valor),
        tipo_flujo=tipo,
        rubro_id=ids["rubro_id"],
        mes_id=ids["mc_id"],
        banco="global66",
        id_banco=f"ING-{fecha}-{valor}",
    ).insert()


async def test_caja_hoy_devuelve_ultimo_saldo_con_fecha_corte(db, monkeypatch):
    import app.cfo.calc.caja as caja_mod

    # Ancla hoy=2026-08-04 (patch en el NOMBRE importado dentro de caja.py, no en
    # app.core.time — mismo idioma que tests/test_bank_parsers.py::TestFronteraAnio).
    monkeypatch.setattr(caja_mod, "today_bogota", lambda: date(2026, 8, 4))
    await _tx(db, "2026-08-02", "5000000")
    await _tx(db, "2026-08-04", "3000000")
    # Movimiento POSTERIOR al "hoy" simulado: si el patch no tomara efecto (se
    # usara la fecha real del sistema, muy posterior), este movimiento SÍ entraría
    # al rango y cambiaría valor/fecha_corte — es la prueba de que el patch aplica.
    await _tx(db, "2026-08-06", "999000000")

    r = await caja_mod.caja_hoy()
    assert r.concepto == "caja_hoy"
    assert r.unidad == "COP"
    assert r.disponible is True
    assert r.valor == Decimal("708000000.00")  # 700M + 5M + 3M (el 08-06 excluido)
    assert r.evidencia.fuente == "caja.service.caja_diaria"
    assert r.evidencia.fecha_corte == "2026-08-04"
    assert r.evidencia.ref == "2026-08"
    assert r.detalle == {"desde": "2026-08-01", "hasta": "2026-08-04"}


async def test_caja_hoy_sin_movimientos_cae_al_ancla(db, monkeypatch):
    import app.cfo.calc.caja as caja_mod

    monkeypatch.setattr(caja_mod, "today_bogota", lambda: date(2026, 8, 4))
    # Sin transacciones insertadas: caja_diaria() devuelve dias=[] (serie_diaria
    # solo emite días CON movimiento) → cae al ancla caja_inicial/vigente_desde.
    r = await caja_mod.caja_hoy()
    assert r.disponible is True
    assert r.valor == Decimal("700000000")
    assert r.evidencia.fecha_corte == "2026-08-01"
    assert r.evidencia.ref == "sin-movimientos"


async def test_caja_hoy_sin_parametros_abstiene():
    c = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=c["compas_vacio"], document_models=DOMAIN_DOCUMENTS)

    from app.cfo.calc.caja import caja_hoy

    r = await caja_hoy()
    assert r.disponible is False
    assert r.valor is None
    assert r.evidencia.fecha_corte is None
    assert r.evidencia.ref == "sin-parametros"
