# backend/tests/cfo/reporte/test_router_reporte.py
"""Task 4 · POST /api/v1/cfo/reporte-inversionistas — doble barrera (router
condicional + guard 404) y RBAC `export:reportes`.

Patrón de auth REUSADO de tests/cfo/agente/test_router.py: create_app() real +
mongomock para auth/audit + login real para obtener el token (dependency_overrides
no sirve aquí — ver docstring de ese archivo). `reunir_datos` queda
monkeypatcheado (fake, sin tocar servicios/LLM reales); `render_rumbo` también se
monkeypatchea por test para separar el caso feliz del fail-soft."""

import httpx
import pytest
import pytest_asyncio
from app.audit.service import configure_audit, reset_audit
from app.auth import passwords, repository
from app.auth.models import User
from app.auth.roles import Role
from app.cfo.reporte.modelos import Cifra, DatosReporte, RumboSerie, Seccion
from app.config import get_settings
from app.main import create_app
from mongomock_motor import AsyncMongoMockClient

PWD = "clave-larga-1234"

DATOS_FAKE = DatosReporte(
    periodo="2026-09",
    resumen_ejecutivo="Todo en orden.",
    secciones=[Seccion(titulo="Caja", cifras=[Cifra(etiqueta="Hoy", valor="$1")])],
    rumbo=RumboSerie(
        meses=["2026-09", "2026-10"],
        caja=["100", "200"],
        caja_minima="50",
        caja_atencion="80",
    ),
)

DATOS_SIN_RUMBO = DatosReporte(
    periodo="2026-09",
    resumen_ejecutivo="Sin proyección disponible.",
    secciones=[Seccion(titulo="Caja", cifras=[Cifra(etiqueta="Hoy", valor="$1")])],
    rumbo=None,
)


async def _fake_reunir_datos(periodo: str | None, *, actor_id: str) -> DatosReporte:
    return DATOS_FAKE


# PNG 1x1 válido (python-docx exige que sea un formato reconocible al armar el
# .docx) — no se compara contenido, solo que armar_docx lo acepte sin reventar.
_PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
    b"\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb0\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _fake_render_rumbo_ok(rumbo: RumboSerie) -> bytes:
    return _PNG_1X1


def _fake_render_rumbo_revienta(rumbo: RumboSerie) -> bytes:
    raise RuntimeError("matplotlib se cayó")


