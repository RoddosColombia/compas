# backend/tests/test_e1_loader.py
"""E1 · P3 — loader de anclaje (única capa Mongo). `cargar_anclas` traduce el estado del
ciclo (MesControl) al régimen de anclaje del plan §1 y arma los insumos que consume
`ejecucion.service.anclar` (dict `anclas`, `RubroInfo`, `neutros_ids`) reusando las
queries ya probadas — sin reinventar agregaciones.

    CERRADO       → 'cerrado'      : ejecutado por rubro + ingreso_real (sin neutros)
    EN_EJECUCION  → 'en_ejecucion' : ejecutado + definido (Regla A la resuelve anclar)
    otro estado con definido vigente > 0 → 'presupuesto' : solo el definido
    sin MesControl / futuro sin definido → OMITIDO (motor intacto)
"""

from decimal import Decimal

import pytest
import pytest_asyncio
from app.domain import DOMAIN_DOCUMENTS
from app.domain.bancos import Banco
from app.domain.mes_control import EstadoMes, MesControl
from app.domain.presupuesto import PresupuestoLinea
from app.domain.rubro import Rubro, RubroGrupo, TipoFlujo
from app.domain.transaccion import Transaccion
from app.proyeccion.ejecucion.lectura import RubroInfo
from app.proyeccion.ejecucion.loader import (
    cargar_anclas,
    cargar_completitud_mes_en_curso,
)
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient

_MES_INICIO = (2026, 7)
_HORIZONTE = 6  # 2026-07 .. 2026-12


@pytest_asyncio.fixture
async def db():
    c = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
    yield c


async def _mes(mes7: str, estado: EstadoMes) -> MesControl:
    mc = MesControl(mes=f"{mes7}-01", saldo_inicial_caja=Decimal("0"), estado=estado)
    await mc.insert()
    return mc


async def _rubro(grupo, nombre, flujo, codigo=None, es_sistema=False) -> Rubro:
    r = Rubro(
        grupo=grupo,
        nombre=nombre,
        tipo_flujo=flujo,
        orden=1,
        codigo=codigo,
        es_sistema=es_sistema,
    )
    await r.insert()
    return r


async def _tx(mc, rubro, valor, flujo, ordinal) -> None:
    await Transaccion(
        fecha=f"{mc.mes[:7]}-10",
        descripcion="mov",
        valor=Decimal(valor),
        tipo_flujo=flujo,
        rubro_id=rubro.id,
        mes_id=mc.id,
        banco=Banco.GLOBAL66,
        id_banco=f"REF-{mc.mes}-{ordinal}|1",
    ).insert()


async def _linea(mc, rubro, definido) -> None:
    await PresupuestoLinea(
        mes_id=mc.id,
        rubro_id=rubro.id,
        monto_sugerido=Decimal("0"),
        prom_3m=Decimal("0"),
        tendencia_mes=Decimal("0"),
        crec_pct=Decimal("0"),
        historia_incompleta=False,
        monto_definido=definido,
        vigente=True,
    ).insert()


@pytest_asyncio.fixture
async def escenario(db):
    """Un horizonte con los cuatro regímenes representados."""
    gasto_a = await _rubro(RubroGrupo.OPERACION, "Arriendos", TipoFlujo.EGRESO, "2010")
    gasto_b = await _rubro(
        RubroGrupo.COSTO_PRODUCTO, "Producto", TipoFlujo.EGRESO, "1010"
    )
    recaudo = await _rubro(
        RubroGrupo.INGRESOS_OPERATIVOS, "Recaudo de cartera", TipoFlujo.INGRESO, "0110"
    )
    neutro = await _rubro(
        RubroGrupo.OTROS, "Reversas y devoluciones", TipoFlujo.INGRESO
    )

    # 2026-07 CERRADO: egreso real + ingreso (recaudo real + una reversa neutra)
    jul = await _mes("2026-07", EstadoMes.CERRADO)
    await _tx(jul, gasto_a, "5000", TipoFlujo.EGRESO, 1)
    await _tx(jul, recaudo, "8000", TipoFlujo.INGRESO, 2)
    await _tx(jul, neutro, "300", TipoFlujo.INGRESO, 3)  # neutro → excluido

    # 2026-08 EN_EJECUCION: ejecutado real + presupuesto definido (Regla A)
    ago = await _mes("2026-08", EstadoMes.EN_EJECUCION)
    await _tx(ago, gasto_a, "2000", TipoFlujo.EGRESO, 1)
    await _linea(ago, gasto_a, Decimal("6000"))
    await _linea(ago, gasto_b, Decimal("3000"))

    # 2026-09 PROPUESTO con definido vigente > 0 → régimen 'presupuesto'
    sep = await _mes("2026-09", EstadoMes.PROPUESTO)
    await _linea(sep, gasto_a, Decimal("4000"))

    # 2026-10 SUGERIDO con línea SIN definido (monto_definido None) → omitido
    oct_ = await _mes("2026-10", EstadoMes.SUGERIDO)
    await _linea(oct_, gasto_a, None)

    # 2026-11 y 2026-12 SIN MesControl → omitidos
    return {
        "gasto_a": gasto_a,
        "gasto_b": gasto_b,
        "recaudo": recaudo,
        "neutro": neutro,
    }


