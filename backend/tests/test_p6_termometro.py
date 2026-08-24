# backend/tests/test_p6_termometro.py
"""P6 del ciclo mensual — EL TERMÓMETRO DE DESVIACIÓN.

Contrato: `docs/COMPAS_Ciclo_Mensual.md` §«Paso 2 · Durante el mes».

    "El mes en curso son proyecciones basadas en los objetivos planteados y lo que
    podemos hacer es revisar la realidad para ver qué desviación o qué precisión
    estamos logrando con los objetivos planteados." (CEO 2026-08-23)

La curva muestra el OBJETIVO (P4/P5). Este bloque muestra la REALIDAD al lado, para
responder otra pregunta: **¿qué tan buenos son nuestros objetivos?** Tres lecturas:

    colocaciones →  llevamos 35 de la meta de 60 motos
    ingreso      →  recaudado real a la fecha vs. el proyectado del mes
    gasto        →  ejecutado real a la fecha vs. el presupuesto del mes

**No toca la proyección.** El candado del contrato: con o sin datos reales cargados, la
serie del motor es idéntica. Si la realidad alimentara el motor volveríamos al error que
P4 eliminó (la realidad pisando el objetivo).

Honestidad de las cifras: lo real es "a la fecha" (día N de M) y lo proyectado es del
MES completo — el payload dice el día y los días del mes para que la pantalla no pueda
presentar una desviación engañosa a mitad de mes. El ingreso real usa el MISMO criterio
que E1 aplica a los meses cerrados (`metas_ingreso.ingreso_real`: Σ INGRESO sin rubros
neutros), así que el termómetro y el cierre nunca dirán cifras distintas.
"""

from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from app.audit.service import configure_audit, reset_audit
from app.auth import passwords, repository
from app.auth.models import User
from app.auth.roles import Role
from app.config import get_settings
from app.domain import DOMAIN_DOCUMENTS
from app.domain.cartera_previa import ColocacionMes
from app.domain.mes_control import EstadoMes, MesControl, SaldoBanco
from app.domain.rubro import Rubro, TipoFlujo
from app.domain.transaccion import Banco, Transaccion
from app.main import create_app
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient

PWD = "clave-larga-1234"
CIERRE_JULIO = Decimal("665715578")
_Q = "horizonte_meses=12&mes_inicio=2026-08"


