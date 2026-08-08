# backend/tests/test_e1_loader_realmongo.py
"""E1 · P3 — loader de anclaje contra Mongo REAL.

La clasificación del loader se cubre en mongomock (`test_e1_loader.py`); esta capa
verifica lo único sensible a mongomock-vs-real: la agregación `$group` de
`_egresos_por_rubro` (Σ egresos por rubro) que alimenta el ejecutado del mes cerrado.
@requires_real_mongo; CI lo provee (local con COMPAS_TEST_MONGO_URI)."""

import os
from decimal import Decimal

import pytest
import pytest_asyncio
from app.domain import DOMAIN_DOCUMENTS
from app.domain.bancos import Banco
from app.domain.mes_control import EstadoMes, MesControl
from app.domain.presupuesto import PresupuestoLinea
from app.domain.rubro import Rubro, RubroGrupo, TipoFlujo
from app.domain.transaccion import Transaccion
from app.proyeccion.ejecucion.loader import (
    cargar_anclas,
    cargar_completitud_mes_en_curso,
)
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient


@pytest.mark.requires_real_mongo
class TestLoaderReal:
    @pytest_asyncio.fixture
    async def db(self):
        uri = os.environ.get("COMPAS_TEST_MONGO_URI")
        if not uri:
            pytest.skip("COMPAS_TEST_MONGO_URI no configurado")
        client = AsyncIOMotorClient(uri, tz_aware=True)
        dbname = "compas_test_e1_loader"
        await client.drop_database(dbname)
        await init_beanie(database=client[dbname], document_models=DOMAIN_DOCUMENTS)
        yield client
        await client.drop_database(dbname)

    @pytest.mark.asyncio
    async def test_cerrado_agrega_egresos_y_en_ejecucion_lee_definido(self, db):
        gasto = await Rubro(
            grupo=RubroGrupo.OPERACION,
            nombre="Arriendos",
            tipo_flujo=TipoFlujo.EGRESO,
            orden=1,
            codigo="2010",
        ).insert()
        recaudo = await Rubro(
            grupo=RubroGrupo.INGRESOS_OPERATIVOS,
            nombre="Recaudo de cartera",
            tipo_flujo=TipoFlujo.INGRESO,
            orden=2,
            codigo="0110",
        ).insert()

        jul = await MesControl(
            mes="2026-07-01",
            saldo_inicial_caja=Decimal("0"),
            estado=EstadoMes.CERRADO,
        ).insert()
        # dos egresos del MISMO rubro → el $group real debe sumarlos (5000)
        for i, v in enumerate(("3000", "2000")):
            await Transaccion(
                fecha="2026-07-10",
                descripcion="egreso",
                valor=Decimal(v),
                tipo_flujo=TipoFlujo.EGRESO,
                rubro_id=gasto.id,
                mes_id=jul.id,
                banco=Banco.GLOBAL66,
                id_banco=f"REF-E-{i}|1",
            ).insert()
        await Transaccion(
            fecha="2026-07-11",
            descripcion="ingreso",
            valor=Decimal("8000"),
            tipo_flujo=TipoFlujo.INGRESO,
            rubro_id=recaudo.id,
            mes_id=jul.id,
            banco=Banco.GLOBAL66,
            id_banco="REF-I|1",
        ).insert()

        ago = await MesControl(
            mes="2026-08-01",
            saldo_inicial_caja=Decimal("0"),
            estado=EstadoMes.EN_EJECUCION,
        ).insert()
        await PresupuestoLinea(
            mes_id=ago.id,
            rubro_id=gasto.id,
            monto_sugerido=Decimal("0"),
            prom_3m=Decimal("0"),
            tendencia_mes=Decimal("0"),
            crec_pct=Decimal("0"),
            historia_incompleta=False,
            monto_definido=Decimal("6000"),
            vigente=True,
        ).insert()

        anclas, _rubros, _neutros = await cargar_anclas((2026, 7), 2)

        assert anclas["2026-07"].estado == "cerrado"
        # el $group real sumó los dos egresos del rubro
        assert anclas["2026-07"].ejecutado_por_rubro_id == {
            str(gasto.id): Decimal("5000")
        }
        assert anclas["2026-07"].ingreso_real == Decimal("8000")
        assert anclas["2026-08"].estado == "en_ejecucion"
        assert anclas["2026-08"].definido_por_rubro_id == {
            str(gasto.id): Decimal("6000")
        }

    @pytest.mark.asyncio
    async def test_paso0_rubro_sistema_sucio_excluye_el_mes_real(self, db):
        """P4/A2 contra Mongo real: la query de PASO 0 (find In sobre rubro_id) detecta
        la tx a un rubro de sistema no clasificable → el mes cae al motor."""
        gasto = await Rubro(
            grupo=RubroGrupo.OPERACION,
            nombre="Arriendos",
            tipo_flujo=TipoFlujo.EGRESO,
            orden=1,
            codigo="2010",
        ).insert()
        sucio = await Rubro(
            grupo=RubroGrupo.OTROS,
            nombre="Sistema no clasificable",
            tipo_flujo=TipoFlujo.EGRESO,
            orden=2,
            es_sistema=True,
        ).insert()
        jul = await MesControl(
            mes="2026-07-01", saldo_inicial_caja=Decimal("0"), estado=EstadoMes.CERRADO
        ).insert()
        await Transaccion(
            fecha="2026-07-10",
            descripcion="ok",
            valor=Decimal("5000"),
            tipo_flujo=TipoFlujo.EGRESO,
            rubro_id=gasto.id,
            mes_id=jul.id,
            banco=Banco.GLOBAL66,
            id_banco="REF-OK|1",
        ).insert()
        await Transaccion(
            fecha="2026-07-11",
            descripcion="sucia",
            valor=Decimal("9"),
            tipo_flujo=TipoFlujo.EGRESO,
            rubro_id=sucio.id,
            mes_id=jul.id,
            banco=Banco.GLOBAL66,
            id_banco="REF-SUCIA|1",
        ).insert()

        anclas, _rubros, _neutros = await cargar_anclas((2026, 7), 1)
        assert "2026-07" not in anclas  # PASO 0 lo sacó (cae al motor)

    @pytest.mark.asyncio
    async def test_completitud_fecha_maxima_real(self, db):
        """P5/B13 contra Mongo real: sort(-fecha).limit(1) devuelve la fecha máxima de
        transacción del mes en ejecución (fecha ISO ordena cronológicamente)."""
        rubro = await Rubro(
            grupo=RubroGrupo.OPERACION,
            nombre="Arriendos",
            tipo_flujo=TipoFlujo.EGRESO,
            orden=1,
            codigo="2010",
        ).insert()
        ago = await MesControl(
            mes="2026-08-01",
            saldo_inicial_caja=Decimal("0"),
            estado=EstadoMes.EN_EJECUCION,
        ).insert()
        for f in ("2026-08-02", "2026-08-09", "2026-08-05"):
            await Transaccion(
                fecha=f,
                descripcion="x",
                valor=Decimal("7"),  # Σ egresos reales = 21
                tipo_flujo=TipoFlujo.EGRESO,
                rubro_id=rubro.id,
                mes_id=ago.id,
                banco=Banco.GLOBAL66,
                id_banco=f"REF-{f}|1",
            ).insert()
        await PresupuestoLinea(
            mes_id=ago.id,
            rubro_id=rubro.id,
            monto_sugerido=Decimal("0"),
            prom_3m=Decimal("0"),
            tendencia_mes=Decimal("0"),
            crec_pct=Decimal("0"),
            historia_incompleta=False,
            monto_definido=Decimal("50"),
            vigente=True,
        ).insert()

        comp = await cargar_completitud_mes_en_curso((2026, 8), 1)
        assert comp["cargado_hasta"] == "2026-08-09"
        assert comp["dia"] == 9
        # P6-b: el $group real suma los egresos (21) y el definido (50)
        assert comp["ejecutado"] == "21.00"
        assert comp["proyectado"] == "50.00"