@pytest.mark.asyncio
async def test_mes_cerrado_ancla_ejecutado_e_ingreso_real_sin_neutros(escenario):
    anclas, _, _ = await cargar_anclas(_MES_INICIO, _HORIZONTE)
    a = anclas["2026-07"]
    assert a.estado == "cerrado"
    assert a.ejecutado_por_rubro_id == {str(escenario["gasto_a"].id): Decimal("5000")}
    assert a.definido_por_rubro_id == {}
    assert a.ingreso_real == Decimal("8000")  # 8000 recaudo, la reversa (300) excluida


@pytest.mark.asyncio
async def test_mes_en_ejecucion_ancla_ejecutado_y_definido(escenario):
    anclas, _, _ = await cargar_anclas(_MES_INICIO, _HORIZONTE)
    a = anclas["2026-08"]
    assert a.estado == "en_ejecucion"
    assert a.ejecutado_por_rubro_id == {str(escenario["gasto_a"].id): Decimal("2000")}
    assert a.definido_por_rubro_id == {
        str(escenario["gasto_a"].id): Decimal("6000"),
        str(escenario["gasto_b"].id): Decimal("3000"),
    }
    assert a.ingreso_real is None


@pytest.mark.asyncio
async def test_mes_propuesto_con_definido_es_regimen_presupuesto(escenario):
    """El régimen 'presupuesto' (plan §1) NO está dormido: un mes propuesto con
    monto_definido > 0 se ancla con el definido, sin ejecutado ni ingreso."""
    anclas, _, _ = await cargar_anclas(_MES_INICIO, _HORIZONTE)
    a = anclas["2026-09"]
    assert a.estado == "presupuesto"
    assert a.definido_por_rubro_id == {str(escenario["gasto_a"].id): Decimal("4000")}
    assert a.ejecutado_por_rubro_id == {}
    assert a.ingreso_real is None


@pytest.mark.asyncio
async def test_futuro_sin_definido_y_sin_mescontrol_se_omiten(escenario):
    anclas, _, _ = await cargar_anclas(_MES_INICIO, _HORIZONTE)
    assert set(anclas) == {"2026-07", "2026-08", "2026-09"}
    assert "2026-10" not in anclas  # SUGERIDO sin definido
    assert "2026-11" not in anclas and "2026-12" not in anclas  # sin MesControl


@pytest.mark.asyncio
async def test_rubros_info_y_neutros_ids_se_arman(escenario):
    _, rubros, neutros_ids = await cargar_anclas(_MES_INICIO, _HORIZONTE)
    assert all(isinstance(r, RubroInfo) for r in rubros)
    nombres = {r.nombre for r in rubros}
    assert {"Arriendos", "Producto", "Recaudo de cartera"} <= nombres
    # el único neutro presente es la reversa
    assert neutros_ids == {str(escenario["neutro"].id)}


# ── P4 · PASO 0 (higiene A2): un mes con tx a rubro de SISTEMA "sucio" (es_sistema, no
# clasificable, no neutro) no se ancla — cae al motor. Alcance por-mes. ──


