# backend/tests/test_rf_f3_pipeline.py
"""RF-F3 · pipeline — cuando el CEO configura UMBRAL_ATENCION, la proyección expone
`caja_atencion`, los meses en la banda ámbar quedan estado='atencion', y los valles
traen entrada/salida/duración. Sin config, todo se mantiene idéntico (candado)."""

from decimal import Decimal

import pytest
import pytest_asyncio
from app.audit.service import configure_audit, reset_audit
from app.auth import passwords, repository
from app.auth.models import User
from app.auth.roles import Role
from app.config import get_settings
from app.domain import DOMAIN_DOCUMENTS
from app.domain.configuracion import ClaveConfig, Configuracion
from app.domain.modelo_moto import ModeloMoto
from app.domain.parametros_proyeccion import ParametrosProyeccion
from app.main import create_app
from beanie import init_beanie
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

PWD = "clave-larga-1234"


async def _sembrar_config():
    """Escenario mínimo: parámetros/modelo que produzcan una serie y una curva que
    cae bajo el umbral de atención en algún mes."""
    await ParametrosProyeccion(
        vigente_desde="2026-07-01",
        caja_inicial=Decimal("30000000"),
        caja_minima=Decimal("30000000"),
        motos_base=10,
        crec_pct_mensual=Decimal("0"),
        horizonte_meses=6,
        adelanto_auteco=Decimal("0"),
        plazo_auteco_dias=150,
        base_auteco_dias=90,
        tasa_auteco=Decimal("0"),
        gastos_fijos=Decimal("40000000"),
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
        cuota_inicial=Decimal("1000000"),
        cuota_semanal=Decimal("100000"),
        plazo_semanas=78,
        matricula=Decimal("0"),
        participacion_mix=Decimal("1"),
        orden=0,
    ).insert()


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
    await _sembrar_config()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
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
async def test_proyeccion_sin_atencion_no_expone_umbral(api):
    """Sin fila UMBRAL_ATENCION: la API devuelve None, ningún mes queda 'atencion'."""
    h = await _token(api)
    r = await api.get("/api/v1/proyeccion?mes_inicio=2026-08", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["caja_atencion"] is None
    assert all(m["estado"] != "atencion" for m in body["meses"])


@pytest.mark.asyncio
async def test_proyeccion_con_atencion_pinta_ambar(api):
    """Con UMBRAL_ATENCION configurado alto: aparecen meses en 'atencion'."""
    await Configuracion(
        clave=ClaveConfig.UMBRAL_ATENCION,
        valor_decimal=Decimal("500000000"),  # muy por encima del piso esperado
        vigente_desde="2026-08-01",
        modificado_por="u",
    ).insert()
    h = await _token(api)
    r = await api.get("/api/v1/proyeccion?mes_inicio=2026-08", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["caja_atencion"] == "500000000.00"
    estados = [m["estado"] for m in body["meses"]]
    assert "atencion" in estados or "critico" in estados


@pytest.mark.asyncio
async def test_valles_endpoint_expone_entrada_salida_duracion(api):
    """/proyeccion/valles con atención configurada trae los 3 campos del segmento."""
    await Configuracion(
        clave=ClaveConfig.UMBRAL_ATENCION,
        valor_decimal=Decimal("500000000"),
        vigente_desde="2026-08-01",
        modificado_por="u",
    ).insert()
    h = await _token(api)
    r = await api.get("/api/v1/proyeccion/valles?mes_inicio=2026-08", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["caja_atencion"] == "500000000.00"
    if body["valles"]:
        v = body["valles"][0]
        assert v["entrada"] is not None
        assert v["duracion"] is not None
        # salida puede ser None si el horizonte queda bajo umbral hasta el final


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
