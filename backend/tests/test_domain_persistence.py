# backend/tests/test_domain_persistence.py
"""Round-trip contra Beanie+mongomock: Decimal sobrevive (Decimal128→Decimal) y
la semilla es idempotente. La UNICIDAD de índices NO se prueba aquí (mongomock no
la exige) — eso está en test_domain_indexes.py con @requires_real_mongo."""

from decimal import Decimal

import pytest
from app.domain import DOMAIN_DOCUMENTS
from app.domain.configuracion import Configuracion
from app.domain.mes_control import MesControl
from app.domain.rubro import Rubro
from app.domain.seed import (
    SEMILLA_REGLAS,
    seed_configuracion,
    seed_reglas_reporte,
    seed_rubros,
    seed_rubros_reporte,
)
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient


@pytest.fixture
async def db():
    # tz_aware=True como el Motor real (mongo.create_client): los datetime
    # re-leídos vuelven UTC-aware (regla 2), no naive.
    client = AsyncMongoMockClient(tz_aware=True)
    database = client["compas_test"]
    await init_beanie(database=database, document_models=DOMAIN_DOCUMENTS)
    return database


async def test_rubro_round_trip(db):
    await Rubro(grupo="operacion", nombre="Arriendos", orden=4).insert()
    got = await Rubro.find_one(Rubro.nombre == "Arriendos")
    assert got is not None and got.grupo.value == "operacion"


async def test_mes_control_decimal_round_trip(db):
    await MesControl(
        mes="2026-07-01", saldo_inicial_caja=Decimal("675967053.19")
    ).insert()
    got = await MesControl.find_one(MesControl.mes == "2026-07-01")
    assert isinstance(got.saldo_inicial_caja, Decimal)
    assert got.saldo_inicial_caja == Decimal("675967053.19")


async def test_configuracion_decimal_round_trip(db):
    await Configuracion(
        clave="UMBRAL_DIF_BANCO_CIERRE",
        valor_decimal=Decimal("50000"),
        vigente_desde="2026-01-01",
    ).insert()
    got = await Configuracion.find_one(Configuracion.clave == "UMBRAL_DIF_BANCO_CIERRE")
    assert got.valor_decimal == Decimal("50000")


async def test_seed_rubros_idempotente(db):
    # Plan de cuentas ARQUITECTURA_PRESUPUESTAL: 41 del plan + 'Ajuste de
    # conciliación' (sistema) = 42.
    n1 = await seed_rubros(db)
    total1 = await Rubro.find_all().count()
    n2 = await seed_rubros(db)  # segunda corrida: no debe duplicar
    total2 = await Rubro.find_all().count()
    assert n1 == 42 and total1 == 42
    assert n2 == 0 and total2 == 42
    sistema = await Rubro.find(Rubro.es_sistema == True).count()  # noqa: E712
    assert sistema == 3  # Recaudo de cartera, Por clasificar, Ajuste de conciliación


async def test_seed_rubros_no_pisa_ediciones(db):
    # $setOnInsert: un doc existente con la misma llave (grupo,nombre) NO se toca
    # aunque la semilla traiga otros valores (ediciones del Admin sobreviven).
    await Rubro(grupo="operacion", nombre="Cafetería", orden=77).insert()
    await seed_rubros(db)
    got = await Rubro.find_one(Rubro.nombre == "Cafetería")
    assert got.orden == 77  # el valor editado sobrevive al re-seed


async def test_seed_rubros_reporte_de_colisiones(db):
    # B-4 (Kimi PLAN-I C1): el re-seed REPORTA los (grupo,nombre) donde
    # $setOnInsert omitió por doc preexistente — un doc viejo con tipo_flujo/orden
    # distintos del mapeo de MODELO.md ya no pasa en silencio.
    await Rubro(
        grupo="operacion", nombre="Cafetería", orden=77, tipo_flujo="ingreso"
    ).insert()
    insertados, colisiones = await seed_rubros_reporte(db)
    assert insertados == 41  # 42 - 1 preexistente
    assert len(colisiones) == 1
    col = colisiones[0]
    assert (col["grupo"], col["nombre"]) == ("operacion", "Cafetería")
    # El reporte trae lo EXISTENTE vs lo que la semilla habría puesto (verificable).
    assert col["existente"]["tipo_flujo"] == "ingreso"
    assert col["semilla"]["tipo_flujo"] == "egreso"
    # Corrida limpia posterior: 0 nuevos, todas las llaves ya existen.
    insertados2, colisiones2 = await seed_rubros_reporte(db)
    assert insertados2 == 0 and len(colisiones2) == 42


