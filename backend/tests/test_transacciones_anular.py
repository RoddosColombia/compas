# backend/tests/test_transacciones_anular.py
"""FIX-G2 — anular una transacción MANUAL por contra-asiento (no se borra dinero).

MARCADO PARA AUDITORÍA KIMI (flujo crítico: crea un movimiento de dinero — el reverso).

Reglas cubiertas:
  - Solo txs banco=MANUAL (bancaria → 422; esas se corrigen re-cargando con dedup).
  - Solo mes abierto (cerrado → 409, regla 4).
  - RBAC: cargas:gestionar (consulta → 403) + verify_origin.
  - Contra-tx exacta: mismo valor/fecha/rubro, tipo_flujo INVERTIDO, banco=MANUAL,
    id_banco MAN-+ULID nuevo, revierte_id = original → efecto neto 0 (ambas patas).
  - motivo obligatorio (422 sin él).
  - No se anula dos veces la misma (409 si ya tiene reverso).
  - Evento `transaccion.creada` (existente) con via='contra_asiento'.
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
from app.domain.bancos import Banco
from app.domain.mes_control import EstadoMes, MesControl
from app.domain.rubro import Rubro
from app.domain.transaccion import Transaccion
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
    c = AsyncMongoMockClient()
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
    await Rubro(
        grupo="otros", nombre="Por clasificar", orden=98, es_sistema=True
    ).insert()
    await Rubro(
        grupo="otros",
        nombre="Recaudo de cartera",
        tipo_flujo="ingreso",
        orden=99,
        es_sistema=True,
    ).insert()
    await MesControl(mes="2026-03-01", saldo_inicial_caja=Decimal("0")).insert()
    await MesControl(
        mes="2026-01-01", saldo_inicial_caja=Decimal("0"), estado=EstadoMes.CERRADO
    ).insert()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, c
    repository.reset_auth()
    reset_audit()
    get_settings.cache_clear()


async def _token(ac, email="fin@roddos.com") -> dict:
    r = await ac.post("/api/v1/auth/login", json={"email": email, "password": PWD})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _crear_manual(ac, h, *, fecha="2026-03-15", valor="50000") -> dict:
    r = await ac.post(
        "/api/v1/transacciones",
        json={
            "fecha": fecha,
            "descripcion": "EGRESO EFECTIVO CAJA",
            "valor": valor,
            "tipo_flujo": "egreso",
        },
        headers={**h, "Idempotency-Key": f"k-{fecha}-{valor}"},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _rubro_id(nombre="Por clasificar") -> str:
    r = await Rubro.find_one(Rubro.nombre == nombre)
    return str(r.id)


@pytest.mark.asyncio
async def test_anular_manual_crea_contra_asiento_exacto_neto_cero(api):
    ac, c = api
    h = await _token(ac)
    orig = await _crear_manual(ac, h)
    r = await ac.post(
        f"/api/v1/transacciones/{orig['id']}/anular",
        json={"motivo": "digitación errada del CEO"},
        headers=h,
    )
    assert r.status_code == 200, r.text
    rev = r.json()
    # contra-tx exacta: mismo valor/fecha/rubro, flujo INVERTIDO, banco MANUAL, vínculo
    assert rev["valor"] == orig["valor"]
    assert rev["fecha"] == orig["fecha"]
    assert rev["rubro_id"] == orig["rubro_id"]
    assert rev["tipo_flujo"] == "ingreso"  # invertido de egreso
    assert rev["banco"] == "manual"
    assert rev["revierte_id"] == orig["id"]
    assert rev["id_banco"].startswith("MAN-") and rev["id_banco"] != orig["id_banco"]
    # efecto neto 0: egreso 50000 + ingreso 50000 (ambas patas persisten)
    txs = await Transaccion.find().to_list()
    assert len(txs) == 2
    neto = sum((t.valor if t.tipo_flujo.value == "ingreso" else -t.valor) for t in txs)
    assert neto == Decimal("0")
    # evento del reverso con via='contra_asiento'
    ev = await c["compas_test"]["audit_log"].find_one(
        {"evento": "transaccion.creada", "metadata.via": "contra_asiento"}
    )
    assert ev is not None
    assert ev["metadata"]["motivo"] == "digitación errada del CEO"


@pytest.mark.asyncio
async def test_motivo_obligatorio_422(api):
    ac, _ = api
    h = await _token(ac)
    orig = await _crear_manual(ac, h)
    # sin motivo
    r = await ac.post(f"/api/v1/transacciones/{orig['id']}/anular", json={}, headers=h)
    assert r.status_code == 422
    # motivo vacío
    r2 = await ac.post(
        f"/api/v1/transacciones/{orig['id']}/anular",
        json={"motivo": "   "},
        headers=h,
    )
    assert r2.status_code == 422


@pytest.mark.asyncio
async def test_no_se_anula_una_bancaria_422(api):
    ac, _ = api
    h = await _token(ac)
    mc = await MesControl.find_one(MesControl.mes == "2026-03-01")
    rid = await _rubro_id("Recaudo de cartera")
    from beanie import PydanticObjectId

    banc = Transaccion(
        fecha="2026-03-10",
        descripcion="Abono cliente",
        valor=Decimal("120000"),
        tipo_flujo="ingreso",
        rubro_id=PydanticObjectId(rid),
        mes_id=mc.id,
        banco=Banco.GLOBAL66,
        id_banco="G66-REF-1",
    )
    await banc.insert()
    r = await ac.post(
        f"/api/v1/transacciones/{banc.id}/anular",
        json={"motivo": "no debería poder"},
        headers=h,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_no_se_anula_en_mes_cerrado_409(api):
    ac, _ = api
    h = await _token(ac)
    # una manual en el mes CERRADO 2026-01 (insertada directo; el cierre es histórico)
    mc = await MesControl.find_one(MesControl.mes == "2026-01-01")
    rid = await _rubro_id()
    from beanie import PydanticObjectId

    tx = Transaccion(
        fecha="2026-01-10",
        descripcion="ajuste viejo",
        valor=Decimal("1000"),
        tipo_flujo="egreso",
        rubro_id=PydanticObjectId(rid),
        mes_id=mc.id,
        banco=Banco.MANUAL,
        id_banco="MAN-viejo-1",
    )
    await tx.insert()
    r = await ac.post(
        f"/api/v1/transacciones/{tx.id}/anular",
        json={"motivo": "tardío"},
        headers=h,
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_no_se_anula_dos_veces_la_misma_409(api):
    ac, _ = api
    h = await _token(ac)
    orig = await _crear_manual(ac, h)
    ok = await ac.post(
        f"/api/v1/transacciones/{orig['id']}/anular",
        json={"motivo": "primera"},
        headers=h,
    )
    assert ok.status_code == 200
    dup = await ac.post(
        f"/api/v1/transacciones/{orig['id']}/anular",
        json={"motivo": "segunda"},
        headers=h,
    )
    assert dup.status_code == 409


@pytest.mark.asyncio
async def test_rbac_consulta_no_anula_403(api):
    ac, _ = api
    hfin = await _token(ac)
    orig = await _crear_manual(ac, hfin)
    hcon = await _token(ac, "consulta@roddos.com")
    r = await ac.post(
        f"/api/v1/transacciones/{orig['id']}/anular",
        json={"motivo": "no permitido"},
        headers=hcon,
    )
    assert r.status_code == 403


# ── GET lista de manuales del mes (panel de /cargas) ────────────────────────────


@pytest.mark.asyncio
async def test_listar_manuales_del_mes_con_estado(api):
    ac, _ = api
    h = await _token(ac)
    a = await _crear_manual(ac, h, valor="50000")
    b = await _crear_manual(ac, h, valor="70000")
    # anular la primera
    await ac.post(
        f"/api/v1/transacciones/{a['id']}/anular",
        json={"motivo": "corrección"},
        headers=h,
    )
    r = await ac.get("/api/v1/transacciones?banco=manual&mes=2026-03", headers=h)
    assert r.status_code == 200, r.text
    items = {i["id"]: i for i in r.json()["items"]}
    # 3 movimientos: a (anulada), su reverso, b (intacta)
    assert len(items) == 3
    assert items[a["id"]]["anulada"] is True
    assert items[a["id"]]["es_reverso"] is False
    assert items[b["id"]]["anulada"] is False
    reverso = next(i for i in items.values() if i["revierte_id"] == a["id"])
    assert reverso["es_reverso"] is True
    assert reverso["tipo_flujo"] == "ingreso"


@pytest.mark.asyncio
async def test_listar_filtra_por_mes(api):
    ac, _ = api
    h = await _token(ac)
    await _crear_manual(ac, h, fecha="2026-03-15", valor="50000")
    r = await ac.get("/api/v1/transacciones?banco=manual&mes=2026-07", headers=h)
    assert r.status_code == 200
    assert r.json()["items"] == []


@pytest.mark.asyncio
async def test_listar_lo_puede_leer_consulta(api):
    ac, _ = api
    hfin = await _token(ac)
    await _crear_manual(ac, hfin)
    hcon = await _token(ac, "consulta@roddos.com")
    r = await ac.get("/api/v1/transacciones?banco=manual&mes=2026-03", headers=hcon)
    assert r.status_code == 200
