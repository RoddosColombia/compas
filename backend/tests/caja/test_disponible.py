# backend/tests/caja/test_disponible.py
"""GET /api/v1/caja/disponible — 'la cerca' de tesorería del IVA (Task 4).

Fakea `conciliacion` + `mes_en_ejecucion` + `proyectar_vigente` (los tres, importados
por nombre en `app.caja.router`) para no montar un mes/config real: esta prueba cubre
la COMPOSICIÓN del endpoint (bruto/reserva_iva/neto/sin_dato), no la conciliación ni
el motor de proyección (que ya tienen su propia suite).

RBAC: `dashboard:leer` = TODOS los roles (mismo permiso que `GET /caja/diaria`, la
otra ruta de LECTURA de `caja/router.py` — NO se inventó un permiso nuevo). Como
ningún rol del sistema carece de `dashboard:leer`, el "403 sin permiso" se prueba
denegándolo temporalmente vía `monkeypatch.setitem` sobre el config único de permisos
(así se verifica que el endpoint SÍ está detrás de `require_permission`, sin
inventar un rol que no existe)."""

from datetime import datetime

import httpx
import pytest_asyncio
from app.audit.service import configure_audit, reset_audit
from app.auth import passwords, repository
from app.auth.models import User
from app.auth.permissions import PERMISSIONS
from app.auth.roles import Role
from app.caja import router as caja_router
from app.cierre.service import CierreError
from app.config import get_settings
from app.core.time import BOGOTA
from app.proyeccion.service import ProyeccionError
from mongomock_motor import AsyncMongoMockClient

PWD = "clave-larga-1234"
_HOY = datetime(2026, 7, 15, 9, 0, tzinfo=BOGOTA)  # ancla determinista para las pruebas


