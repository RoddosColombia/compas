# backend/tests/test_rv_v2_r3_unidades_extra.py
"""RV-V2 rebanada 3 · Fundacional §3 AC #5 + AC #7.

AC #5 · Escenario superpuesto: base + escenario dibujados juntos con área
       coloreada. El «escenario» que el cockpit ofrece por default es «vender
       más motos» — controlado por un input de UNIDADES EXTRA por mes.

AC #7 · Motos del escenario editable ANTES de activar (input libre) + botón
       «vender de más» = calcula el mínimo N (goal-seek de unidades) que evita
       que la caja perfore la referencia.

Contexto (mapa):
  · Ya existe `resolver_unidades_para_umbral()` en `proyeccion/solver_unidades.py`
    (bisección entera acotada; `proyectar_fn` corre el pipeline completo
    motor→E1→D2 por candidato). Fue construido para FABS (`cfo.calc.escenario.
    motos_para_evitar_umbral`); RF-F5 lo dejó como stub honesto en el cockpit
    (`disponible=False`) porque no cabía en el hot-path de las palancas por
    valle.
  · Este PR lo EXPONE detrás de dos endpoints compute-only invocados por clic
    explícito del CEO (no hot-path):
    - `POST /proyeccion/con-unidades-extra` — corre la proyección con
      `motos_base + N` donde N lo teclea el CEO (AC #7 «editable antes»).
    - `POST /proyeccion/solver-unidades` — corre el solver ya existente (AC #7
      «vender de más» → devuelve el N mínimo).

Motor sin tocar. Golden-master 176 meses intacto.
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
from app.domain.modelo_moto import ModeloMoto
from app.domain.parametros_proyeccion import ParametrosProyeccion
from app.main import create_app
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient

PWD = "clave-larga-1234"


async def _sembrar_config(horizonte: int = 12, motos_base: int = 10):
    """Config mínima con motos_base configurable — para que el escenario con
    unidades extra devuelva otra serie que la base."""
    await ParametrosProyeccion(
        vigente_desde="2026-07-01",
        caja_inicial=Decimal("50000000"),
        caja_minima=Decimal("30000000"),
        motos_base=motos_base,
        crec_pct_mensual=Decimal("0"),
        horizonte_meses=horizonte,
        adelanto_auteco=Decimal("0"),
        plazo_auteco_dias=150,
        base_auteco_dias=90,
        tasa_auteco=Decimal("0"),
        gastos_fijos=Decimal("30000000"),
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


# ─────────────────────────── AC #5 + AC #7 «editable antes» ───────────────────────────


@pytest.mark.asyncio
async def test_rvv2_r3_con_unidades_extra_devuelve_shape_de_proyeccion(api):
    """POST /proyeccion/con-unidades-extra devuelve el MISMO shape que GET
    /proyeccion (los 23 campos por mes). El frontend lo pinta como serie
    superpuesta."""
    h = await _token(api)
    r = await api.post(
        "/api/v1/proyeccion/con-unidades-extra?mes_inicio=2026-08",
        headers=h,
        json={"unidades_extra": 5},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # Mismo shape que GET /proyeccion.
    assert "meses" in body
    assert len(body["meses"]) > 0
    assert "piso_caja" in body
    # Motos por mes suben: motos_base=10 + 5 = 15 en el primer mes (sin rampa).
    assert body["meses"][0]["motos"] == 15


@pytest.mark.asyncio
async def test_rvv2_r3_con_unidades_extra_0_es_paridad_con_get_proyeccion(api):
    """`unidades_extra=0` debe devolver EXACTAMENTE la misma serie que el GET
    de la proyección vigente — la superposición es aditiva, cero rompe."""
    h = await _token(api)
    base = await api.get("/api/v1/proyeccion?mes_inicio=2026-08", headers=h)
    esc = await api.post(
        "/api/v1/proyeccion/con-unidades-extra?mes_inicio=2026-08",
        headers=h,
        json={"unidades_extra": 0},
    )
    assert base.status_code == 200 and esc.status_code == 200
    b = base.json()
    e = esc.json()
    assert b["piso_caja"] == e["piso_caja"]
    assert len(b["meses"]) == len(e["meses"])
    for mb, me in zip(b["meses"], e["meses"], strict=True):
        assert mb["mes"] == me["mes"]
        assert mb["motos"] == me["motos"]
        assert mb["caja"] == me["caja"]


@pytest.mark.asyncio
async def test_rvv2_r3_unidades_extra_negativas_es_422(api):
    h = await _token(api)
    r = await api.post(
        "/api/v1/proyeccion/con-unidades-extra?mes_inicio=2026-08",
        headers=h,
        json={"unidades_extra": -5},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_rvv2_r3_unidades_extra_sobre_cap_es_422(api):
    """Rechazo simétrico con el cap del solver (10_000)."""
    h = await _token(api)
    r = await api.post(
        "/api/v1/proyeccion/con-unidades-extra?mes_inicio=2026-08",
        headers=h,
        json={"unidades_extra": 10_001},
    )
    assert r.status_code == 422


# ─────────────────────────── AC #7 «vender de más» ───────────────────────────


@pytest.mark.asyncio
async def test_rvv2_r3_solver_unidades_devuelve_n_alcanzable(api):
    """POST /proyeccion/solver-unidades corre el bisector ya existente y
    devuelve `{unidades_extra, alcanzable, piso_resultante, meta}`. Con la
    config del test, el piso base > umbral ⇒ N=0 alcanzable."""
    h = await _token(api)
    r = await api.post(
        "/api/v1/proyeccion/solver-unidades?mes_inicio=2026-08",
        headers=h,
        json={},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) >= {"unidades_extra", "alcanzable", "piso_resultante", "meta"}
    # Con caja_inicial=$50M y caja_minima=$30M y motos_base=10, la base ya cumple.
    assert body["alcanzable"] is True
    assert body["unidades_extra"] >= 0


@pytest.mark.asyncio
async def test_rvv2_r3_solver_unidades_shape_alcanzable_false(api, monkeypatch):
    """Cuando ni siquiera el cap alcanza el umbral, el solver devuelve
    `alcanzable=False` sin piso (contrato de UnidadesResultado)."""
    # Elevamos el umbral crítico a un valor imposible de alcanzar sin ingresos
    # significativos — con motos que solo pagan cuota_inicial pequeña, ningún N
    # sube el piso a $500M.
    from app.domain.parametros_proyeccion import ParametrosProyeccion

    await ParametrosProyeccion.find({}).delete()
    await ParametrosProyeccion(
        vigente_desde="2026-07-01",
        caja_inicial=Decimal("10000000"),
        caja_minima=Decimal("500000000"),  # umbral inalcanzable
        motos_base=10,
        crec_pct_mensual=Decimal("0"),
        horizonte_meses=12,
        adelanto_auteco=Decimal("0"),
        plazo_auteco_dias=150,
        base_auteco_dias=90,
        tasa_auteco=Decimal("0"),
        gastos_fijos=Decimal("30000000"),
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
    h = await _token(api)
    # Cap bajo para que la bisección termine rápido en el test.
    r = await api.post(
        "/api/v1/proyeccion/solver-unidades?mes_inicio=2026-08",
        headers=h,
        json={"cap_unidades": 50},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["alcanzable"] is False
    assert body["piso_resultante"] is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