async def test_seed_configuracion_idempotente(db):
    await seed_configuracion(db)
    await seed_configuracion(db)
    total = await Configuracion.find_all().count()
    assert total == 4  # + PERIODICIDAD_IVA (CR IVA período configurable)


# ── C3: semilla de reglas de clasificación (GO Kimi PLAN-I 9.3) ──


# Rubros de egreso a los que apuntan las reglas de comercios/conceptos genéricos
# (todos existen en SEMILLA_RUBROS y en prod). Guarda: una regla de egreso jamás
# apunta a un rubro fuera de esta taxonomía.
_RUBROS_EGRESO_REGLAS = {
    "Gastos bancarios",
    "Impuestos",
    "Gastos financieros",
    "Gastos notariales",
    "Transporte/peajes/combustible/parqueo",
    "Tecnología y software",
    "Cafetería",
    "Mercado y aseo",
    "Marketing y publicidad",
}


def test_semilla_reglas_sin_pii_y_origen_manual():
    # Kimi §3 (Ley 1581): SOLO patrones genéricos/comercios — NUNCA nombres de
    # personas. Se dejan fuera socios, 'Débito' pelado y reversas/FX (revisión
    # manual). Las genéricas de ingreso (PRD M7 / MODELO §C3) quedan CONGELADAS.
    ingreso = [r for r in SEMILLA_REGLAS if r["tipo_flujo"] == "ingreso"]
    assert [(r["patron"], r["rubro_nombre"]) for r in ingreso] == [
        ("Abono", "Recaudo de cartera"),
        ("Recibido de", "Recaudo de cartera"),
    ]
    for r in SEMILLA_REGLAS:
        assert r["origen"] == "manual"  # curaduría, no aprendizaje (Kimi §3)
        assert r["tipo_flujo"] in ("ingreso", "egreso")
        assert len(r["patron"]) >= 3  # PATRON_MIN — sin match-all
    # toda regla de egreso apunta a un rubro de gasto conocido (no a un socio, no a
    # un rubro inventado): guarda estructural contra clasificar mal dinero.
    for r in SEMILLA_REGLAS:
        if r["tipo_flujo"] == "egreso":
            assert r["rubro_nombre"] in _RUBROS_EGRESO_REGLAS


async def test_seed_reglas_idempotente_y_resuelve_rubro(db):
    from app.domain.regla_clasificacion import ReglaClasificacion

    await seed_rubros(db)  # siembra la taxonomía (incl. 'Recaudo de cartera')
    total = len(SEMILLA_REGLAS)
    n1, col1 = await seed_reglas_reporte(db)
    n2, col2 = await seed_reglas_reporte(db)
    assert n1 == total and col1 == []
    assert n2 == 0 and len(col2) == total  # 2ª corrida: no duplica
    reglas = await ReglaClasificacion.find_all().to_list()
    assert len(reglas) == total
    assert all(r.activa for r in reglas)
    # las de ingreso resuelven a 'Recaudo de cartera'; las de egreso, a un rubro
    # de gasto (rubro_id no nulo, resuelto sin fail-loud).
    recaudo = await Rubro.find_one(Rubro.nombre == "Recaudo de cartera")
    ingreso = [r for r in reglas if r.tipo_flujo.value == "ingreso"]
    assert ingreso and all(r.rubro_id == recaudo.id for r in ingreso)


async def test_seed_reglas_fail_loud_sin_rubro_destino(db):
    # Kimi §3: si el rubro destino del mapeo no existe → error, no silencio.
    with pytest.raises(LookupError):
        await seed_reglas_reporte(db)  # sin sembrar rubros primero