@pytest.mark.asyncio
async def test_paso0_mes_con_rubro_sistema_sucio_no_se_ancla(db):
    gasto = await _rubro(RubroGrupo.OPERACION, "Arriendos", TipoFlujo.EGRESO, "2010")
    sucio = await _rubro(
        RubroGrupo.OTROS, "Sistema no clasificable", TipoFlujo.EGRESO, es_sistema=True
    )
    jul = await _mes("2026-07", EstadoMes.CERRADO)
    await _tx(jul, gasto, "5000", TipoFlujo.EGRESO, 1)
    await _tx(
        jul, sucio, "9", TipoFlujo.EGRESO, 2
    )  # 1 tx sucia → PASO 0 excluye el mes
    anclas, _, _ = await cargar_anclas(_MES_INICIO, _HORIZONTE)
    assert "2026-07" not in anclas  # cae al motor


@pytest.mark.asyncio
async def test_paso0_clasificables_y_neutros_no_disparan(db):
    gasto = await _rubro(RubroGrupo.OPERACION, "Arriendos", TipoFlujo.EGRESO, "2010")
    porclas = await _rubro(
        RubroGrupo.OTROS, "Por clasificar", TipoFlujo.EGRESO, es_sistema=True
    )
    neutro = await _rubro(
        RubroGrupo.OTROS, "Reversas y devoluciones", TipoFlujo.INGRESO, es_sistema=True
    )
    jul = await _mes("2026-07", EstadoMes.CERRADO)
    await _tx(jul, gasto, "5000", TipoFlujo.EGRESO, 1)
    await _tx(jul, porclas, "3", TipoFlujo.EGRESO, 2)  # clasificable → NO dispara
    await _tx(jul, neutro, "7", TipoFlujo.INGRESO, 3)  # neutro → NO dispara
    anclas, _, _ = await cargar_anclas(_MES_INICIO, _HORIZONTE)
    assert "2026-07" in anclas  # el mes se ancla igual


@pytest.mark.asyncio
async def test_cerrado_trae_definido_para_la_marca(db):
    gasto = await _rubro(RubroGrupo.OPERACION, "Arriendos", TipoFlujo.EGRESO, "2010")
    jul = await _mes("2026-07", EstadoMes.CERRADO)
    await _tx(jul, gasto, "5000", TipoFlujo.EGRESO, 1)
    await _linea(jul, gasto, Decimal("12000"))  # presupuesto definido del mes cerrado
    anclas, _, _ = await cargar_anclas(_MES_INICIO, _HORIZONTE)
    # el loader trae el definido también para cerrado (alimenta la marca B10)
    assert anclas["2026-07"].definido_por_rubro_id == {str(gasto.id): Decimal("12000")}


@pytest.mark.asyncio
async def test_completitud_mes_en_curso_toma_la_fecha_maxima(db):
    """P5/B13: para el mes EN_EJECUCION, completitud = fecha máxima de tx + fórmula, y
    (P6-b) el ejecutado real a la fecha vs el proyectado (Σ presupuesto definido)."""
    ago = await _mes("2026-08", EstadoMes.EN_EJECUCION)
    gasto = await _rubro(RubroGrupo.OPERACION, "Arriendos", TipoFlujo.EGRESO, "2010")
    for f in ("2026-08-03", "2026-08-06", "2026-08-01"):
        await Transaccion(
            fecha=f,
            descripcion="x",
            valor=Decimal("10"),  # Σ egresos reales = 30
            tipo_flujo=TipoFlujo.EGRESO,
            rubro_id=gasto.id,
            mes_id=ago.id,
            banco=Banco.GLOBAL66,
            id_banco=f"REF-{f}|1",
        ).insert()
    await _linea(ago, gasto, Decimal("100"))  # presupuesto definido = 100

    comp = await cargar_completitud_mes_en_curso((2026, 8), 1)
    assert comp == {
        "mes": "2026-08",
        "cargado_hasta": "2026-08-06",
        "dia": 6,
        "formula": "ejecutado + max(0, definido - ejecutado) por concepto",
        "ejecutado": "30.00",  # P6-b: Σ egresos reales del mes a la fecha
        "proyectado": "100.00",  # P6-b: Σ presupuesto definido del mes
    }


@pytest.mark.asyncio
async def test_completitud_none_sin_mes_en_ejecucion(db):
    await _mes("2026-08", EstadoMes.CERRADO)
    assert await cargar_completitud_mes_en_curso((2026, 8), 1) is None
