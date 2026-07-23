# backend/tests/test_reglas_endpoints.py
"""C3 auto-clasificación — /api/v1/reglas-clasificacion (GO Kimi PLAN-I 9.3, CR-S5).

MARCADO PARA AUDITORÍA KIMI (gate I-PR1; lista §5 del veredicto PLAN-I).

Cubre: D1 coherencia tipo regla↔rubro al crear/editar Y al activar/aprobar (B-1);
precedencia determinista (prioridad asc + _id); unicidad de patrón activo;
aprendidas nunca auto-activadas (§1.9); aplicar-pendientes solo 'Por clasificar'
de meses NO cerrados, idempotente y SELLADO con clasificada_por/at + regla_id
(B-2); RBAC exacto; O1 fail-closed con compensación (estándar C1/B-5).
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
from app.reglas.service import elegir_regla
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient

PWD = "clave-larga-1234"
BASE = "/api/v1/reglas-clasificacion"


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
        ("dir@roddos.com", Role.directivo),
        ("admin@roddos.com", Role.admin),
    ]:
        await repository.create_user(
            User(email=correo, password_hash=passwords.hash_password(PWD), rol=rol)
        )
    await Rubro(
        grupo="otros", nombre="Por clasificar", orden=97, es_sistema=True
    ).insert()
    await Rubro(
        grupo="otros",
        nombre="Recaudo",
        tipo_flujo="ingreso",
        orden=99,
        es_sistema=True,
    ).insert()
    await Rubro(grupo="operacion", nombre="Cafetería", orden=1).insert()
    await Rubro(grupo="operacion", nombre="Transporte", orden=2).insert()
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


async def _rubro(nombre: str) -> Rubro:
    r = await Rubro.find_one(Rubro.nombre == nombre)
    assert r is not None, nombre
    return r


async def _crear(ac, h, patron="Cafetería", rubro=None, tipo="egreso", prioridad=10):
    if rubro is None:
        rubro = await _rubro("Cafetería")
    return await ac.post(
        BASE,
        json={
            "patron": patron,
            "rubro_id": str(rubro.id),
            "tipo_flujo": tipo,
            "prioridad": prioridad,
        },
        headers=h,
    )


# ────────────── elegir_regla (precedencia determinista, unitario) ──────────────


async def test_precedencia_gana_menor_prioridad(api):
    caf = await _rubro("Cafetería")
    tra = await _rubro("Transporte")
    r1 = ReglaClasificacion(
        patron="pago", rubro_id=tra.id, tipo_flujo="egreso", prioridad=5, creada_por="u"
    )
    r2 = ReglaClasificacion(
        patron="cafe", rubro_id=caf.id, tipo_flujo="egreso", prioridad=1, creada_por="u"
    )
    await r1.insert()
    await r2.insert()
    activos = {caf.id, tra.id}
    # Ambas matchean; gana la de prioridad 1 (cafe), no la de 5.
    elegida = elegir_regla("PAGO CAFETERIA LA 14", [r1, r2], activos)
    assert elegida is not None and elegida.id == r2.id


async def test_precedencia_empate_desempata_por_id(api):
    caf = await _rubro("Cafetería")
    tra = await _rubro("Transporte")
    a = ReglaClasificacion(
        patron="pago", rubro_id=caf.id, tipo_flujo="egreso", prioridad=1, creada_por="u"
    )
    b = ReglaClasificacion(
        patron="pag", rubro_id=tra.id, tipo_flujo="egreso", prioridad=1, creada_por="u"
    )
    await a.insert()
    await b.insert()
    activos = {caf.id, tra.id}
    primero = min([a, b], key=lambda r: (r.prioridad, str(r.id)))
    # Determinista: siempre el mismo, pase lo que pase con el orden de entrada.
    assert elegir_regla("pago x", [a, b], activos).id == primero.id
    assert elegir_regla("pago x", [b, a], activos).id == primero.id


async def test_elegir_salta_rubro_inactivo_d2(api):
    caf = await _rubro("Cafetería")
    r = ReglaClasificacion(
        patron="cafe", rubro_id=caf.id, tipo_flujo="egreso", prioridad=1, creada_por="u"
    )
    await r.insert()
    # rubro NO está en el set de activos → la regla se salta (D2).
    assert elegir_regla("CAFETERIA", [r], set()) is None


# ────────────────────────────── POST (crear) ──────────────────────────────


async def test_post_crea_y_emite_regla_creada(api):
    ac, c = api
    h = await _token(ac)
    r = await _crear(ac, h, patron="Café", prioridad=7)
    assert r.status_code == 201
    d = r.json()
    assert d["patron"] == "Café"
    assert d["patron_normalizado"] == "cafe"
    assert d["origen"] == "manual"
    assert d["activa"] is True
    ev = await c["compas_test"]["audit_log"].find_one({"evento": "regla.creada"})
    assert ev is not None and ev["entidad_id"] == d["id"]


async def test_post_patron_2_chars_422(api):
    ac, _ = api
    h = await _token(ac)
    r = await _crear(ac, h, patron="ab")
    assert r.status_code == 422


async def test_post_rubro_de_otro_tipo_409_d1(api):
    # D1: regla de egreso apuntando a 'Recaudo' (ingreso) → 409.
    ac, _ = api
    h = await _token(ac)
    recaudo = await _rubro("Recaudo")
    r = await _crear(ac, h, rubro=recaudo, tipo="egreso")
    assert r.status_code == 409


async def test_post_rubro_inactivo_422_d1(api):
    ac, _ = api
    h = await _token(ac)
    caf = await _rubro("Cafetería")
    caf.activo = False
    await caf.save()
    r = await _crear(ac, h)
    assert r.status_code == 422


async def test_post_rubro_inexistente_404(api):
    ac, _ = api
    h = await _token(ac)
    r = await ac.post(
        BASE,
        json={
            "patron": "cafe",
            "rubro_id": "64b000000000000000000000",
            "tipo_flujo": "egreso",
            "prioridad": 1,
        },
        headers=h,
    )
    assert r.status_code == 404


async def test_post_patron_activo_duplicado_409(api):
    # Unicidad (patron_normalizado, tipo_flujo) activa — "Café" ≡ "cafe".
    ac, _ = api
    h = await _token(ac)
    assert (await _crear(ac, h, patron="Café")).status_code == 201
    r = await _crear(ac, h, patron="cafe", prioridad=99)
    assert r.status_code == 409


async def test_precheck_duplicado_desactivado_no_cuenta(api):
    # La desactivada no bloquea una nueva activa con el mismo patrón. El pre-check
    # se prueba aquí (unitario); el ÍNDICE parcial real, en test_domain_indexes
    # (@requires_real_mongo — mongomock PIERDE el partialFilterExpression al crear
    # el índice vía Beanie y lo aplica como único TOTAL: se tumba aquí para poder
    # coexistir activa+inactiva, que es exactamente el caso del parcial real).
    from app.domain.rubro import TipoFlujo
    from app.reglas.service import _patron_activo_duplicado

    ac, c = api
    await c["compas_test"]["reglas_clasificacion"].drop_index(
        "patron_tipo_activa_unico"
    )
    caf = await _rubro("Cafetería")
    await ReglaClasificacion(
        patron="Café",
        rubro_id=caf.id,
        tipo_flujo="egreso",
        prioridad=1,
        activa=False,
        creada_por="u",
    ).insert()
    assert not await _patron_activo_duplicado("cafe", TipoFlujo.EGRESO)
    await ReglaClasificacion(
        patron="cafe",
        rubro_id=caf.id,
        tipo_flujo="egreso",
        prioridad=2,
        creada_por="u",
    ).insert()
    assert await _patron_activo_duplicado("CAFÉ", TipoFlujo.EGRESO)
    # Otro tipo_flujo no colisiona (la partición D1-ii también parte la unicidad).
    assert not await _patron_activo_duplicado("cafe", TipoFlujo.INGRESO)


# ────────────────────────────── PATCH (editar) ──────────────────────────────


async def test_patch_edita_y_emite_regla_editada(api):
    ac, c = api
    h = await _token(ac)
    rid = (await _crear(ac, h)).json()["id"]
    r = await ac.patch(f"{BASE}/{rid}", json={"prioridad": 3}, headers=h)
    assert r.status_code == 200
    assert r.json()["prioridad"] == 3
    ev = await c["compas_test"]["audit_log"].find_one({"evento": "regla.editada"})
    assert ev is not None
    assert ev["metadata"]["cambios"]["prioridad"] == {"anterior": 10, "nuevo": 3}


async def test_patch_patron_rederiva_normalizado(api):
    ac, _ = api
    h = await _token(ac)
    rid = (await _crear(ac, h)).json()["id"]
    r = await ac.patch(f"{BASE}/{rid}", json={"patron": "Peaje Túnel"}, headers=h)
    assert r.status_code == 200
    assert r.json()["patron_normalizado"] == "peaje tunel"


async def test_patch_rubro_de_otro_tipo_409_d1(api):
    ac, _ = api
    h = await _token(ac)
    rid = (await _crear(ac, h)).json()["id"]
    recaudo = await _rubro("Recaudo")
    r = await ac.patch(f"{BASE}/{rid}", json={"rubro_id": str(recaudo.id)}, headers=h)
    assert r.status_code == 409


async def test_patch_activa_false_422_usa_desactivar(api):
    ac, _ = api
    h = await _token(ac)
    rid = (await _crear(ac, h)).json()["id"]
    r = await ac.patch(f"{BASE}/{rid}", json={"activa": False}, headers=h)
    assert r.status_code == 422


async def test_patch_reactivar_revalida_rubro_b1(api):
    # B-1 Kimi: el rubro pudo desactivarse ENTRE la creación y la reactivación.
    ac, _ = api
    h = await _token(ac)
    rid = (await _crear(ac, h)).json()["id"]
    await ac.post(f"{BASE}/{rid}/desactivar", headers=h)
    caf = await _rubro("Cafetería")
    caf.activo = False
    await caf.save()
    r = await ac.patch(f"{BASE}/{rid}", json={"activa": True}, headers=h)
    assert r.status_code == 409  # activar hacia rubro inactivo, prohibido


async def test_patch_reactivar_ok_emite_editada(api):
    ac, c = api
    h = await _token(ac)
    rid = (await _crear(ac, h)).json()["id"]
    await ac.post(f"{BASE}/{rid}/desactivar", headers=h)
    r = await ac.patch(f"{BASE}/{rid}", json={"activa": True}, headers=h)
    assert r.status_code == 200 and r.json()["activa"] is True
    evs = await c["compas_test"]["audit_log"].count_documents(
        {"evento": "regla.editada"}
    )
    assert evs == 1


# ────────────────────────── desactivar / aprobar ──────────────────────────


async def test_desactivar_emite_regla_desactivada(api):
    ac, c = api
    h = await _token(ac)
    rid = (await _crear(ac, h)).json()["id"]
    r = await ac.post(f"{BASE}/{rid}/desactivar", headers=h)
    assert r.status_code == 200 and r.json()["activa"] is False
    ev = await c["compas_test"]["audit_log"].find_one({"evento": "regla.desactivada"})
    assert ev is not None
    # Ya inactiva → 409 explícito.
    assert (await ac.post(f"{BASE}/{rid}/desactivar", headers=h)).status_code == 409


async def _proponer_aprendida(activa=False) -> ReglaClasificacion:
    caf = await Rubro.find_one(Rubro.nombre == "Cafetería")
    regla = ReglaClasificacion(
        patron="cafeteria",
        rubro_id=caf.id,
        tipo_flujo="egreso",
        prioridad=50,
        origen="aprendida",
        activa=activa,
        creada_por="u1",
    )
    await regla.insert()
    return regla


async def test_aprobar_aprendida_emite_editada_via_aprobacion(api):
    ac, c = api
    h = await _token(ac)
    regla = await _proponer_aprendida()
    r = await ac.post(f"{BASE}/{regla.id}/aprobar", headers=h)
    assert r.status_code == 200 and r.json()["activa"] is True
    ev = await c["compas_test"]["audit_log"].find_one({"evento": "regla.editada"})
    assert ev is not None
    assert ev["metadata"]["cambios"]["activa"] == {"anterior": False, "nuevo": True}
    assert ev["metadata"]["via"] == "aprobacion"


async def test_aprobar_manual_409(api):
    ac, _ = api
    h = await _token(ac)
    rid = (await _crear(ac, h)).json()["id"]  # origen manual
    r = await ac.post(f"{BASE}/{rid}/aprobar", headers=h)
    assert r.status_code == 409


async def test_aprobar_ya_activa_409(api):
    ac, _ = api
    h = await _token(ac)
    regla = await _proponer_aprendida(activa=True)
    r = await ac.post(f"{BASE}/{regla.id}/aprobar", headers=h)
    assert r.status_code == 409


async def test_aprobar_con_rubro_inactivo_409_b1(api):
    # B-1 Kimi: la activación exige rubro existente + activo + tipo coherente.
    ac, _ = api
    h = await _token(ac)
    regla = await _proponer_aprendida()
    caf = await _rubro("Cafetería")
    caf.activo = False
    await caf.save()
    r = await ac.post(f"{BASE}/{regla.id}/aprobar", headers=h)
    assert r.status_code == 409


# ────────────────────────── aplicar-pendientes (B-2) ──────────────────────────


async def _tx_por_clasificar(fecha: str, descripcion: str, tipo="egreso"):
    pc = await Rubro.find_one(Rubro.nombre == "Por clasificar")
    mc = await MesControl.find_one(MesControl.mes == fecha[:7] + "-01")
    tx = Transaccion(
        fecha=fecha,
        descripcion=descripcion,
        valor=Decimal("10000"),
        tipo_flujo=tipo,
        rubro_id=pc.id,
        mes_id=mc.id,
        banco="manual",
        id_banco=f"MAN-{descripcion[:20]}-{fecha}",
    )
    await tx.insert()
    return tx


async def test_aplicar_pendientes_clasifica_y_sella_b2(api):
    ac, _ = api
    h = await _token(ac)
    await _crear(ac, h, patron="cafeteria")
    tx = await _tx_por_clasificar("2026-03-10", "COMPRA CAFETERÍA LA 14")
    r = await ac.post(f"{BASE}/aplicar-pendientes", headers=h)
    assert r.status_code == 200
    assert r.json()["clasificadas"] == 1
    caf = await _rubro("Cafetería")
    despues = await Transaccion.get(tx.id)
    assert despues.rubro_id == caf.id
    assert despues.regla_id is not None  # rastro forense §1.5
    # B-2 (Kimi): sellado por documento — quién disparó el lote y cuándo.
    assert despues.clasificada_por is not None
    assert despues.clasificada_at is not None


async def test_aplicar_pendientes_no_toca_mes_cerrado(api):
    # Regla 4: 'Por clasificar' de un mes CERRADO no se reclasifica.
    ac, _ = api
    h = await _token(ac)
    await _crear(ac, h, patron="cafeteria")
    tx = await _tx_por_clasificar("2026-01-10", "CAFETERIA CENTRO")
    r = await ac.post(f"{BASE}/aplicar-pendientes", headers=h)
    assert r.status_code == 200
    assert r.json()["clasificadas"] == 0
    pc = await _rubro("Por clasificar")
    assert (await Transaccion.get(tx.id)).rubro_id == pc.id  # intacta


async def test_aplicar_pendientes_idempotente_y_no_toca_clasificadas(api):
    ac, _ = api
    h = await _token(ac)
    await _crear(ac, h, patron="cafeteria")
    await _tx_por_clasificar("2026-03-10", "CAFETERIA LA 14")
    r1 = await ac.post(f"{BASE}/aplicar-pendientes", headers=h)
    assert r1.json()["clasificadas"] == 1
    r2 = await ac.post(f"{BASE}/aplicar-pendientes", headers=h)
    assert r2.json()["clasificadas"] == 0  # lo ya clasificado no se toca
    assert r2.json()["sin_match"] == 0


async def test_aplicar_pendientes_sin_match_queda_por_clasificar(api):
    ac, _ = api
    h = await _token(ac)
    await _crear(ac, h, patron="cafeteria")
    tx = await _tx_por_clasificar("2026-03-10", "GASOLINA TEXACO")
    r = await ac.post(f"{BASE}/aplicar-pendientes", headers=h)
    assert r.json()["clasificadas"] == 0 and r.json()["sin_match"] == 1
    pc = await _rubro("Por clasificar")
    assert (await Transaccion.get(tx.id)).rubro_id == pc.id


# ────────────────────────────── RBAC exacto ──────────────────────────────


@pytest.mark.parametrize(
    "email",
    ["consulta@roddos.com", "fin@roddos.com", "dir@roddos.com", "admin@roddos.com"],
)
async def test_get_200_los_cuatro_roles(api, email):
    ac, _ = api
    h = await _token(ac, email)
    assert (await ac.get(BASE, headers=h)).status_code == 200


@pytest.mark.parametrize("email", ["consulta@roddos.com", "dir@roddos.com"])
async def test_mutaciones_403_consulta_y_directivo(api, email):
    ac, _ = api
    hf = await _token(ac)  # financiero prepara una regla
    rid = (await _crear(ac, hf)).json()["id"]
    h = await _token(ac, email)
    assert (await _crear(ac, h, patron="otra")).status_code == 403
    assert (
        await ac.patch(f"{BASE}/{rid}", json={"prioridad": 1}, headers=h)
    ).status_code == 403
    assert (await ac.post(f"{BASE}/{rid}/desactivar", headers=h)).status_code == 403
    assert (await ac.post(f"{BASE}/{rid}/aprobar", headers=h)).status_code == 403
    assert (await ac.post(f"{BASE}/aplicar-pendientes", headers=h)).status_code == 403


# ────────────────────────── O1 fail-closed (B-5 C1) ──────────────────────────


async def test_fail_closed_crear_compensa(api, monkeypatch):
    ac, _ = api
    h = await _token(ac)

    async def _boom(*a, **k):
        raise RuntimeError("audit caído")

    monkeypatch.setattr("app.reglas.service.emit_audit", _boom)
    with pytest.raises(RuntimeError):
        await _crear(ac, h)
    assert await ReglaClasificacion.find_one() is None


async def test_fail_closed_aprobar_compensa(api, monkeypatch):
    ac, _ = api
    h = await _token(ac)
    regla = await _proponer_aprendida()

    async def _boom(*a, **k):
        raise RuntimeError("audit caído")

    monkeypatch.setattr("app.reglas.service.emit_audit", _boom)
    with pytest.raises(RuntimeError):
        await ac.post(f"{BASE}/{regla.id}/aprobar", headers=h)
    assert (await ReglaClasificacion.get(regla.id)).activa is False  # revertido


async def test_fail_closed_desactivar_compensa(api, monkeypatch):
    ac, _ = api
    h = await _token(ac)
    rid = (await _crear(ac, h)).json()["id"]

    async def _boom(*a, **k):
        raise RuntimeError("audit caído")

    monkeypatch.setattr("app.reglas.service.emit_audit", _boom)
    with pytest.raises(RuntimeError):
        await ac.post(f"{BASE}/{rid}/desactivar", headers=h)
    regla = await ReglaClasificacion.find_one()
    assert regla.activa is True  # revertido