@pytest_asyncio.fixture
async def api(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    monkeypatch.setenv("COOKIE_SECURE", "False")
    monkeypatch.delenv("RUN_SCHEDULER", raising=False)
    get_settings.cache_clear()

    from app.main import create_app

    app = create_app()
    c = AsyncMongoMockClient(tz_aware=True)
    repository.configure_auth(c, "compas_test")
    configure_audit(c, "compas_test")
    for correo, rol in [
        ("consulta@roddos.com", Role.consulta),
        ("fin@roddos.com", Role.financiero),
        ("dir@roddos.com", Role.directivo),
        ("admin@roddos.com", Role.admin),
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
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _fake_mes_en_ejecucion(mes):
    async def _f():
        return mes

    return _f


def _fake_conciliacion(con):
    async def _f(mes):
        return con

    return _f


def _fake_conciliacion_error(err: CierreError):
    async def _f(mes):
        raise err

    return _f


def _fake_proyectar(fondo_provision, *, capturado: dict | None = None):
    async def _f(*, escenario, mes_inicio, horizonte_meses, caja_inicial_override=None):
        if capturado is not None:
            capturado["escenario"] = escenario
            capturado["mes_inicio"] = mes_inicio
            capturado["horizonte_meses"] = horizonte_meses
        return {"fondo_provision": fondo_provision}

    return _f


def _fake_proyectar_error():
    async def _f(*, escenario, mes_inicio, horizonte_meses, caja_inicial_override=None):
        raise ProyeccionError("sin config vigente", 409)

    return _f


# ── RBAC ──


async def test_sin_token_401(api):
    r = await api.get("/api/v1/caja/disponible")
    assert r.status_code == 401


async def test_sin_permiso_403(api, monkeypatch):
    # dashboard:leer es de TODOS los roles hoy: se le quita temporalmente a
    # 'consulta' para verificar que el endpoint SÍ está detrás de require_permission.
    monkeypatch.setitem(
        PERMISSIONS,
        "dashboard:leer",
        frozenset({Role.financiero, Role.directivo, Role.admin}),
    )
    h = await _token(api, "consulta@roddos.com")
    r = await api.get("/api/v1/caja/disponible", headers=h)
    assert r.status_code == 403


async def test_todos_los_roles_leen_hoy(api, monkeypatch):
    # Sin mes en ejecución -> respuesta en cero, pero todo rol pasa el RBAC actual.
    monkeypatch.setattr(caja_router, "mes_en_ejecucion", _fake_mes_en_ejecucion(None))
    for email in (
        "consulta@roddos.com",
        "fin@roddos.com",
        "dir@roddos.com",
        "admin@roddos.com",
    ):
        h = await _token(api, email)
        r = await api.get("/api/v1/caja/disponible", headers=h)
        assert r.status_code == 200, email


# ── sin mes en ejecución ──


async def test_sin_mes_en_ejecucion_da_ceros(api, monkeypatch):
    monkeypatch.setattr(caja_router, "mes_en_ejecucion", _fake_mes_en_ejecucion(None))
    h = await _token(api)
    r = await api.get("/api/v1/caja/disponible", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body == {
        "bruto": "0",
        "reserva_iva": "0",
        "neto": "0",
        "fecha_corte": None,
        "sin_dato": [],
    }


# ── composición bruto/reserva/neto ──


async def test_bruto_reserva_neto_desde_fondo_del_mes(api, monkeypatch):
    monkeypatch.setattr(caja_router, "now_bogota", lambda: _HOY)
    monkeypatch.setattr(
        caja_router, "mes_en_ejecucion", _fake_mes_en_ejecucion("2026-07-01")
    )
    monkeypatch.setattr(
        caja_router,
        "conciliacion",
        _fake_conciliacion(
            {
                "mes": "2026-07",
                "consolidado_reportado": "15000000.00",
                "sin_dato": ["bbva"],
            }
        ),
    )
    capturado: dict = {}
    monkeypatch.setattr(
        caja_router,
        "proyectar_vigente",
        _fake_proyectar(
            [
                {
                    "mes": "2026-06",
                    "reserva": "500000.00",
                    "pago": "0",
                    "saldo": "500000.00",
                },
                {
                    "mes": "2026-07",
                    "reserva": "500000.00",
                    "pago": "0",
                    "saldo": "3000000.00",
                },
            ],
            capturado=capturado,
        ),
    )
    h = await _token(api)
    r = await api.get("/api/v1/caja/disponible", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["bruto"] == "15000000.00"
    assert body["reserva_iva"] == "3000000.00"
    assert body["neto"] == "12000000.00"
    assert body["sin_dato"] == ["bbva"]
    # el fondo se ancla en el mes CALENDARIO de hoy (no en el mes en ejecución del
    # ciclo, que podría no coincidir) -- mismo patrón que el tool CFO del Task 3.
    assert capturado["mes_inicio"] == (2026, 7)
    assert capturado["horizonte_meses"] is None
    assert capturado["escenario"] == "base"


async def test_neto_puede_ser_negativo(api, monkeypatch):
    monkeypatch.setattr(caja_router, "now_bogota", lambda: _HOY)
    monkeypatch.setattr(
        caja_router, "mes_en_ejecucion", _fake_mes_en_ejecucion("2026-07-01")
    )
    monkeypatch.setattr(
        caja_router,
        "conciliacion",
        _fake_conciliacion(
            {
                "mes": "2026-07",
                "consolidado_reportado": "1000000.00",
                "sin_dato": [],
            }
        ),
    )
    monkeypatch.setattr(
        caja_router,
        "proyectar_vigente",
        _fake_proyectar(
            [
                {
                    "mes": "2026-07",
                    "reserva": "0",
                    "pago": "0",
                    "saldo": "4000000.00",
                },
            ]
        ),
    )
    h = await _token(api)
    r = await api.get("/api/v1/caja/disponible", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["neto"] == "-3000000.00"


async def test_sin_fondo_o_proyeccion_error_reserva_es_cero(api, monkeypatch):
    monkeypatch.setattr(caja_router, "now_bogota", lambda: _HOY)
    monkeypatch.setattr(
        caja_router, "mes_en_ejecucion", _fake_mes_en_ejecucion("2026-07-01")
    )
    monkeypatch.setattr(
        caja_router,
        "conciliacion",
        _fake_conciliacion(
            {
                "mes": "2026-07",
                "consolidado_reportado": "9000000.00",
                "sin_dato": [],
            }
        ),
    )
    monkeypatch.setattr(caja_router, "proyectar_vigente", _fake_proyectar_error())
    h = await _token(api)
    r = await api.get("/api/v1/caja/disponible", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["reserva_iva"] == "0"
    assert body["neto"] == body["bruto"] == "9000000.00"


async def test_sin_entrada_del_mes_en_el_fondo_reserva_es_cero(api, monkeypatch):
    monkeypatch.setattr(caja_router, "now_bogota", lambda: _HOY)
    monkeypatch.setattr(
        caja_router, "mes_en_ejecucion", _fake_mes_en_ejecucion("2026-07-01")
    )
    monkeypatch.setattr(
        caja_router,
        "conciliacion",
        _fake_conciliacion(
            {
                "mes": "2026-07",
                "consolidado_reportado": "9000000.00",
                "sin_dato": [],
            }
        ),
    )
    # fondo_provision existe pero sin entrada para el mes de HOY (2026-07).
    monkeypatch.setattr(
        caja_router,
        "proyectar_vigente",
        _fake_proyectar(
            [{"mes": "2026-08", "reserva": "1", "pago": "0", "saldo": "1"}]
        ),
    )
    h = await _token(api)
    r = await api.get("/api/v1/caja/disponible", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["reserva_iva"] == "0"
    assert body["neto"] == body["bruto"] == "9000000.00"


# ── conciliación en error (CierreError) ──


async def test_conciliacion_error_propaga_status(api, monkeypatch):
    monkeypatch.setattr(
        caja_router, "mes_en_ejecucion", _fake_mes_en_ejecucion("2026-07-01")
    )
    monkeypatch.setattr(
        caja_router,
        "conciliacion",
        _fake_conciliacion_error(CierreError("mes no en ejecución", 409)),
    )
    h = await _token(api)
    r = await api.get("/api/v1/caja/disponible", headers=h)
    assert r.status_code == 409
