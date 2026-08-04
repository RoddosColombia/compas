# backend/tests/test_fixl_rampa.py
"""FIX-L — rampa de unidades por mes editable en Supuestos.

`ParametrosProyeccion.rampa_unidades` (YYYY-MM → unidades) se mapea al `rampa` nativo
del motor (`colocacion_mensual`): los primeros meses (prefijo contiguo desde mes_inicio)
toman los valores dados; el primer mes post-rampa REINICIA en motos_base y de ahí crece
encadenado (semántica del motor, sin tocarlo). Aditivo: {} → comportamiento de hoy.
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
from app.domain.parametros_proyeccion import ParametrosProyeccion
from app.main import create_app
from app.proyeccion.motor import colocacion_mensual
from app.proyeccion.service import _rampa_a_lista
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient
from pydantic import ValidationError

PWD = "clave-larga-1234"


# ── _rampa_a_lista: dict (YYYY-MM) → lista posicional desde mes_inicio ──


def test_rampa_un_mes():
    assert _rampa_a_lista({"2026-08": 75}, (2026, 8)) == [75]


def test_rampa_prefijo_contiguo():
    r = {"2026-08": 75, "2026-09": 80, "2026-10": 90}
    assert _rampa_a_lista(r, (2026, 8)) == [75, 80, 90]


def test_rampa_corta_en_el_primer_mes_ausente():
    # 2026-09 falta → la rampa es solo agosto; el motor reinicia en septiembre.
    assert _rampa_a_lista({"2026-08": 75, "2026-10": 90}, (2026, 8)) == [75]


def test_rampa_cruza_anio():
    r = {"2026-12": 100, "2027-01": 110}
    assert _rampa_a_lista(r, (2026, 12)) == [100, 110]


def test_rampa_vacia_es_none():
    assert _rampa_a_lista({}, (2026, 8)) is None


def test_rampa_sin_prefijo_desde_inicio_es_none():
    # El único mes con dato no es el mes de inicio → no hay prefijo → None (sin rampa).
    assert _rampa_a_lista({"2026-10": 90}, (2026, 8)) is None


# ── semántica del motor: rampa + reinicio (colocacion_mensual, sin tocar el motor) ──


def test_colocacion_con_rampa_reinicia_en_motos_base():
    # agosto=75 (rampa); septiembre REINICIA en motos_base=50, luego crece 1% encadenado
    serie = colocacion_mensual(50, Decimal("0.01"), 4, rampa=[75])
    assert serie == [75, 50, 51, 52]


def test_colocacion_sin_rampa_identica_a_hoy():
    # default (rampa None) → cadena desde motos_base, sin deriva.
    assert colocacion_mensual(50, Decimal("0.01"), 4, rampa=None) == [50, 51, 52, 53]


# ── dominio: campo aditivo + validación ──


def _params(**over):
    base = dict(
        vigente_desde="2026-08-01",
        caja_inicial=Decimal("0"),
        caja_minima=Decimal("0"),
        motos_base=50,
        crec_pct_mensual=Decimal("0.01"),
        horizonte_meses=12,
        adelanto_auteco=Decimal("0"),
        plazo_auteco_dias=30,
        base_auteco_dias=30,
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
    )
    base.update(over)
    return ParametrosProyeccion(**base)


def test_rampa_default_vacia():
    assert _params().rampa_unidades == {}


def test_rampa_acepta_serie():
    p = _params(rampa_unidades={"2026-08": 75, "2026-09": 80})
    assert p.rampa_unidades == {"2026-08": 75, "2026-09": 80}


def test_rampa_rechaza_mes_invalido():
    with pytest.raises(ValidationError):
        _params(rampa_unidades={"2026-13": 75})


def test_rampa_rechaza_unidades_negativas():
    with pytest.raises(ValidationError):
        _params(rampa_unidades={"2026-08": -5})


# ── endpoint PUT/GET /parametros-proyeccion (round-trip + 422) ──


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
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _body(**over):
    b = {
        "vigente_desde": "2026-08-01",
        "caja_inicial": "24000000",
        "caja_minima": "125000000",
        "motos_base": 50,
        "crec_pct_mensual": "0.01",
        "horizonte_meses": 12,
        "adelanto_auteco": "970000",
        "plazo_auteco_dias": 150,
        "base_auteco_dias": 90,
        "tasa_auteco": "0.016",
        "gastos_fijos": "125000000",
        "gps_moto": "33201",
        "costo_moto_nueva": "692005",
        "deuda": "28527080",
        "tasa_deuda": "0.011",
        "mes_inicio_deuda": 2,
        "meses_deuda": 14,
        "pct_mora": "0.03",
        "pct_recuperacion": "0.40",
        "pct_default": "0.03",
        "pct_provision": "0.02",
    }
    b.update(over)
    return b


async def test_put_guarda_rampa_y_get_la_devuelve(api):
    h = await _token(api)
    r = await api.put(
        "/api/v1/parametros-proyeccion",
        json=_body(rampa_unidades={"2026-08": 75, "2026-09": 80}),
        headers=h,
    )
    assert r.status_code == 200
    g = await api.get("/api/v1/parametros-proyeccion", headers=h)
    assert g.json()["rampa_unidades"] == {"2026-08": 75, "2026-09": 80}


async def test_put_sin_rampa_default_vacia(api):
    h = await _token(api)
    await api.put("/api/v1/parametros-proyeccion", json=_body(), headers=h)
    g = await api.get("/api/v1/parametros-proyeccion", headers=h)
    assert g.json()["rampa_unidades"] == {}


async def test_put_rampa_mes_invalido_422(api):
    h = await _token(api)
    r = await api.put(
        "/api/v1/parametros-proyeccion",
        json=_body(rampa_unidades={"2026-13": 75}),
        headers=h,
    )
    assert r.status_code == 422
