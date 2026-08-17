# backend/tests/test_metas_ingreso.py
"""Metas de ingreso (D2 §6, CR-D2) — CRUD auditado, informativo (no toca el motor)."""

import httpx
import pytest
import pytest_asyncio
from app.audit.service import configure_audit, reset_audit
from app.auth import passwords, repository
from app.auth.models import User
from app.auth.roles import Role
from app.config import get_settings
from app.domain import DOMAIN_DOCUMENTS
from app.main import create_app
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient

PWD = "clave-larga-1234"


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
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.mark.asyncio
async def test_crear_listar_meta(api):
    h = await _token(api)
    r = await api.post(
        "/api/v1/metas-ingreso",
        json={
            "mes": "2026-09",
            "valor": "300000000",
            "lineas": [{"nombre": "Motos nuevas", "valor": "250000000"}],
        },
        headers=h,
    )
    assert r.status_code == 201, r.text
    assert r.json()["mes"] == "2026-09"
    # sin MesControl del mes, el real es null (aún no se abrió el ciclo)
    assert r.json()["real_ejecutado"] is None
    lst = await api.get("/api/v1/metas-ingreso", headers=h)
    assert [m["mes"] for m in lst.json()["items"]] == ["2026-09"]


@pytest.mark.asyncio
async def test_una_meta_por_mes(api):
    h = await _token(api)
    base = {"mes": "2026-09", "valor": "1", "lineas": []}
    assert (
        await api.post("/api/v1/metas-ingreso", json=base, headers=h)
    ).status_code == 201
    r = await api.post("/api/v1/metas-ingreso", json=base, headers=h)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_editar_y_eliminar(api):
    h = await _token(api)
    mid = (
        await api.post(
            "/api/v1/metas-ingreso",
            json={"mes": "2026-09", "valor": "100", "lineas": []},
            headers=h,
        )
    ).json()["id"]
    r = await api.patch(
        f"/api/v1/metas-ingreso/{mid}", json={"valor": "200"}, headers=h
    )
    assert r.status_code == 200
    assert r.json()["valor"] == "200.00"
    assert (
        await api.delete(f"/api/v1/metas-ingreso/{mid}", headers=h)
    ).status_code == 204
    assert (await api.get("/api/v1/metas-ingreso", headers=h)).json()["items"] == []


@pytest.mark.asyncio
async def test_mes_mal_formado_422(api):
    h = await _token(api)
    r = await api.post(
        "/api/v1/metas-ingreso",
        json={"mes": "2026/09", "valor": "1", "lineas": []},
        headers=h,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_rbac(api):
    h = await _token(api, "consulta@roddos.com")
    r = await api.post(
        "/api/v1/metas-ingreso",
        json={"mes": "2026-09", "valor": "1", "lineas": []},
        headers=h,
    )
    assert r.status_code == 403
    assert (await api.get("/api/v1/metas-ingreso", headers=h)).status_code == 200


@pytest.mark.asyncio
async def test_meta_con_dos_lineas_persiste_y_serializa(api):
    """PTS6-E: la meta se guarda en 2 líneas (Cuota inicial / Cuotas semanales)
    que suman el total; la API las devuelve tal cual."""
    h = await _token(api)
    r = await api.post(
        "/api/v1/metas-ingreso",
        json={
            "mes": "2026-09",
            "valor": "260000000",
            "lineas": [
                {"nombre": "Cuota inicial", "valor": "60000000"},
                {"nombre": "Cuotas semanales", "valor": "200000000"},
            ],
        },
        headers=h,
    )
    assert r.status_code == 201, r.text
    lineas = r.json()["lineas"]
    assert [ln["nombre"] for ln in lineas] == ["Cuota inicial", "Cuotas semanales"]
    assert [ln["valor"] for ln in lineas] == ["60000000.00", "200000000.00"]


@pytest.mark.asyncio
async def test_real_separado_inicial_vs_semanal_por_rubro(api):
    """PTS6-E: real_inicial ← 0120, real_semanal ← 0110 (expande partes, excluye
    neutros). Hoy todo el ingreso cae en 0110 → inicial 0, semanal = total."""
    from decimal import Decimal

    from app.domain.mes_control import MesControl
    from app.domain.rubro import Rubro
    from app.domain.transaccion import ParteClasificacion, Transaccion

    h = await _token(api)
    mc = await MesControl(mes="2026-09-01", saldo_inicial_caja=Decimal("0")).insert()
    r0110 = await Rubro(
        grupo="ingresos_operativos",
        nombre="Recaudo de cartera",
        tipo_flujo="ingreso",
        codigo="0110",
        orden=1,
        es_sistema=True,
    ).insert()
    r0120 = await Rubro(
        grupo="ingresos_operativos",
        nombre="Cuotas iniciales",
        tipo_flujo="ingreso",
        codigo="0120",
        orden=2,
    ).insert()
    reversas = await Rubro(
        grupo="otros",
        nombre="Reversas y devoluciones",
        tipo_flujo="ingreso",
        codigo=None,
        orden=98,
        es_sistema=True,
    ).insert()
    # recaudo semanal directo
    await Transaccion(
        fecha="2026-09-03",
        descripcion="cuota semanal",
        valor=Decimal("50000000"),
        tipo_flujo="ingreso",
        rubro_id=r0110.id,
        mes_id=mc.id,
        banco="global66",
        id_banco="SEM|1",
    ).insert()
    # consignación MIXTA dividida: 12M cuota inicial (0120) + 8M recaudo (0110)
    await Transaccion(
        fecha="2026-09-04",
        descripcion="mixta",
        valor=Decimal("20000000"),
        tipo_flujo="ingreso",
        rubro_id=r0120.id,
        mes_id=mc.id,
        banco="global66",
        id_banco="MIX|1",
        partes=[
            ParteClasificacion(rubro_id=r0120.id, valor=Decimal("12000000")),
            ParteClasificacion(rubro_id=r0110.id, valor=Decimal("8000000")),
        ],
    ).insert()
    # una reversa (neutro) que NO debe contar
    await Transaccion(
        fecha="2026-09-05",
        descripcion="reversa",
        valor=Decimal("1000000"),
        tipo_flujo="ingreso",
        rubro_id=reversas.id,
        mes_id=mc.id,
        banco="global66",
        id_banco="REV|1",
    ).insert()

    await api.post(
        "/api/v1/metas-ingreso",
        json={"mes": "2026-09", "valor": "100000000", "lineas": []},
        headers=h,
    )
    lst = await api.get("/api/v1/metas-ingreso", headers=h)
    meta = next(m for m in lst.json()["items"] if m["mes"] == "2026-09")
    assert meta["real_inicial"] == "12000000.00"  # solo la parte 0120
    assert meta["real_semanal"] == "58000000.00"  # 50M + 8M
    assert meta["real_ejecutado"] == "70000000.00"  # total sin la reversa
