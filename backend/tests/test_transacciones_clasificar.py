# backend/tests/test_transacciones_clasificar.py
"""C3 — PATCH /api/v1/transacciones/{id}/clasificar (GO Kimi PLAN-I 9.3).

MARCADO PARA AUDITORÍA KIMI (gate I-PR1; lista §5).

Reclasificación MANUAL: mes cerrado → 409 (regla 4); rubro inexistente → 404,
inactivo → 422, tipo incoherente → 409 (D1); OK → `transaccion.clasificada` con
{rubro_anterior→nuevo}; fecha/valor/banco/id_banco INTACTOS (Spec §2.2, assert
explícito). `proponer_regla:true` → ReglaClasificacion aprendida con activa=False
FORZADO (§1.9: nunca auto-activada) + `regla.creada`.
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
from app.domain.mes_control import EstadoMes, MesControl
from app.domain.regla_clasificacion import ReglaClasificacion
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
    await Rubro(
        grupo="otros", nombre="Por clasificar", orden=97, es_sistema=True
    ).insert()
    await Rubro(grupo="operacion", nombre="Cafetería", orden=1).insert()
    await Rubro(
        grupo="otros",
        nombre="Recaudo",
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


async def _tx(fecha="2026-03-15", tipo="egreso") -> Transaccion:
    pc = await Rubro.find_one(Rubro.nombre == "Por clasificar")
    mc = await MesControl.find_one(MesControl.mes == fecha[:7] + "-01")
    tx = Transaccion(
        fecha=fecha,
        descripcion="COMPRA CAFETERIA LA 14",
        valor=Decimal("50000"),
        tipo_flujo=tipo,
        rubro_id=pc.id,
        mes_id=mc.id,
        banco="manual",
        id_banco=f"MAN-CLASIF-{fecha}",
    )
    await tx.insert()
    return tx


async def _clasificar(ac, h, tx_id, rubro_id, **extra):
    return await ac.patch(
        f"/api/v1/transacciones/{tx_id}/clasificar",
        json={"rubro_id": str(rubro_id), **extra},
        headers=h,
    )


async def test_clasificar_ok_emite_evento_con_anterior_y_nuevo(api):
    ac, c = api
    h = await _token(ac)
    tx = await _tx()
    caf = await Rubro.find_one(Rubro.nombre == "Cafetería")
    pc = await Rubro.find_one(Rubro.nombre == "Por clasificar")
    r = await _clasificar(ac, h, tx.id, caf.id)
    assert r.status_code == 200
    assert r.json()["rubro_id"] == str(caf.id)
    despues = await Transaccion.get(tx.id)
    assert despues.rubro_id == caf.id
    assert despues.clasificada_por is not None
    assert despues.clasificada_at is not None
    ev = await c["compas_test"]["audit_log"].find_one(
        {"evento": "transaccion.clasificada"}
    )
    assert ev is not None and ev["entidad_id"] == str(tx.id)
    assert ev["metadata"]["rubro_anterior"] == str(pc.id)
    assert ev["metadata"]["rubro_nuevo"] == str(caf.id)


async def test_clasificar_inmutables_intactos(api):
    # Spec §2.2 (assert explícito de Kimi): fecha/valor/banco/id_banco no cambian.
    ac, _ = api
    h = await _token(ac)
    tx = await _tx()
    caf = await Rubro.find_one(Rubro.nombre == "Cafetería")
    await _clasificar(ac, h, tx.id, caf.id)
    d = await Transaccion.get(tx.id)
    assert d.fecha == tx.fecha
    assert d.valor == tx.valor
    assert d.banco == tx.banco
    assert d.id_banco == tx.id_banco
    assert d.tipo_flujo == tx.tipo_flujo


async def test_clasificar_mes_cerrado_409(api):
    # Regla 4: el histórico congelado no se reclasifica.
    ac, _ = api
    h = await _token(ac)
    tx = await _tx(fecha="2026-01-15")
    caf = await Rubro.find_one(Rubro.nombre == "Cafetería")
    r = await _clasificar(ac, h, tx.id, caf.id)
    assert r.status_code == 409


async def test_clasificar_rubro_inactivo_422(api):
    ac, _ = api
    h = await _token(ac)
    tx = await _tx()
    caf = await Rubro.find_one(Rubro.nombre == "Cafetería")
    caf.activo = False
    await caf.save()
    r = await _clasificar(ac, h, tx.id, caf.id)
    assert r.status_code == 422


async def test_clasificar_tipo_incoherente_409_d1(api):
    # Transacción de egreso hacia 'Recaudo' (ingreso) → 409.
    ac, _ = api
    h = await _token(ac)
    tx = await _tx(tipo="egreso")
    recaudo = await Rubro.find_one(Rubro.nombre == "Recaudo")
    r = await _clasificar(ac, h, tx.id, recaudo.id)
    assert r.status_code == 409


async def test_clasificar_rubro_inexistente_404(api):
    ac, _ = api
    h = await _token(ac)
    tx = await _tx()
    r = await _clasificar(ac, h, tx.id, "64b000000000000000000000")
    assert r.status_code == 404


async def test_clasificar_transaccion_inexistente_404(api):
    ac, _ = api
    h = await _token(ac)
    caf = await Rubro.find_one(Rubro.nombre == "Cafetería")
    r = await _clasificar(ac, h, "64b000000000000000000000", caf.id)
    assert r.status_code == 404


async def test_proponer_regla_crea_aprendida_inactiva(api):
    # §1.9/D5: la propuesta nace activa=False SIEMPRE + regla.creada.
    ac, c = api
    h = await _token(ac)
    tx = await _tx()
    caf = await Rubro.find_one(Rubro.nombre == "Cafetería")
    r = await _clasificar(
        ac, h, tx.id, caf.id, proponer_regla=True, patron="cafeteria la 14"
    )
    assert r.status_code == 200
    regla = await ReglaClasificacion.find_one()
    assert regla is not None
    assert regla.origen.value == "aprendida"
    assert regla.activa is False  # NUNCA auto-activada
    assert regla.rubro_id == caf.id
    ev = await c["compas_test"]["audit_log"].find_one({"evento": "regla.creada"})
    assert ev is not None and ev["metadata"]["origen"] == "aprendida"


async def test_proponer_regla_sin_patron_422(api):
    ac, _ = api
    h = await _token(ac)
    tx = await _tx()
    caf = await Rubro.find_one(Rubro.nombre == "Cafetería")
    r = await _clasificar(ac, h, tx.id, caf.id, proponer_regla=True)
    assert r.status_code == 422


async def test_clasificar_consulta_403(api):
    ac, _ = api
    h = await _token(ac, "consulta@roddos.com")
    tx = await _tx()
    caf = await Rubro.find_one(Rubro.nombre == "Cafetería")
    r = await _clasificar(ac, h, tx.id, caf.id)
    assert r.status_code == 403


async def test_fail_closed_clasificar_compensa(api, monkeypatch):
    # O1: si el emit de transaccion.clasificada falla, el rubro se revierte.
    ac, _ = api
    h = await _token(ac)
    tx = await _tx()
    caf = await Rubro.find_one(Rubro.nombre == "Cafetería")
    pc = await Rubro.find_one(Rubro.nombre == "Por clasificar")

    async def _boom(*a, **k):
        raise RuntimeError("audit caído")

    monkeypatch.setattr("app.transacciones.service.emit_audit", _boom)
    with pytest.raises(RuntimeError):
        await _clasificar(ac, h, tx.id, caf.id)
    assert (await Transaccion.get(tx.id)).rubro_id == pc.id  # revertido
