# backend/tests/test_presupuesto_generar.py
"""POST /meses/{mes}/sugerido — generación del sugerido end-to-end (F-07, §1.4.1).

MARCADO PARA AUDITORÍA KIMI (motor del sugerido).

El test estrella reproduce el ejemplo oficial del Spec §1.4.1 EN LA API: 3 meses
cerrados con ejecutado 48M/61M/75M de un rubro + crec 15% → línea con sugerido
84.033.333,33 y sus componentes. Cubre además: solo meses cerrados; RBAC; idempotencia
(no regenerar); rubros de sistema excluidos; historia incompleta.
"""

from decimal import Decimal

import httpx
import pytest_asyncio
from app.audit.service import configure_audit, reset_audit
from app.auth import passwords, repository
from app.auth.models import User
from app.auth.roles import Role
from app.config import get_settings
from app.domain import DOMAIN_DOCUMENTS
from app.domain.mes_control import EstadoMes, MesControl
from app.domain.rubro import Rubro
from app.domain.transaccion import Transaccion
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

    from app.main import create_app

    app = create_app()
    # tz_aware=True como el Motor real (mongo.create_client) → los datetime
    # re-leídos vuelven UTC-aware (regla 2), no naive.
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


async def _mes(mesd: str, estado: EstadoMes) -> MesControl:
    mc = MesControl(mes=mesd, saldo_inicial_caja=Decimal("0"), estado=estado)
    await mc.insert()
    return mc


async def _rubro(nombre: str, orden: int, sistema: bool = False) -> Rubro:
    r = Rubro(grupo="operacion", nombre=nombre, orden=orden, es_sistema=sistema)
    await r.insert()
    return r


_SEQ = [0]


async def _ejec(rubro_id, mes_id, monto: str):
    """Una transacción de egreso que aporta `monto` al ejecutado del rubro/mes."""
    _SEQ[0] += 1
    await Transaccion(
        fecha="2026-01-15",
        descripcion="EJEC",
        valor=Decimal(monto),
        tipo_flujo="egreso",
        rubro_id=rubro_id,
        mes_id=mes_id,
        banco="manual",
        id_banco=f"MAN-EJEC-{_SEQ[0]}",
    ).insert()


async def test_ejemplo_oficial_end_to_end(api):
    # Spec §1.4.1 vía API: abr/may/jun cerrados 48/61/75M → jul sugerido 84.033.333,33
    h = await _token(api)
    abr = await _mes("2026-04-01", EstadoMes.CERRADO)
    may = await _mes("2026-05-01", EstadoMes.CERRADO)
    jun = await _mes("2026-06-01", EstadoMes.CERRADO)
    await _mes("2026-07-01", EstadoMes.SUGERIDO)  # objetivo (abierto)
    rubro = await _rubro("Arriendos", 4)
    # dos transacciones en un mes para verificar que E(i) SUMA
    await _ejec(rubro.id, abr.id, "20000000")
    await _ejec(rubro.id, abr.id, "28000000")  # abr total 48M
    await _ejec(rubro.id, may.id, "61000000")
    await _ejec(rubro.id, jun.id, "75000000")

    r = await api.post(
        "/api/v1/meses/2026-07/sugerido", json={"crec_pct": "0.15"}, headers=h
    )
    assert r.status_code == 201
    ln = next(x for x in r.json()["lineas"] if x["rubro_id"] == str(rubro.id))
    assert ln["prom_3m"] == "61333333.33"
    assert ln["tendencia_mes"] == "13500000.00"
    assert ln["monto_sugerido"] == "84033333.33"
    assert ln["historia_incompleta"] is False
    assert ln["monto_definido"] is None
    assert ln["vigente"] is True


async def test_solo_cuenta_meses_cerrados(api):
    # Un mes EN_EJECUCION no cuenta como historia (solo 'cerrado').
    h = await _token(api)
    jun = await _mes("2026-06-01", EstadoMes.CERRADO)
    await _mes("2026-07-01", EstadoMes.SUGERIDO)  # abierto, no cerrado
    await _mes("2026-08-01", EstadoMes.SUGERIDO)  # objetivo
    rubro = await _rubro("Arriendos", 4)
    await _ejec(rubro.id, jun.id, "50000000")
    r = await api.post("/api/v1/meses/2026-08/sugerido", json={}, headers=h)
    ln = next(x for x in r.json()["lineas"] if x["rubro_id"] == str(rubro.id))
    assert ln["historia_incompleta"] is True  # solo 1 mes cerrado
    assert ln["prom_3m"] == "50000000.00"


async def test_excluye_rubros_de_sistema(api):
    h = await _token(api)
    await _mes("2026-07-01", EstadoMes.SUGERIDO)
    await _rubro("Arriendos", 4)
    await _rubro("Por clasificar", 98, sistema=True)
    await _rubro("Recaudo", 99, sistema=True)
    r = await api.post("/api/v1/meses/2026-07/sugerido", json={}, headers=h)
    nombres_generados = len(r.json()["lineas"])
    assert nombres_generados == 1  # solo Arriendos, no los de sistema


async def test_no_regenera_409(api):
    h = await _token(api)
    await _mes("2026-07-01", EstadoMes.SUGERIDO)
    await _rubro("Arriendos", 4)
    await api.post("/api/v1/meses/2026-07/sugerido", json={}, headers=h)
    r = await api.post("/api/v1/meses/2026-07/sugerido", json={}, headers=h)
    assert r.status_code == 409


async def test_mes_inexistente_422(api):
    h = await _token(api)
    r = await api.post("/api/v1/meses/2026-07/sugerido", json={}, headers=h)
    assert r.status_code == 422


async def test_consulta_403(api):
    h = await _token(api, "consulta@roddos.com")
    await _mes("2026-07-01", EstadoMes.SUGERIDO)
    r = await api.post("/api/v1/meses/2026-07/sugerido", json={}, headers=h)
    assert r.status_code == 403


async def test_crec_negativo_422(api):
    h = await _token(api)
    await _mes("2026-07-01", EstadoMes.SUGERIDO)
    r = await api.post(
        "/api/v1/meses/2026-07/sugerido", json={"crec_pct": "-0.1"}, headers=h
    )
    assert r.status_code == 422


async def test_listar_presupuesto(api):
    h = await _token(api)
    await _mes("2026-07-01", EstadoMes.SUGERIDO)
    await _rubro("Arriendos", 4)
    await api.post("/api/v1/meses/2026-07/sugerido", json={}, headers=h)
    r = await api.get("/api/v1/meses/2026-07/presupuesto", headers=h)
    assert r.status_code == 200
    assert len(r.json()["lineas"]) == 1
    assert r.json()["lineas"][0]["vigente"] is True