@pytest_asyncio.fixture
async def api(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    monkeypatch.setenv("COOKIE_SECURE", "False")
    monkeypatch.delenv("RUN_SCHEDULER", raising=False)
    get_settings.cache_clear()

    app = create_app()
    c = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
    repository.configure_auth(c, "compas_test")
    configure_audit(c, "compas_test")
    await repository.create_user(
        User(
            email="fin@roddos.com",
            password_hash=passwords.hash_password(PWD),
            rol=Role.financiero,
        )
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    repository.reset_auth()
    reset_audit()
    get_settings.cache_clear()


async def _token(ac) -> dict:
    r = await ac.post(
        "/api/v1/auth/login", json={"email": "fin@roddos.com", "password": PWD}
    )
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _params():
    return {
        "vigente_desde": "2026-08-01",
        "caja_inicial": "665715578",
        "caja_minima": "30000000",
        "motos_base": 60,
        "crec_pct_mensual": "0.10",
        "horizonte_meses": 12,
        "adelanto_auteco": "0",
        "plazo_auteco_dias": 150,
        "base_auteco_dias": 90,
        "tasa_auteco": "0.016",
        "gastos_fijos": "208000000",
        "gps_moto": "33201",
        "costo_moto_nueva": "691500",
        "deuda": "25000000",
        "tasa_deuda": "0.1157",
        "mes_inicio_deuda": 2,
        "meses_deuda": 14,
        "pct_mora": "0.08",
        "pct_recuperacion": "0.65",
        "pct_default": "0.03",
        "pct_provision": "0.02",
        "rampa_unidades": {"2026-08": 60},  # la META del mes (dato del CEO)
    }


async def _setup(ac) -> dict:
    h = await _token(ac)
    assert (
        await ac.post(
            "/api/v1/modelos-moto",
            json={
                "nombre": "Raider",
                "costo_auteco": "6720557",
                "precio_venta_con_iva": "8000000",
                "cuota_inicial": "1620000",
                "cuota_semanal": "184900",
                "plazo_semanas": 78,
                "matricula": "500000",
                "participacion_mix": "1",
            },
            headers=h,
        )
    ).status_code == 201
    assert (
        await ac.put("/api/v1/parametros-proyeccion", json=_params(), headers=h)
    ).status_code == 200
    return h


async def _abrir_agosto() -> MesControl:
    """Taxonomía + julio cerrado + agosto EN EJECUCIÓN (la foto de PROD)."""
    plan = [
        ("0110", "ingresos_operativos", TipoFlujo.INGRESO),  # recaudo semanal
        ("0120", "ingresos_operativos", TipoFlujo.INGRESO),  # cuota inicial
        ("1010", "costo_producto", TipoFlujo.EGRESO),
        ("1020", "costo_producto", TipoFlujo.EGRESO),
        ("1030", "costo_producto", TipoFlujo.EGRESO),
        ("4010", "deudas_obligaciones", TipoFlujo.EGRESO),
        ("4020", "deudas_obligaciones", TipoFlujo.EGRESO),
        ("4030", "deudas_obligaciones", TipoFlujo.EGRESO),
        ("4040", "deudas_obligaciones", TipoFlujo.EGRESO),
        ("4050", "deudas_obligaciones", TipoFlujo.EGRESO),
        ("4070", "deudas_obligaciones", TipoFlujo.EGRESO),
        ("5060", "otros", TipoFlujo.EGRESO),
        ("2010", "operacion", TipoFlujo.EGRESO),  # arriendos (gasto fijo)
    ]
    for i, (cod, grupo, flujo) in enumerate(plan):
        await Rubro(
            grupo=grupo, nombre=f"Rubro {cod}", codigo=cod, tipo_flujo=flujo, orden=i
        ).insert()
    await MesControl(
        mes="2026-07-01",
        estado=EstadoMes.CERRADO,
        saldo_inicial_caja=Decimal("814796138.93"),
        saldos_banco=[
            SaldoBanco(banco="global66", saldo=CIERRE_JULIO, fecha_reporte="2026-07-31")
        ],
    ).insert()
    return await MesControl(
        mes="2026-08-01",
        estado=EstadoMes.EN_EJECUCION,
        saldo_inicial_caja=CIERRE_JULIO,
        saldos_banco=[
            SaldoBanco(banco="global66", saldo=CIERRE_JULIO, fecha_reporte="2026-08-01")
        ],
    ).insert()


async def _tx(mc: MesControl, codigo: str, valor: str, fecha: str, flujo: TipoFlujo):
    r = await Rubro.find_one(Rubro.codigo == codigo)
    assert r is not None
    await Transaccion(
        fecha=fecha,
        descripcion=f"mov {codigo}",
        valor=Decimal(valor),
        tipo_flujo=flujo,
        rubro_id=r.id,
        mes_id=mc.id,
        banco=Banco.GLOBAL66,
        id_banco=f"MAN-{codigo}-{fecha}-{valor}",
    ).insert()


# ───────────────────────── las tres lecturas ─────────────────────────


@pytest.mark.asyncio
async def test_el_termometro_trae_las_colocaciones_reales_contra_la_meta(api):
    h = await _setup(api)
    await _abrir_agosto()
    await ColocacionMes(mes="2026-08", unidades=35).insert()
    d = (await api.get(f"/api/v1/proyeccion?{_Q}", headers=h)).json()
    mc = d["mes_en_curso"]
    assert mc["colocaciones_meta"] == 60  # lo que proyecta la curva
    assert mc["colocaciones_reales"] == 35  # lo que de verdad se colocó


@pytest.mark.asyncio
async def test_sin_colocaciones_cargadas_no_se_inventa_un_cero(api):
    """Regla 7: "no hay dato" y "cero motos" son cosas distintas."""
    h = await _setup(api)
    await _abrir_agosto()
    d = (await api.get(f"/api/v1/proyeccion?{_Q}", headers=h)).json()
    assert d["mes_en_curso"]["colocaciones_reales"] is None
    assert d["mes_en_curso"]["colocaciones_meta"] == 60


@pytest.mark.asyncio
async def test_el_termometro_trae_el_ingreso_real_contra_el_proyectado(api):
    h = await _setup(api)
    mc = await _abrir_agosto()
    await _tx(mc, "0120", "59480000", "2026-08-05", TipoFlujo.INGRESO)  # iniciales
    await _tx(mc, "0110", "39944130", "2026-08-12", TipoFlujo.INGRESO)  # semanales
    d = (await api.get(f"/api/v1/proyeccion?{_Q}", headers=h)).json()
    t = d["mes_en_curso"]
    assert t["ingreso_real"] == "99424130.00"  # el mismo criterio que usa el cierre
    # y el proyectado del mes es el `neto` de la fila (lo que muestra la curva)
    assert t["ingreso_proyectado"] == d["meses"][0]["neto"]


@pytest.mark.asyncio
async def test_el_ingreso_real_viene_discriminado_inicial_vs_semanal(api):
    """Para leer la desviación donde importa: si falla la colocación o el recaudo."""
    h = await _setup(api)
    mc = await _abrir_agosto()
    await _tx(mc, "0120", "59480000", "2026-08-05", TipoFlujo.INGRESO)
    await _tx(mc, "0110", "39944130", "2026-08-12", TipoFlujo.INGRESO)
    t = (await api.get(f"/api/v1/proyeccion?{_Q}", headers=h)).json()["mes_en_curso"]
    assert t["ingreso_real_inicial"] == "59480000.00"
    assert t["ingreso_real_semanal"] == "39944130.00"
    # el proyectado, discriminado igual (columnas de la propia tabla)
    assert t["ingreso_proyectado_inicial"] is not None
    assert t["ingreso_proyectado_semanal"] is not None


@pytest.mark.asyncio
async def test_el_gasto_sigue_comparando_ejecutado_contra_presupuesto(api):
    """La lectura que ya existía (B13), ahora con la fórmula de P4."""
    h = await _setup(api)
    mc = await _abrir_agosto()
    await _tx(mc, "2010", "150673128.72", "2026-08-12", TipoFlujo.EGRESO)
    t = (await api.get(f"/api/v1/proyeccion?{_Q}", headers=h)).json()["mes_en_curso"]
    assert t["ejecutado"] == "150673128.72"
    assert t["dia"] == 12
    assert t["dias_del_mes"] == 31  # el payload dice el día Y los días del mes


@pytest.mark.asyncio
async def test_la_formula_declarada_es_la_de_P4_no_la_regla_A(api):
    """La pantalla muestra cómo se armó el mes. Con P4 es el presupuesto, ya no
    'ejecutado + lo que resta' — si el texto quedara viejo, mentiría."""
    h = await _setup(api)
    await _abrir_agosto()
    t = (await api.get(f"/api/v1/proyeccion?{_Q}", headers=h)).json()["mes_en_curso"]
    assert "presupuesto" in t["formula"].lower()
    assert "max(" not in t["formula"]
    assert "ejecutado +" not in t["formula"]


# ───────────────────────── el candado: no toca la curva ─────────────────────────


@pytest.mark.asyncio
async def test_el_termometro_NO_cambia_la_proyeccion(api):
    """El candado del Paso 2: cargar realidad no mueve ni un peso de la curva. Si la
    moviera, volveríamos al error que P4 eliminó."""
    h = await _setup(api)
    mc = await _abrir_agosto()
    antes = (await api.get(f"/api/v1/proyeccion?{_Q}", headers=h)).json()

    await ColocacionMes(mes="2026-08", unidades=35).insert()
    await _tx(mc, "0120", "59480000", "2026-08-05", TipoFlujo.INGRESO)
    await _tx(mc, "0110", "39944130", "2026-08-12", TipoFlujo.INGRESO)
    despues = (await api.get(f"/api/v1/proyeccion?{_Q}", headers=h)).json()

    assert antes["meses"] == despues["meses"]
    assert antes["piso_caja"] == despues["piso_caja"]
    assert antes["arranque"] == despues["arranque"]
    # y el termómetro sí cambió
    assert despues["mes_en_curso"]["ingreso_real"] == "99424130.00"
    assert despues["mes_en_curso"]["colocaciones_reales"] == 35
