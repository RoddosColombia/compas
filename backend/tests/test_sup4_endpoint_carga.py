# backend/tests/test_sup4_endpoint_carga.py
"""SUP-4 — POST /api/v1/cartera-previa/cargar-cronograma: la carga semanal.

El CEO sube el cronograma (lunes) y COMPAS hace TODO lo demás: agrega la serie de la
cartera ya originada, la persiste, y deja la rampa del MES EN CURSO en el remanente
hacia la meta. Devuelve un resumen con lo que cambió — nada de tocar la base a mano.

Reglas: RBAC `proyeccion:gestionar` (mueve la proyección), fail-closed ante un archivo
vacío o de encabezados desconocidos (jamás pisar la cartera real en silencio) y
auditoría con los eventos que ya existen.
"""

from datetime import date
from io import BytesIO

import httpx
import pytest
import pytest_asyncio
from app.audit.service import configure_audit, reset_audit
from app.auth import passwords, repository
from app.auth.models import User
from app.auth.roles import Role
from app.config import get_settings
from app.domain import DOMAIN_DOCUMENTS
from app.domain.cartera_previa import CarteraPreviaRecaudo
from app.domain.parametros_proyeccion import ParametrosProyeccion
from app.main import create_app
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient
from openpyxl import Workbook

PWD = "clave-larga-1234"
URL = "/api/v1/cartera-previa/cargar-cronograma"
ENCABEZADOS = [
    "Crédito",
    "Cuota #",
    "Fecha Programada",
    "Monto Total",
    "Capital",
    "Interés",
    "Pagado",
    "Saldo",
    "Estado",
    "Mora",
]


def _xlsx(filas: list[list], encabezados: list[str] | None = None) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(["Generado"])
    ws.append(encabezados or ENCABEZADOS)
    for f in filas:
        ws.append(f)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _cuota(credito="LB-1", n=1, fecha="2026-09-02", monto=179900, estado="pendiente"):
    return [credito, n, fecha, monto, 150000, 29900, 0, monto, estado, 0]


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
    for correo, rol in [
        ("consulta@roddos.com", Role.consulta),
        ("fin@roddos.com", Role.financiero),
    ]:
        await repository.create_user(
            User(email=correo, password_hash=passwords.hash_password(PWD), rol=rol)
        )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    repository.reset_auth()
    reset_audit()
    get_settings.cache_clear()


