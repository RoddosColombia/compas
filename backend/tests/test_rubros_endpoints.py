# backend/tests/test_rubros_endpoints.py
"""C1 categorías administrables — /api/v1/rubros (GO Kimi PLAN-I 9.2, CR-S4).

MARCADO PARA AUDITORÍA KIMI (gate de código I-PR1; lista de tests del §5 del
veredicto PLAN-I).

Reglas cubiertas:
  - CR-S4: `rubro.creado`/`rubro.editado` (+ `rubro.desactivado` v1.0) y RBAC
    `rubros:gestionar` = {financiero, admin}; consulta/directivo → 403 en mutar.
  - Sistema inmutable (§2.2): PATCH y desactivar sobre los 3 rubros de sistema → 409.
  - D1/B-1: `tipo_flujo` congelado si el rubro tiene Transaccion O PresupuestoLinea
    (referencias, no solo movimientos); sin referencias → editable.
  - D2/B-2: baja lógica; desactivar con movimientos → 200 e histórico intacto.
  - B-3: reactivación = PATCH activo:true → `rubro.editado` {activo false→true};
    PATCH activo:false → 422 (la baja va por POST /desactivar, evento propio).
  - B-5: auditoría fail-closed estilo O1 — si el emit falla, se compensa (el rubro
    creado se borra / el campo editado se revierte).
  - Único (grupo, nombre) → 409 (pre-check en mongomock; índice real en el gate
    real-mongo de dedup).
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
from app.domain.mes_control import MesControl
from app.domain.presupuesto import PresupuestoLinea
from app.domain.rubro import Rubro, TipoFlujo
from app.domain.transaccion import Transaccion
from app.main import create_app
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient

PWD = "clave-larga-1234"

SISTEMA = ["Por clasificar", "Ajuste de conciliación", "Recaudo"]


@pytest_asyncio.fixture
async def api(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    monkeypatch.setenv("COOKIE_SECURE", "False")
    monkeypatch.delenv("RUN_SCHEDULER", raising=False)
    get_settings.cache_clear()

    app = create_app()
    # tz_aware=True como el Motor real: los datetime re-leídos vuelven UTC-aware.
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
    # Semilla mínima: 3 de sistema + 2 operativos.
    await Rubro(
        grupo="otros", nombre="Por clasificar", orden=97, es_sistema=True
    ).insert()
    await Rubro(
        grupo="otros", nombre="Ajuste de conciliación", orden=98, es_sistema=True
    ).insert()
    await Rubro(
        grupo="otros",
        nombre="Recaudo",
        tipo_flujo="ingreso",
        orden=99,
        es_sistema=True,
    ).insert()
    await Rubro(grupo="operacion", nombre="Arriendos", orden=1).insert()
    await Rubro(grupo="operacion", nombre="Cafetería", orden=2).insert()
    await MesControl(mes="2026-03-01", saldo_inicial_caja=Decimal("0")).insert()

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


async def _referencia_tx(rubro: Rubro) -> Transaccion:
    mc = await MesControl.find_one(MesControl.mes == "2026-03-01")
    tx = Transaccion(
        fecha="2026-03-15",
        descripcion="EGRESO TEST",
        valor=Decimal("10000"),
        tipo_flujo=TipoFlujo.EGRESO,
        rubro_id=rubro.id,
        mes_id=mc.id,
        banco=Banco.MANUAL,
        id_banco="MAN-TEST0000000000000000000001",
    )
    await tx.insert()
    return tx


async def _referencia_linea(rubro: Rubro) -> PresupuestoLinea:
    mc = await MesControl.find_one(MesControl.mes == "2026-03-01")
    ln = PresupuestoLinea(
        mes_id=mc.id,
        rubro_id=rubro.id,
        monto_sugerido=Decimal("100"),
        prom_3m=Decimal("100"),
        tendencia_mes=Decimal("0"),
        crec_pct=Decimal("0"),
        historia_incompleta=True,
    )
    await ln.insert()
    return ln


# ────────────────────────────── GET ──────────────────────────────


async def test_get_lista_ordenada(api):
    ac, _ = api
    h = await _token(ac)
    r = await ac.get("/api/v1/rubros", headers=h)
    assert r.status_code == 200
    d = r.json()
    assert [x["nombre"] for x in d if x["grupo"] == "operacion"] == [
        "Arriendos",
        "Cafetería",
    ]
    campos = {
        "id",
        "grupo",
        "nombre",
        "tipo_flujo",
        "codigo",
        "tipo",
        "orden",
        "activo",
        "es_sistema",
    }
    assert campos <= set(d[0].keys())


async def test_post_crea_con_codigo_y_tipo(api):
    # ARQUITECTURA_PRESUPUESTAL: código jerárquico + Fijo/Variable en el alta.
    ac, _ = api
    h = await _token(ac)
    r = await ac.post(
        "/api/v1/rubros",
        json={
            "grupo": "operacion",
            "nombre": "Freelance",
            "tipo_flujo": "egreso",
            "codigo": "2140",
            "tipo": "variable",
        },
        headers=h,
    )
    assert r.status_code == 201
    body = r.json()
    assert body["codigo"] == "2140"
    assert body["tipo"] == "variable"


async def test_patch_edita_tipo_fijo_variable(api):
    ac, _ = api
    h = await _token(ac)
    arr = await _rubro("Arriendos")
    r = await ac.patch(
        f"/api/v1/rubros/{arr.id}",
        json={"codigo": "2010", "tipo": "fijo"},
        headers=h,
    )
    assert r.status_code == 200
    assert r.json()["tipo"] == "fijo" and r.json()["codigo"] == "2010"


async def test_get_filtra_por_grupo_y_activo(api):
    ac, _ = api
    h = await _token(ac)
    r = await ac.get("/api/v1/rubros?grupo=operacion", headers=h)
    assert {x["grupo"] for x in r.json()} == {"operacion"}
    arr = await _rubro("Arriendos")
    arr.activo = False
    await arr.save()
    r = await ac.get("/api/v1/rubros?activo=true", headers=h)
    assert "Arriendos" not in [x["nombre"] for x in r.json()]
    r = await ac.get("/api/v1/rubros?activo=false", headers=h)
    assert [x["nombre"] for x in r.json()] == ["Arriendos"]


async def test_get_grupo_invalido_422(api):
    ac, _ = api
    h = await _token(ac)
    r = await ac.get("/api/v1/rubros?grupo=inventado", headers=h)
    assert r.status_code == 422


@pytest.mark.parametrize(
    "email",
    [
        "consulta@roddos.com",
        "fin@roddos.com",
        "dir@roddos.com",
        "admin@roddos.com",
    ],
)
async def test_get_200_los_cuatro_roles(api, email):
    ac, _ = api
    h = await _token(ac, email)
    assert (await ac.get("/api/v1/rubros", headers=h)).status_code == 200


# ────────────────────────────── POST (crear) ──────────────────────────────


async def test_post_crea_con_orden_max_grupo_mas_1_y_emite_creado(api):
    ac, c = api
    h = await _token(ac)
    r = await ac.post(
        "/api/v1/rubros",
        # RF-F9: codigo + tipo obligatorios al crear categoría.
        json={
            "grupo": "operacion",
            "nombre": "Freelance",
            "tipo_flujo": "egreso",
            "codigo": "2140",
            "tipo": "variable",
        },
        headers=h,
    )
    assert r.status_code == 201
    d = r.json()
    assert d["orden"] == 3  # máx(operacion)=2 → 3
    assert d["activo"] is True and d["es_sistema"] is False
    ev = await c["compas_test"]["audit_log"].find_one({"evento": "rubro.creado"})
    assert ev is not None
    assert ev["entidad_id"] == d["id"]
    assert ev["metadata"]["nombre"] == "Freelance"


async def test_post_grupo_vacio_arranca_en_1(api):
    ac, _ = api
    h = await _token(ac)
    r = await ac.post(
        "/api/v1/rubros",
        json={
            "grupo": "nomina",
            "nombre": "Sueldos",
            "tipo_flujo": "egreso",
            "codigo": "3011",
            "tipo": "fijo",
        },
        headers=h,
    )
    assert r.status_code == 201
    assert r.json()["orden"] == 1


async def test_post_duplicado_409(api):
    ac, _ = api
    h = await _token(ac)
    r = await ac.post(
        "/api/v1/rubros",
        json={
            "grupo": "operacion",
            "nombre": "Arriendos",
            "tipo_flujo": "egreso",
            "codigo": "2011",
            "tipo": "fijo",
        },
        headers=h,
    )
    assert r.status_code == 409


async def test_post_mismo_nombre_en_otro_grupo_ok(api):
    # El índice es (grupo, nombre): 'Arriendos' puede existir en otro grupo.
    ac, _ = api
    h = await _token(ac)
    r = await ac.post(
        "/api/v1/rubros",
        json={
            "grupo": "otros",
            "nombre": "Arriendos",
            "tipo_flujo": "egreso",
            "codigo": "5099",
            "tipo": "variable",
        },
        headers=h,
    )
    assert r.status_code == 201


async def test_post_grupo_invalido_422(api):
    ac, _ = api
    h = await _token(ac)
    r = await ac.post(
        "/api/v1/rubros",
        json={"grupo": "inventado", "nombre": "X", "tipo_flujo": "egreso"},
        headers=h,
    )
    assert r.status_code == 422


# ────────────────────────────── PATCH (editar) ──────────────────────────────


async def test_patch_nombre_orden_emite_editado_con_cambios(api):
    ac, c = api
    h = await _token(ac)
    arr = await _rubro("Arriendos")
    r = await ac.patch(
        f"/api/v1/rubros/{arr.id}",
        json={"nombre": "Arriendos sede", "orden": 7},
        headers=h,
    )
    assert r.status_code == 200
    assert r.json()["nombre"] == "Arriendos sede"
    assert r.json()["orden"] == 7
    ev = await c["compas_test"]["audit_log"].find_one({"evento": "rubro.editado"})
    assert ev is not None
    assert ev["metadata"]["cambios"]["nombre"] == {
        "anterior": "Arriendos",
        "nuevo": "Arriendos sede",
    }
    assert ev["metadata"]["cambios"]["orden"] == {"anterior": 1, "nuevo": 7}


async def test_patch_nombre_duplicado_409(api):
    ac, _ = api
    h = await _token(ac)
    arr = await _rubro("Arriendos")
    r = await ac.patch(
        f"/api/v1/rubros/{arr.id}", json={"nombre": "Cafetería"}, headers=h
    )
    assert r.status_code == 409


async def test_patch_sin_cambios_422(api):
    ac, _ = api
    h = await _token(ac)
    arr = await _rubro("Arriendos")
    r = await ac.patch(f"/api/v1/rubros/{arr.id}", json={}, headers=h)
    assert r.status_code == 422
    # Mismo valor actual → tampoco hay cambio efectivo.
    r = await ac.patch(
        f"/api/v1/rubros/{arr.id}", json={"nombre": "Arriendos"}, headers=h
    )
    assert r.status_code == 422


async def test_patch_404_y_id_invalido_422(api):
    ac, _ = api
    h = await _token(ac)
    r = await ac.patch(
        "/api/v1/rubros/64b000000000000000000000", json={"orden": 9}, headers=h
    )
    assert r.status_code == 404
    r = await ac.patch("/api/v1/rubros/no-es-oid", json={"orden": 9}, headers=h)
    assert r.status_code == 422


# ── D1/B-1: tipo_flujo congelado con referencias ──


async def test_patch_tipo_flujo_con_transaccion_409(api):
    ac, _ = api
    h = await _token(ac)
    arr = await _rubro("Arriendos")
    await _referencia_tx(arr)
    r = await ac.patch(
        f"/api/v1/rubros/{arr.id}", json={"tipo_flujo": "ingreso"}, headers=h
    )
    assert r.status_code == 409


async def test_patch_tipo_flujo_con_linea_presupuesto_409(api):
    # B-1: la guarda es "tiene referencias", no solo "tiene transacciones".
    ac, _ = api
    h = await _token(ac)
    arr = await _rubro("Arriendos")
    await _referencia_linea(arr)
    r = await ac.patch(
        f"/api/v1/rubros/{arr.id}", json={"tipo_flujo": "ingreso"}, headers=h
    )
    assert r.status_code == 409


async def test_patch_tipo_flujo_sin_referencias_200(api):
    ac, _ = api
    h = await _token(ac)
    arr = await _rubro("Arriendos")
    r = await ac.patch(
        f"/api/v1/rubros/{arr.id}", json={"tipo_flujo": "ingreso"}, headers=h
    )
    assert r.status_code == 200
    assert r.json()["tipo_flujo"] == "ingreso"


async def test_patch_nombre_editable_aun_con_referencias(api):
    # B-1: nombre/orden editables SIEMPRE (no afectan cómputo).
    ac, _ = api
    h = await _token(ac)
    arr = await _rubro("Arriendos")
    await _referencia_tx(arr)
    r = await ac.patch(
        f"/api/v1/rubros/{arr.id}", json={"nombre": "Arriendos sede"}, headers=h
    )
    assert r.status_code == 200


# ────────────────────── Sistema inmutable (parametrizado) ──────────────────────


@pytest.mark.parametrize("nombre", SISTEMA)
async def test_patch_sistema_409(api, nombre):
    ac, _ = api
    h = await _token(ac)
    r = await _rubro(nombre)
    resp = await ac.patch(f"/api/v1/rubros/{r.id}", json={"orden": 50}, headers=h)
    assert resp.status_code == 409


@pytest.mark.parametrize("nombre", SISTEMA)
async def test_desactivar_sistema_409(api, nombre):
    ac, _ = api
    h = await _token(ac)
    r = await _rubro(nombre)
    resp = await ac.post(f"/api/v1/rubros/{r.id}/desactivar", headers=h)
    assert resp.status_code == 409
    assert (await _rubro(nombre)).activo is True


# ────────────────────────────── Desactivar / reactivar ──────────────────────────────


async def test_desactivar_ok_emite_desactivado(api):
    ac, c = api
    h = await _token(ac)
    arr = await _rubro("Arriendos")
    r = await ac.post(f"/api/v1/rubros/{arr.id}/desactivar", headers=h)
    assert r.status_code == 200
    assert r.json()["activo"] is False
    ev = await c["compas_test"]["audit_log"].find_one({"evento": "rubro.desactivado"})
    assert ev is not None
    assert ev["entidad_id"] == str(arr.id)


async def test_desactivar_con_movimientos_200_historico_intacto(api):
    # D2: baja lógica; las transacciones permanecen en la categoría inactiva.
    ac, _ = api
    h = await _token(ac)
    arr = await _rubro("Arriendos")
    tx = await _referencia_tx(arr)
    r = await ac.post(f"/api/v1/rubros/{arr.id}/desactivar", headers=h)
    assert r.status_code == 200
    tx_despues = await Transaccion.get(tx.id)
    assert tx_despues is not None
    assert tx_despues.rubro_id == arr.id  # histórico intacto (regla 4)


async def test_desactivar_ya_inactivo_409(api):
    ac, _ = api
    h = await _token(ac)
    arr = await _rubro("Arriendos")
    await ac.post(f"/api/v1/rubros/{arr.id}/desactivar", headers=h)
    r = await ac.post(f"/api/v1/rubros/{arr.id}/desactivar", headers=h)
    assert r.status_code == 409


async def test_reactivar_por_patch_activo_true_emite_editado(api):
    # B-3: reactivación = PATCH activo:true → rubro.editado {activo false→true};
    # sin un 34.º evento (CR-S4 queda en +2).
    ac, c = api
    h = await _token(ac)
    arr = await _rubro("Arriendos")
    await ac.post(f"/api/v1/rubros/{arr.id}/desactivar", headers=h)
    r = await ac.patch(f"/api/v1/rubros/{arr.id}", json={"activo": True}, headers=h)
    assert r.status_code == 200
    assert r.json()["activo"] is True
    ev = await c["compas_test"]["audit_log"].find_one({"evento": "rubro.editado"})
    assert ev is not None
    assert ev["metadata"]["cambios"]["activo"] == {"anterior": False, "nuevo": True}


async def test_patch_activo_false_422_usa_desactivar(api):
    # B-3: la baja va por POST /desactivar (evento rubro.desactivado propio).
    ac, _ = api
    h = await _token(ac)
    arr = await _rubro("Arriendos")
    r = await ac.patch(f"/api/v1/rubros/{arr.id}", json={"activo": False}, headers=h)
    assert r.status_code == 422


# ────────────────────────────── RBAC exacto ──────────────────────────────


@pytest.mark.parametrize("email", ["consulta@roddos.com", "dir@roddos.com"])
async def test_mutaciones_403_consulta_y_directivo(api, email):
    ac, _ = api
    h = await _token(ac, email)
    arr = await _rubro("Arriendos")
    body = {"grupo": "otros", "nombre": "Nuevo", "tipo_flujo": "egreso"}
    assert (await ac.post("/api/v1/rubros", json=body, headers=h)).status_code == 403
    assert (
        await ac.patch(f"/api/v1/rubros/{arr.id}", json={"orden": 9}, headers=h)
    ).status_code == 403
    assert (
        await ac.post(f"/api/v1/rubros/{arr.id}/desactivar", headers=h)
    ).status_code == 403


@pytest.mark.parametrize("email", ["fin@roddos.com", "admin@roddos.com"])
async def test_mutaciones_ok_financiero_y_admin(api, email):
    ac, _ = api
    h = await _token(ac, email)
    # RF-F9: codigo + tipo obligatorios al crear categoría.
    body = {
        "grupo": "otros",
        "nombre": f"Nuevo {email}",
        "tipo_flujo": "egreso",
        "codigo": "5088",
        "tipo": "variable",
    }
    assert (await ac.post("/api/v1/rubros", json=body, headers=h)).status_code == 201


# ────────────────────────────── B-5: fail-closed O1 ──────────────────────────────


# El transport ASGI de httpx RE-LANZA las excepciones no manejadas de la app
# (raise_app_exceptions=True); en producción Starlette las convierte en 500.
# Lo que fija el test es la COMPENSACIÓN (B-5), no el status.


async def test_fail_closed_crear_compensa(api, monkeypatch):
    # B-5: si el emit de rubro.creado falla, el rubro creado se BORRA (compensación).
    ac, _ = api
    h = await _token(ac)

    async def _boom(*a, **k):
        raise RuntimeError("audit caído")

    monkeypatch.setattr("app.rubros.service.emit_audit", _boom)
    with pytest.raises(RuntimeError):
        await ac.post(
            "/api/v1/rubros",
            json={
                "grupo": "otros",
                "nombre": "Fantasma",
                "tipo_flujo": "egreso",
                "codigo": "5077",
                "tipo": "variable",
            },
            headers=h,
        )
    assert await Rubro.find_one(Rubro.nombre == "Fantasma") is None


async def test_fail_closed_editar_compensa(api, monkeypatch):
    ac, _ = api
    h = await _token(ac)
    arr = await _rubro("Arriendos")

    async def _boom(*a, **k):
        raise RuntimeError("audit caído")

    monkeypatch.setattr("app.rubros.service.emit_audit", _boom)
    with pytest.raises(RuntimeError):
        await ac.patch(
            f"/api/v1/rubros/{arr.id}", json={"nombre": "Efímero"}, headers=h
        )
    assert (await Rubro.get(arr.id)).nombre == "Arriendos"  # revertido


async def test_fail_closed_desactivar_compensa(api, monkeypatch):
    ac, _ = api
    h = await _token(ac)
    arr = await _rubro("Arriendos")

    async def _boom(*a, **k):
        raise RuntimeError("audit caído")

    monkeypatch.setattr("app.rubros.service.emit_audit", _boom)
    with pytest.raises(RuntimeError):
        await ac.post(f"/api/v1/rubros/{arr.id}/desactivar", headers=h)
    assert (await Rubro.get(arr.id)).activo is True  # revertido