@pytest_asyncio.fixture
async def api(monkeypatch):
    """App con el router cfo MONTADO (CFO_ENABLED=true) + un usuario por rol.
    `reunir_datos` y `render_rumbo` quedan monkeypatcheados (ningún test aquí
    toca un LLM, servicios reales, o matplotlib de verdad)."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    monkeypatch.setenv("COOKIE_SECURE", "False")
    monkeypatch.setenv("CFO_ENABLED", "true")
    monkeypatch.delenv("RUN_SCHEDULER", raising=False)
    get_settings.cache_clear()

    import app.cfo.router as cfo_router_module

    monkeypatch.setattr(cfo_router_module, "reunir_datos", _fake_reunir_datos)
    monkeypatch.setattr(cfo_router_module, "render_rumbo", _fake_render_rumbo_ok)

    app = create_app()
    c = AsyncMongoMockClient()
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


async def _token(ac, email) -> str:
    r = await ac.post("/api/v1/auth/login", json={"email": email, "password": PWD})
    assert r.status_code == 200
    return r.json()["access_token"]


DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


@pytest.mark.parametrize(
    "email", ["fin@roddos.com", "dir@roddos.com", "admin@roddos.com"]
)
async def test_responde_200_con_docx_para_rol_autorizado(api, email):
    tok = await _token(api, email)
    h = {"Authorization": f"Bearer {tok}"}
    r = await api.post("/api/v1/cfo/reporte-inversionistas", json={}, headers=h)
    assert r.status_code == 200
    assert r.headers["content-type"] == DOCX_MEDIA_TYPE
    assert (
        r.headers["content-disposition"]
        == 'attachment; filename="reporte-inversionistas-2026-09.docx"'
    )
    assert len(r.content) > 0


async def test_acepta_periodo_explicito(api):
    tok = await _token(api, "admin@roddos.com")
    h = {"Authorization": f"Bearer {tok}"}
    r = await api.post(
        "/api/v1/cfo/reporte-inversionistas",
        json={"periodo": "2026-01"},
        headers=h,
    )
    assert r.status_code == 200
    assert len(r.content) > 0


async def test_rol_consulta_no_autorizado_403(api):
    tok = await _token(api, "consulta@roddos.com")
    h = {"Authorization": f"Bearer {tok}"}
    r = await api.post("/api/v1/cfo/reporte-inversionistas", json={}, headers=h)
    assert r.status_code == 403


async def test_sin_token_es_401(api):
    r = await api.post("/api/v1/cfo/reporte-inversionistas", json={})
    assert r.status_code == 401


async def test_body_extra_forbidden_422(api):
    # Regla 3 (Pydantic strict=True/extra=forbid): campo no declarado se rechaza.
    tok = await _token(api, "admin@roddos.com")
    h = {"Authorization": f"Bearer {tok}"}
    r = await api.post(
        "/api/v1/cfo/reporte-inversionistas",
        json={"campo_extra": 1},
        headers=h,
    )
    assert r.status_code == 422


async def test_periodo_malformado_422(api):
    # Fix 1: `periodo` viaja al filename (Content-Disposition) y a
    # motos_para_evitar_umbral(mes_inicio=periodo) — un valor malformado debe
    # rechazarse en Pydantic (422), antes de llegar al handler.
    tok = await _token(api, "admin@roddos.com")
    h = {"Authorization": f"Bearer {tok}"}
    r = await api.post(
        "/api/v1/cfo/reporte-inversionistas",
        json={"periodo": "2026-9"},
        headers=h,
    )
    assert r.status_code == 422


async def test_guard_defensivo_404_si_flag_se_apaga_en_runtime(api, monkeypatch):
    tok = await _token(api, "admin@roddos.com")
    h = {"Authorization": f"Bearer {tok}"}
    monkeypatch.setenv("CFO_ENABLED", "false")
    r = await api.post("/api/v1/cfo/reporte-inversionistas", json={}, headers=h)
    assert r.status_code == 404
    assert r.json()["detail"] == "No encontrado."


async def test_ruta_ausente_si_flag_apagado_al_construir_la_app(monkeypatch):
    # Barrera 1: con el flag apagado desde el arranque, create_app() NUNCA monta el
    # router — la ruta no existe (404 genérico de FastAPI, no el guard del handler).
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    monkeypatch.delenv("CFO_ENABLED", raising=False)
    get_settings.cache_clear()

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post("/api/v1/cfo/reporte-inversionistas", json={})
    assert r.status_code == 404
    assert r.json() == {"detail": "Not Found"}
    get_settings.cache_clear()


async def test_fail_soft_grafica_no_tumba_el_reporte(api, monkeypatch):
    # render_rumbo lanza ⇒ el reporte sale igual (sin gráfica), no revienta.
    import app.cfo.router as cfo_router_module

    monkeypatch.setattr(
        cfo_router_module, "render_rumbo", _fake_render_rumbo_revienta
    )
    tok = await _token(api, "admin@roddos.com")
    h = {"Authorization": f"Bearer {tok}"}
    r = await api.post("/api/v1/cfo/reporte-inversionistas", json={}, headers=h)
    assert r.status_code == 200
    assert r.headers["content-type"] == DOCX_MEDIA_TYPE
    assert len(r.content) > 0


async def test_sin_rumbo_no_intenta_renderizar_grafica(api, monkeypatch):
    # datos.rumbo is None ⇒ ni siquiera se llama render_rumbo; reporte sale igual.
    import app.cfo.router as cfo_router_module

    llamado = {"veces": 0}

    def _render_no_debe_llamarse(rumbo):
        llamado["veces"] += 1
        raise AssertionError("render_rumbo no debía llamarse sin rumbo")

    async def _sin_rumbo(periodo, *, actor_id):
        return DATOS_SIN_RUMBO

    monkeypatch.setattr(cfo_router_module, "reunir_datos", _sin_rumbo)
    monkeypatch.setattr(cfo_router_module, "render_rumbo", _render_no_debe_llamarse)

    tok = await _token(api, "admin@roddos.com")
    h = {"Authorization": f"Bearer {tok}"}
    r = await api.post("/api/v1/cfo/reporte-inversionistas", json={}, headers=h)
    assert r.status_code == 200
    assert llamado["veces"] == 0
    assert len(r.content) > 0