async def _token(ac, email="fin@roddos.com") -> dict:
    r = await ac.post("/api/v1/auth/login", json={"email": email, "password": PWD})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _cargar(ac, h, contenido: bytes, nombre="cronogramas.xlsx"):
    return await ac.post(
        URL,
        files={
            "archivo": (
                nombre,
                contenido,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        headers=h,
    )


async def _params(**over):
    base = dict(
        vigente_desde="2026-08-01",
        caja_inicial="100000000",
        caja_minima="125000000",
        motos_base=70,
        crec_pct_mensual="0.10",
        horizonte_meses=24,
        adelanto_auteco="0",
        plazo_auteco_dias=150,
        base_auteco_dias=90,
        tasa_auteco="0.016",
        gastos_fijos="208000000",
        gps_moto="33201",
        costo_moto_nueva="691500",
        deuda="25000000",
        tasa_deuda="0.1157",
        mes_inicio_deuda=2,
        meses_deuda=14,
        pct_mora="0.08",
        pct_recuperacion="0.65",
        pct_default="0.05",
        pct_provision="0.02",
    )
    base.update(over)
    return base


@pytest.mark.asyncio
async def test_carga_feliz_persiste_la_serie_y_devuelve_el_resumen(api):
    h = await _token(api)
    r = await _cargar(
        api,
        h,
        _xlsx(
            [
                # desembolso en JULIO: desde P5 (no-solape) un crédito originado dentro
                # del mes en curso sale de la serie — lo proyecta el motor.
                _cuota(credito="LB-1", n=0, fecha="2026-07-05", estado="pagada"),
                _cuota(credito="LB-1", n=1, fecha="2026-09-02"),
                _cuota(credito="LB-2", n=1, fecha="2026-09-02", monto=210000),
            ]
        ),
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["creditos"] == 2
    assert d["semanas"] == 1
    assert d["recaudo_futuro"] == "389900.00"
    assert d["colocaciones_por_mes"] == {"2026-07": 1}
    # y quedó persistida para el motor
    filas = await CarteraPreviaRecaudo.find_all().to_list()
    assert len(filas) == 1
    assert filas[0].n_activos == 2


@pytest.mark.asyncio
async def test_la_segunda_carga_reemplaza_la_serie_no_la_duplica(api):
    """Idempotente: cargar el lunes siguiente deja la foto nueva, no la suma."""
    h = await _token(api)
    await _cargar(api, h, _xlsx([_cuota(fecha="2026-09-02")]))
    await _cargar(api, h, _xlsx([_cuota(fecha="2026-10-07", monto=200000)]))
    filas = await CarteraPreviaRecaudo.find_all().to_list()
    assert len(filas) == 1  # la semana vieja se fue con la foto vieja
    assert filas[0].recaudo.compare(__import__("decimal").Decimal("200000")) == 0


@pytest.mark.asyncio
async def test_carga_vacia_no_pisa_la_cartera(api):
    """Fail-closed: un archivo sin cuotas útiles dejaría la cartera en cero — se
    rechaza (422) y la serie anterior queda intacta."""
    h = await _token(api)
    await _cargar(api, h, _xlsx([_cuota(fecha="2026-09-02")]))
    antes = len(await CarteraPreviaRecaudo.find_all().to_list())
    r = await _cargar(api, h, _xlsx([]))
    assert r.status_code == 422
    assert "vac" in r.json()["detail"].lower()
    assert len(await CarteraPreviaRecaudo.find_all().to_list()) == antes


@pytest.mark.asyncio
async def test_encabezados_desconocidos_es_422_listando(api):
    h = await _token(api)
    r = await _cargar(api, h, _xlsx([_cuota()], encabezados=["A", "B", "C"]))
    assert r.status_code == 422
    assert "encabezados" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_extension_no_xlsx_es_422(api):
    h = await _token(api)
    r = await _cargar(api, h, b"no soy excel", nombre="cronograma.csv")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_rbac_solo_proyeccion_gestionar(api):
    h = await _token(api, "consulta@roddos.com")
    r = await _cargar(api, h, _xlsx([_cuota()]))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_actualiza_la_rampa_del_mes_en_curso(api):
    """P4 (CEO 2026-08-23) — **la carga semanal NO toca la meta del mes.**

    SUPERSEDE la automatización de SUP-4, que dejaba la rampa del mes en curso en el
    remanente (meta − colocadas) y con eso PISABA el dato del CEO: agosto-2026 estaba en
    70 por decisión suya y la carga lo bajó a 35. La meta es dato del CEO; la carga solo
    devuelve los insumos del termómetro (meta vigente vs. colocadas)."""
    h = await _token(api)
    assert (
        await api.put("/api/v1/parametros-proyeccion", json=await _params(), headers=h)
    ).status_code == 200

    hoy = date.today()
    mes = f"{hoy.year:04d}-{hoy.month:02d}"
    # el CEO fijó la meta del mes en 70 (a mano, en Supuestos)
    p0 = await ParametrosProyeccion.find_one(
        ParametrosProyeccion.vigente_desde == "2026-08-01"
    )
    assert p0 is not None
    p0.rampa_unidades = {**p0.rampa_unidades, mes: 70}
    await p0.save()

    filas = [
        _cuota(credito=f"LB-{i}", n=0, fecha=f"{mes}-05", estado="pagada")
        for i in range(35)
    ]
    # un crédito PREEXISTENTE (originado antes del mes en curso) para que la serie no
    # quede vacía: los 35 del mes en curso salen por el no-solape de P5.
    filas.append(_cuota(credito="LB-VIEJO", n=0, fecha="2026-06-03", estado="pagada"))
    filas.append(_cuota(credito="LB-VIEJO", n=1, fecha="2027-01-06"))
    r = await _cargar(api, h, _xlsx(filas))
    assert r.status_code == 200, r.text
    d = r.json()
    # los insumos del termómetro: la meta del CEO, intacta, y lo colocado
    assert d["meta_del_mes"] == 70
    assert d["colocadas_del_mes"] == 35
    assert d["mes_en_curso"] == mes

    # y la META del CEO NO se tocó
    p = await ParametrosProyeccion.find_one(
        ParametrosProyeccion.vigente_desde == "2026-08-01"
    )
    assert p.rampa_unidades[mes] == 70
