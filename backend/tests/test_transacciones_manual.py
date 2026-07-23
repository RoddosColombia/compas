# backend/tests/test_transacciones_manual.py
"""POST /api/v1/transacciones — transacción manual (US-10, F-04, Spec §1.12).

MARCADO PARA AUDITORÍA KIMI (flujo crítico: crea movimientos de dinero).

Reglas cubiertas:
  - Regla 1: `valor` viaja como STRING en el JSON; un number float → 422 (strict).
  - F-04: id_banco = 'MAN-'+ULID → dos manuales idénticos el mismo día coexisten.
  - §1.12: Idempotency-Key OBLIGATORIA; misma key+mismo payload → replay (no
    duplica); misma key+payload distinto → 422.
  - RBAC: cargas:gestionar (consulta → 403).
  - Regla 4: mes cerrado → 409 (tardías llegan con el flujo de cierre, Sprint 4).
  - Regla 11: rubro explícito emite `transaccion.clasificada` (catálogo cerrado).
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
    # Semillas mínimas del dominio.
    await Rubro(
        grupo="otros", nombre="Por clasificar", orden=98, es_sistema=True
    ).insert()
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


def _body(**over):
    base = {
        "fecha": "2026-03-15",
        "descripcion": "EGRESO EFECTIVO CAJA",
        "valor": "50000",
        "tipo_flujo": "egreso",
    }
    base.update(over)
    return base


async def _post(ac, h, body, key="k-001"):
    return await ac.post(
        "/api/v1/transacciones",
        json=body,
        headers={**h, "Idempotency-Key": key},
    )


async def test_crea_manual_ok(api):
    ac, _ = api
    h = await _token(ac)
    r = await _post(ac, h, _body())
    assert r.status_code == 201
    d = r.json()
    assert d["banco"] == "manual"
    assert d["id_banco"].startswith("MAN-")
    assert d["valor"] == "50000.00"  # string, 2 decimales (regla 1)
    assert isinstance(d["valor"], str)


async def test_dos_manuales_identicos_coexisten(api):
    # F-04 / US-10: mismo día, mismo valor, misma descripción → ambos entran.
    ac, _ = api
    h = await _token(ac)
    r1 = await _post(ac, h, _body(), key="k-A")
    r2 = await _post(ac, h, _body(), key="k-B")
    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.json()["id_banco"] != r2.json()["id_banco"]
    assert await Transaccion.find_all().count() == 2


async def test_idempotency_key_obligatoria(api):
    ac, _ = api
    h = await _token(ac)
    r = await ac.post("/api/v1/transacciones", json=_body(), headers=h)
    assert r.status_code == 422


async def test_replay_misma_key_mismo_payload(api):
    # §1.12: replay de la respuesta original, NO segunda transacción.
    ac, _ = api
    h = await _token(ac)
    r1 = await _post(ac, h, _body(), key="k-R")
    r2 = await _post(ac, h, _body(), key="k-R")
    assert r2.status_code == r1.status_code == 201
    assert r2.json()["id_banco"] == r1.json()["id_banco"]
    assert await Transaccion.find_all().count() == 1


async def test_misma_key_payload_distinto_422(api):
    ac, _ = api
    h = await _token(ac)
    await _post(ac, h, _body(), key="k-X")
    r = await _post(ac, h, _body(valor="99999"), key="k-X")
    assert r.status_code == 422


async def test_valor_como_number_es_422(api):
    # Regla 1: montos como string en la API; un number JSON se rechaza (strict).
    ac, _ = api
    h = await _token(ac)
    r = await _post(ac, h, _body(valor=50000.0))
    assert r.status_code == 422


async def test_valor_no_positivo_422(api):
    ac, _ = api
    h = await _token(ac)
    assert (await _post(ac, h, _body(valor="0"), key="kz")).status_code == 422
    assert (await _post(ac, h, _body(valor="-5"), key="kn")).status_code == 422


async def test_consulta_403(api):
    ac, _ = api
    h = await _token(ac, "consulta@roddos.com")
    r = await _post(ac, h, _body())
    assert r.status_code == 403


async def test_mes_cerrado_409(api):
    # Regla 4: el histórico es inmutable; la tardía llega en Sprint 4.
    ac, _ = api
    h = await _token(ac)
    r = await _post(ac, h, _body(fecha="2026-01-15"))
    assert r.status_code == 409


async def test_mes_inexistente_422(api):
    ac, _ = api
    h = await _token(ac)
    r = await _post(ac, h, _body(fecha="2026-06-15"))
    assert r.status_code == 422


async def test_toda_creacion_manual_emite_creada(api):
    # Kimi M-1 (CR-S2): el POST manual es la única vía de dinero sin archivo de
    # banco → TODA creación manual deja `transaccion.creada` (aunque caiga en
    # 'Por clasificar'); la IdempotencyKey expira a 24h y no sirve de rastro.
    ac, c = api
    h = await _token(ac)
    r = await _post(ac, h, _body())  # sin rubro explícito
    assert r.status_code == 201
    ev = await c["compas_test"]["audit_log"].find_one({"evento": "transaccion.creada"})
    assert ev is not None
    assert ev["entidad_id"] == r.json()["id"]
    assert ev["metadata"]["origen"] == "manual"


async def test_carrera_idempotency_key_da_409(api, monkeypatch):
    # Kimi B-1: dos requests concurrentes con la misma key → el 2º insert choca
    # con el índice único → 409 (no 500). Se simula el DuplicateKeyError.
    from app.domain.idempotency import IdempotencyKey
    from pymongo.errors import DuplicateKeyError

    ac, _ = api
    h = await _token(ac)

    async def _choca(self):
        raise DuplicateKeyError("E11000 duplicate key")

    monkeypatch.setattr(IdempotencyKey, "insert", _choca)
    r = await _post(ac, h, _body(), key="k-race")
    assert r.status_code == 409


async def test_rubro_explicito_emite_clasificada(api):
    ac, c = api
    h = await _token(ac)
    recaudo = await Rubro.find_one(Rubro.nombre == "Recaudo")
    r = await _post(
        ac,
        h,
        _body(
            tipo_flujo="ingreso",
            rubro_id=str(recaudo.id),
            descripcion="ABONO CUOTA",
        ),
    )
    assert r.status_code == 201
    ev = await c["compas_test"]["audit_log"].find_one(
        {"evento": "transaccion.clasificada"}
    )
    assert ev is not None
    assert ev["metadata"]["origen"] == "manual"


async def test_rubro_incoherente_con_tipo_422(api):
    # Recaudo es ingreso; declararlo egreso es ambigüedad → 422, no se adivina.
    ac, _ = api
    h = await _token(ac)
    recaudo = await Rubro.find_one(Rubro.nombre == "Recaudo")
    r = await _post(ac, h, _body(tipo_flujo="egreso", rubro_id=str(recaudo.id)))
    assert r.status_code == 422


async def test_clasificar_hacia_rubro_inactivo_422(api):
    # B-2a (Kimi PLAN-I C1): la baja lógica impide clasificaciones NUEVAS hacia el
    # rubro inactivo — la guarda vive aquí (crear_transaccion_manual) y aplicará
    # igual a la futura auto-clasificación (C3).
    ac, _ = api
    h = await _token(ac)
    inactivo = await Rubro(
        grupo="operacion", nombre="Renting", orden=50, activo=False
    ).insert()
    r = await _post(ac, h, _body(rubro_id=str(inactivo.id)))
    assert r.status_code == 422
