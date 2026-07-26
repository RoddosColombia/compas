# backend/tests/test_cartera_previa.py
"""PR-1 "Fidelidad de caja" — CarteraPreviaRecaudo: seed/carga idempotente de la serie
semanal REAL de los 111 créditos preexistentes + lectura como dicts para el motor.

mongomock basta aquí (no depende del índice único parcial del Sprint 1 ni de
transacciones multi-documento); el test de unicidad real va con @requires_real_mongo.
"""

from decimal import Decimal

import pytest_asyncio
from app.audit.service import configure_audit, reset_audit
from app.domain import DOMAIN_DOCUMENTS
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient


@pytest_asyncio.fixture
async def db():
    c = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
    configure_audit(c, "compas_test")
    yield c
    reset_audit()


async def test_cargar_y_obtener_series(db):
    from app.cartera_previa import service

    filas = [
        {"semana_global": 1, "recaudo": Decimal("759600"), "n_activos": 5},
        {"semana_global": 2, "recaudo": Decimal("1009500"), "n_activos": 7},
    ]
    n = await service.cargar_serie(filas, usuario_id="u1")
    assert n == 2
    recaudo, activos = await service.obtener_series()
    assert recaudo == {1: Decimal("759600"), 2: Decimal("1009500")}
    assert activos == {1: 5, 2: 7}


async def test_cargar_serie_es_idempotente(db):
    from app.cartera_previa import service
    from app.domain.cartera_previa import CarteraPreviaRecaudo

    await service.cargar_serie(
        [{"semana_global": 1, "recaudo": Decimal("759600"), "n_activos": 5}],
        usuario_id="u1",
    )
    # segunda carga corrige el valor de la misma semana: PISA, no duplica.
    await service.cargar_serie(
        [{"semana_global": 1, "recaudo": Decimal("800000"), "n_activos": 6}],
        usuario_id="u1",
    )
    total = await CarteraPreviaRecaudo.find_all().count()
    assert total == 1
    recaudo, activos = await service.obtener_series()
    assert recaudo == {1: Decimal("800000")}
    assert activos == {1: 6}


async def test_obtener_series_vacia_es_dicts_vacios(db):
    from app.cartera_previa import service

    recaudo, activos = await service.obtener_series()
    assert recaudo == {}
    assert activos == {}


async def test_proyectar_vigente_incluye_cartera_previa(db):
    """El servicio de proyección alimenta la serie previa al motor: con 0 motos nuevas,
    TODO el recaudo de crédito de julio viene de la cartera previa."""
    from app.cartera_previa import service as cp
    from app.domain.modelo_moto import ModeloMoto
    from app.domain.parametros_proyeccion import ParametrosProyeccion
    from app.proyeccion import service as proy

    await ParametrosProyeccion(
        vigente_desde="2026-07-01",
        caja_inicial=Decimal("0"),
        caja_minima=Decimal("0"),
        motos_base=0,  # sin colocación nueva → recaudo nuevo = 0
        crec_pct_mensual=Decimal("0"),
        horizonte_meses=2,
        adelanto_auteco=Decimal("0"),
        plazo_auteco_dias=0,
        base_auteco_dias=0,
        tasa_auteco=Decimal("0"),
        gastos_fijos=Decimal("0"),
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
    ).insert()
    await ModeloMoto(
        nombre="Raider",
        costo_auteco=Decimal("0"),
        precio_venta_con_iva=Decimal("0"),
        cuota_inicial=Decimal("0"),
        cuota_semanal=Decimal("100"),
        plazo_semanas=6,
        matricula=Decimal("0"),
        participacion_mix=Decimal("1"),
        orden=0,
    ).insert()
    # jul-2026 cobra semanas 18-22; pongo la previa en w22 (recaudo 1000, 3 activos).
    await cp.cargar_serie(
        [{"semana_global": 22, "recaudo": Decimal("1000"), "n_activos": 3}],
        usuario_id="u1",
    )
    res = await proy.proyectar_vigente(
        escenario="base", mes_inicio=(2026, 7), horizonte_meses=2
    )
    assert res["meses"][0]["recaudo_credito"] == "1000.00"  # todo de la previa
    assert res["meses"][0]["cartera"] == 3  # activos previos en w_ref=22


async def test_seed_cartera_previa_idempotente_y_completo(db):
    from app.cartera_previa import service
    from app.domain.seed import seed_cartera_previa

    n1 = await seed_cartera_previa(db["compas_test"])
    assert n1 == 97  # las 97 semanas del artefacto
    n2 = await seed_cartera_previa(db["compas_test"])
    assert n2 == 0  # idempotente: segunda corrida no inserta nada
    recaudo, activos = await service.obtener_series()
    assert len(recaudo) == 97
    assert recaudo[1] == Decimal("759600")  # w1 = mié 2026-03-04
    assert recaudo[97] == Decimal("209900")  # w97 (~ene-2028)
    # total exacto de la serie (verificado al peso contra el artefacto)
    assert sum(recaudo.values()) == Decimal("1095640900")
