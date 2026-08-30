# backend/tests/test_rf_f9_plan_de_cuentas.py
"""RF-F9 · Fundacional §2 — «Plan de cuentas completo: código contable y clase
obligatorios al crear categoría».

Contexto (mapa):
  · `Rubro.codigo` (str | None, jerárquico p. ej. '2070') y `Rubro.tipo` (Fijo/
    Variable) hoy son OPCIONALES en creación (rubros/service.py:85 y router:29).
  · La semilla real cubre 33/34 rubros con código; el único sin código es
    'Ajuste de conciliación' (`es_sistema=True`, línea 220 de domain/rubro.py) —
    legítimo, no forma parte del plan de cuentas del negocio.
  · Motor NO ve rubros; endurecer la creación es capa de dominio pura.

RF-F9 hace obligatorios `codigo` (no vacío, ≤8 chars) y `tipo` (Fijo|Variable)
para RUBROS NO DE SISTEMA. La regla es «al CREAR»: rubros existentes sin código
NO se tocan (nunca reescribimos histórico — regla 4 en espíritu). Reactivar un
rubro previo tampoco los exige (edición ≠ creación).
"""

import httpx
import pytest
import pytest_asyncio
from app.audit.service import configure_audit, reset_audit
from app.auth import passwords, repository
from app.auth.models import User
from app.auth.roles import Role
from app.config import get_settings
from app.domain import DOMAIN_DOCUMENTS
from app.domain.rubro import Rubro, RubroGrupo, TipoFlujo, TipoRubro
from app.main import create_app
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient

PWD = "clave-larga-1234"


# ─────────────────────────── servicio (unit) ───────────────────────────


@pytest_asyncio.fixture
async def db():
    c = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
    repository.configure_auth(c, "compas_test")
    configure_audit(c, "compas_test")
    yield c
    repository.reset_auth()
    reset_audit()


@pytest.mark.asyncio
async def test_rff9_crear_sin_codigo_es_422(db):
    """Sin `codigo` → 422 al crear (era None → ahora requerido)."""
    from app.rubros.service import RubrosError, crear_rubro

    with pytest.raises(RubrosError) as ex:
        await crear_rubro(
            grupo=RubroGrupo.OPERACION,
            nombre="Categoría de prueba",
            tipo_flujo=TipoFlujo.EGRESO,
            codigo=None,  # ← violación de RF-F9
            tipo=TipoRubro.VARIABLE,
            usuario_id="u1",
        )
    assert ex.value.status == 422
    assert "codigo" in ex.value.detalle.lower()


@pytest.mark.asyncio
async def test_rff9_crear_con_codigo_vacio_es_422(db):
    """Codigo vacío o solo espacios NO cuenta como código contable."""
    from app.rubros.service import RubrosError, crear_rubro

    for codigo_malo in ("", "   "):
        with pytest.raises(RubrosError) as ex:
            await crear_rubro(
                grupo=RubroGrupo.OPERACION,
                nombre=f"Cat {codigo_malo!r}",
                tipo_flujo=TipoFlujo.EGRESO,
                codigo=codigo_malo,
                tipo=TipoRubro.VARIABLE,
                usuario_id="u1",
            )
        assert ex.value.status == 422
        assert "codigo" in ex.value.detalle.lower()


@pytest.mark.asyncio
async def test_rff9_crear_sin_tipo_es_422(db):
    """Sin `tipo` (Fijo/Variable) → 422 al crear."""
    from app.rubros.service import RubrosError, crear_rubro

    with pytest.raises(RubrosError) as ex:
        await crear_rubro(
            grupo=RubroGrupo.OPERACION,
            nombre="Sin clase",
            tipo_flujo=TipoFlujo.EGRESO,
            codigo="2900",
            tipo=None,  # ← violación de RF-F9
            usuario_id="u1",
        )
    assert ex.value.status == 422
    assert "tipo" in ex.value.detalle.lower() or "clase" in ex.value.detalle.lower()


@pytest.mark.asyncio
async def test_rff9_crear_con_ambos_obligatorios_ok(db):
    """Con `codigo` no vacío + `tipo` → crea + queda persistido con ambos."""
    from app.rubros.service import crear_rubro

    rubro = await crear_rubro(
        grupo=RubroGrupo.OPERACION,
        nombre="Categoría plena",
        tipo_flujo=TipoFlujo.EGRESO,
        codigo="2900",
        tipo=TipoRubro.VARIABLE,
        usuario_id="u1",
    )
    assert rubro.codigo == "2900"
    assert rubro.tipo == TipoRubro.VARIABLE
    persistido = await Rubro.get(rubro.id)
    assert persistido is not None
    assert persistido.codigo == "2900"
    assert persistido.tipo == TipoRubro.VARIABLE


@pytest.mark.asyncio
async def test_rff9_editar_no_exige_llenar_los_nuevos_obligatorios(db):
    """Un rubro EXISTENTE creado antes de RF-F9 puede seguir editándose sin
    llenar codigo/tipo (RF-F9 es «al CREAR», no «para todo cambio»)."""
    from app.rubros.service import editar_rubro

    # Nace directo en Mongo (bypass del service) con codigo=None — simula un
    # rubro previo a RF-F9. La creación via service ya lo rechazaría; aquí
    # probamos la ruta de EDICIÓN.
    r = await Rubro(
        grupo=RubroGrupo.OPERACION,
        nombre="Legacy sin código",
        tipo_flujo=TipoFlujo.EGRESO,
        codigo=None,
        tipo=None,
        orden=999,
    ).insert()
    editado = await editar_rubro(
        rubro_id=str(r.id), usuario_id="u1", nombre="Legacy renombrado"
    )
    # El PATCH pasa: sigue sin código y no lo pide.
    assert editado.nombre == "Legacy renombrado"
    assert editado.codigo is None


@pytest.mark.asyncio
async def test_rff9_semilla_sistema_ajuste_de_conciliacion_intacta():
    """La semilla no viola RF-F9: solo `Ajuste de conciliación` no tiene código,
    y ES DE SISTEMA (legítimo). Guardián contra reformas accidentales."""
    from app.domain.rubro import SEMILLA_RUBROS

    sin_codigo = [r for r in SEMILLA_RUBROS if r["codigo"] is None]
    # Único legítimo sin código: rubro de sistema.
    assert all(r["es_sistema"] for r in sin_codigo)
    assert {r["nombre"] for r in sin_codigo} == {"Ajuste de conciliación"}


# ─────────────────────────── endpoint (integración) ───────────────────────────


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


@pytest.mark.asyncio
async def test_endpoint_crear_sin_codigo_es_422(api):
    h = await _token(api)
    r = await api.post(
        "/api/v1/rubros",
        headers=h,
        json={
            "grupo": "operacion",
            "nombre": "Sin código",
            "tipo_flujo": "egreso",
            "tipo": "variable",
            # falta `codigo`
        },
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_endpoint_crear_sin_tipo_es_422(api):
    h = await _token(api)
    r = await api.post(
        "/api/v1/rubros",
        headers=h,
        json={
            "grupo": "operacion",
            "nombre": "Sin clase",
            "tipo_flujo": "egreso",
            "codigo": "2900",
            # falta `tipo`
        },
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_endpoint_crear_con_ambos_ok(api):
    h = await _token(api)
    r = await api.post(
        "/api/v1/rubros",
        headers=h,
        json={
            "grupo": "operacion",
            "nombre": "Categoría RF-F9",
            "tipo_flujo": "egreso",
            "codigo": "2900",
            "tipo": "variable",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["codigo"] == "2900"
    assert body["tipo"] == "variable"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
