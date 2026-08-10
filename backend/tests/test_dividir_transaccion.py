# backend/tests/test_dividir_transaccion.py
"""PTS6-B — POST /api/v1/transacciones/{id}/dividir + /deshacer-division (CR división).

MARCADO PARA AUDITORÍA KIMI (gate PTS6-B; clasificación de plata).

Una transacción bancaria real puede cubrir varios conceptos (caso Luis Miguel 2026-08:
$20.123.787,47 = $14M garantía Auteco + $6.123.787,47 préstamo). La división vive en la
superficie de CLASIFICACIÓN (partes[{rubro,valor}] que suman EXACTO el total): `valor`,
`fecha`, `banco`, `id_banco` quedan INTACTOS (Spec §2.2 — asserts explícitos). Las
agregaciones por rubro expanden partes; las sumas totales no cambian por construcción.
Eventos nuevos (CR regla 11): `transaccion.dividida` y `transaccion.division_deshecha`.
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
from app.control.service import _egresos_por_rubro
from app.domain import DOMAIN_DOCUMENTS
from app.domain.mes_control import EstadoMes, MesControl
from app.domain.rubro import Rubro
from app.domain.transaccion import Transaccion
from app.main import create_app
from app.metas_ingreso.service import ingreso_real
from app.presupuesto.service import _ejecutados_por_rubro_mes
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
    # Taxonomía mínima del caso real + bordes.
    await Rubro(
        grupo="otros", nombre="Por clasificar", orden=97, es_sistema=True
    ).insert()
    await Rubro(grupo="deudas_obligaciones", nombre="Garantía cupo", orden=1).insert()
    await Rubro(grupo="deudas_obligaciones", nombre="Préstamos", orden=2).insert()
    await Rubro(
        grupo="operacion", nombre="Rubro inactivo", orden=3, activo=False
    ).insert()
    await Rubro(
        grupo="ingresos_operativos",
        nombre="Recaudo de cartera",
        tipo_flujo="ingreso",
        orden=1,
        es_sistema=True,
    ).insert()
    await Rubro(
        grupo="ingresos_operativos",
        nombre="Cuotas iniciales",
        tipo_flujo="ingreso",
        orden=2,
    ).insert()
    await Rubro(
        grupo="otros",
        nombre="Reversas y devoluciones",
        tipo_flujo="ingreso",
        orden=98,
        es_sistema=True,
    ).insert()
    # Sistema EGRESO fuera de la lista blanca (guard P0-1): destino inválido de parte.
    await Rubro(
        grupo="otros", nombre="Ajuste de conciliación", orden=99, es_sistema=True
    ).insert()
    await MesControl(mes="2026-08-01", saldo_inicial_caja=Decimal("0")).insert()
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
    assert r is not None
    return r


async def _tx_luis_miguel(fecha="2026-08-04") -> Transaccion:
    prestamos = await _rubro("Préstamos")
    mc = await MesControl.find_one(MesControl.mes == fecha[:7] + "-01")
    tx = Transaccion(
        fecha=fecha,
        descripcion="Envío a cuenta bancaria Luis miguel becerra ferro — Préstamos",
        valor=Decimal("20123787.47"),
        tipo_flujo="egreso",
        rubro_id=prestamos.id,
        mes_id=mc.id,
        banco="global66",
        id_banco="38009969|1",
    )
    await tx.insert()
    return tx


def _partes_ok(garantia: Rubro, prestamos: Rubro) -> list[dict]:
    return [
        {"rubro_id": str(garantia.id), "valor": "14000000.00"},
        {"rubro_id": str(prestamos.id), "valor": "6123787.47"},
    ]


async def _eventos(c, tipo: str) -> list[dict]:
    return await c["compas_test"]["audit_log"].find({"evento": tipo}).to_list(None)


# ── dividir: camino feliz ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dividir_ok_partes_exactas_e_inmutables_intactos(api):
    ac, c = api
    h = await _token(ac)
    tx = await _tx_luis_miguel()
    garantia, prestamos = await _rubro("Garantía cupo"), await _rubro("Préstamos")

    r = await ac.post(
        f"/api/v1/transacciones/{tx.id}/dividir",
        json={"partes": _partes_ok(garantia, prestamos)},
        headers=h,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dividida"] is True
    assert [p["valor"] for p in body["partes"]] == ["14000000.00", "6123787.47"]

    tx2 = await Transaccion.get(tx.id)
    # Spec §2.2: inmutables INTACTOS.
    assert tx2.valor == Decimal("20123787.47")
    assert tx2.id_banco == "38009969|1"
    assert tx2.fecha == "2026-08-04"
    assert tx2.banco.value == "global66"
    # Rubro primario = la parte MAYOR (Garantía cupo, 14M).
    assert tx2.rubro_id == garantia.id
    assert tx2.rubro_pre_division == prestamos.id
    assert len(tx2.partes) == 2
    assert sum(p.valor for p in tx2.partes) == tx2.valor

    evs = await _eventos(c, "transaccion.dividida")
    assert len(evs) == 1
    meta = evs[0]["metadata"]
    assert meta["valor_total"] == "20123787.47"
    assert len(meta["partes"]) == 2


@pytest.mark.asyncio
async def test_dividir_suma_inexacta_422_sin_cambios(api):
    ac, _ = api
    h = await _token(ac)
    tx = await _tx_luis_miguel()
    garantia, prestamos = await _rubro("Garantía cupo"), await _rubro("Préstamos")
    r = await ac.post(
        f"/api/v1/transacciones/{tx.id}/dividir",
        json={
            "partes": [
                {"rubro_id": str(garantia.id), "valor": "14000000.00"},
                {"rubro_id": str(prestamos.id), "valor": "6123787.00"},  # −0,47
            ]
        },
        headers=h,
    )
    assert r.status_code == 422
    tx2 = await Transaccion.get(tx.id)
    assert tx2.partes is None and tx2.rubro_id == prestamos.id


@pytest.mark.asyncio
async def test_dividir_menos_de_dos_partes_422(api):
    ac, _ = api
    h = await _token(ac)
    tx = await _tx_luis_miguel()
    garantia = await _rubro("Garantía cupo")
    r = await ac.post(
        f"/api/v1/transacciones/{tx.id}/dividir",
        json={"partes": [{"rubro_id": str(garantia.id), "valor": "20123787.47"}]},
        headers=h,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_dividir_validaciones_de_rubro_por_parte(api):
    ac, _ = api
    h = await _token(ac)
    garantia = await _rubro("Garantía cupo")

    # rubro inexistente → 404
    tx = await _tx_luis_miguel()
    r = await ac.post(
        f"/api/v1/transacciones/{tx.id}/dividir",
        json={
            "partes": [
                {"rubro_id": str(garantia.id), "valor": "14000000.00"},
                {"rubro_id": "6a7a3c1e508cee7551f9ffff", "valor": "6123787.47"},
            ]
        },
        headers=h,
    )
    assert r.status_code == 404

    # rubro inactivo → 422
    inactivo = await Rubro.find_one(Rubro.nombre == "Rubro inactivo")
    r = await ac.post(
        f"/api/v1/transacciones/{tx.id}/dividir",
        json={
            "partes": [
                {"rubro_id": str(garantia.id), "valor": "14000000.00"},
                {"rubro_id": str(inactivo.id), "valor": "6123787.47"},
            ]
        },
        headers=h,
    )
    assert r.status_code == 422

    # tipo_flujo incoherente (rubro ingreso en tx egreso) → 409
    ingreso = await _rubro("Cuotas iniciales")
    r = await ac.post(
        f"/api/v1/transacciones/{tx.id}/dividir",
        json={
            "partes": [
                {"rubro_id": str(garantia.id), "valor": "14000000.00"},
                {"rubro_id": str(ingreso.id), "valor": "6123787.47"},
            ]
        },
        headers=h,
    )
    assert r.status_code == 409

    # rubro de sistema fuera de la lista blanca (guard estructural P0-1) → 422.
    # OJO: 'Por clasificar' SÍ es clasificable (whitelist), por eso el caso usa
    # 'Ajuste de conciliación'.
    sistema = await Rubro.find_one(Rubro.nombre == "Ajuste de conciliación")
    r = await ac.post(
        f"/api/v1/transacciones/{tx.id}/dividir",
        json={
            "partes": [
                {"rubro_id": str(garantia.id), "valor": "14000000.00"},
                {"rubro_id": str(sistema.id), "valor": "6123787.47"},
            ]
        },
        headers=h,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_dividir_mes_cerrado_409(api):
    ac, _ = api
    h = await _token(ac)
    prestamos = await _rubro("Préstamos")
    mc = await MesControl.find_one(MesControl.mes == "2026-01-01")
    tx = Transaccion(
        fecha="2026-01-15",
        descripcion="pago viejo",
        valor=Decimal("100.00"),
        tipo_flujo="egreso",
        rubro_id=prestamos.id,
        mes_id=mc.id,
        banco="manual",
        id_banco="MAN-TESTCERRADO000000000001",
    )
    await tx.insert()
    garantia = await _rubro("Garantía cupo")
    r = await ac.post(
        f"/api/v1/transacciones/{tx.id}/dividir",
        json={
            "partes": [
                {"rubro_id": str(garantia.id), "valor": "60.00"},
                {"rubro_id": str(prestamos.id), "valor": "40.00"},
            ]
        },
        headers=h,
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_redividir_409_y_deshacer_restaura(api):
    ac, c = api
    h = await _token(ac)
    tx = await _tx_luis_miguel()
    garantia, prestamos = await _rubro("Garantía cupo"), await _rubro("Préstamos")
    r = await ac.post(
        f"/api/v1/transacciones/{tx.id}/dividir",
        json={"partes": _partes_ok(garantia, prestamos)},
        headers=h,
    )
    assert r.status_code == 200

    # re-dividir sin deshacer → 409
    r = await ac.post(
        f"/api/v1/transacciones/{tx.id}/dividir",
        json={"partes": _partes_ok(garantia, prestamos)},
        headers=h,
    )
    assert r.status_code == 409

    # deshacer → restaura rubro original y limpia partes
    r = await ac.post(f"/api/v1/transacciones/{tx.id}/deshacer-division", headers=h)
    assert r.status_code == 200, r.text
    tx2 = await Transaccion.get(tx.id)
    assert tx2.partes is None
    assert tx2.rubro_id == prestamos.id  # el rubro pre-división
    assert tx2.rubro_pre_division is None
    assert tx2.valor == Decimal("20123787.47")
    assert len(await _eventos(c, "transaccion.division_deshecha")) == 1

    # deshacer sin división → 409
    r = await ac.post(f"/api/v1/transacciones/{tx.id}/deshacer-division", headers=h)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_dividir_requiere_permiso_403(api):
    ac, _ = api
    h = await _token(ac, "consulta@roddos.com")
    tx = await _tx_luis_miguel()
    garantia, prestamos = await _rubro("Garantía cupo"), await _rubro("Préstamos")
    r = await ac.post(
        f"/api/v1/transacciones/{tx.id}/dividir",
        json={"partes": _partes_ok(garantia, prestamos)},
        headers=h,
    )
    assert r.status_code == 403


# ── agregaciones por rubro: expanden partes; los totales no cambian ─────────


@pytest.mark.asyncio
async def test_control_egresos_por_rubro_expande_partes(api):
    ac, _ = api
    h = await _token(ac)
    tx = await _tx_luis_miguel()
    garantia, prestamos = await _rubro("Garantía cupo"), await _rubro("Préstamos")
    r = await ac.post(
        f"/api/v1/transacciones/{tx.id}/dividir",
        json={"partes": _partes_ok(garantia, prestamos)},
        headers=h,
    )
    assert r.status_code == 200
    por_rubro = await _egresos_por_rubro(tx.mes_id)
    assert por_rubro[str(garantia.id)] == Decimal("14000000.00")
    assert por_rubro[str(prestamos.id)] == Decimal("6123787.47")
    assert sum(por_rubro.values()) == Decimal("20123787.47")  # total conservado


@pytest.mark.asyncio
async def test_prom3m_ejecutados_por_rubro_mes_expande_partes(api):
    ac, _ = api
    # tx dividida dentro de un mes que luego CIERRA: prom_3m debe ver las partes.
    garantia, prestamos = await _rubro("Garantía cupo"), await _rubro("Préstamos")
    mc = await MesControl.find_one(MesControl.mes == "2026-01-01")
    from app.domain.transaccion import ParteClasificacion

    tx = Transaccion(
        fecha="2026-01-10",
        descripcion="mixta histórica",
        valor=Decimal("1000.00"),
        tipo_flujo="egreso",
        rubro_id=garantia.id,
        mes_id=mc.id,
        banco="manual",
        id_banco="MAN-TESTPROM3M000000000001",
        partes=[
            ParteClasificacion(rubro_id=garantia.id, valor=Decimal("600.00")),
            ParteClasificacion(rubro_id=prestamos.id, valor=Decimal("400.00")),
        ],
    )
    await tx.insert()
    out = await _ejecutados_por_rubro_mes([mc.id], [garantia.id, prestamos.id])
    assert out[(str(garantia.id), str(mc.id))] == Decimal("600.00")
    assert out[(str(prestamos.id), str(mc.id))] == Decimal("400.00")


@pytest.mark.asyncio
async def test_metas_ingreso_real_expande_partes_y_excluye_neutro_por_parte(api):
    # El guard P0-1 impide clasificar HACIA un neutro por el endpoint (Reversas no
    # está en la lista blanca) — el caso se arma directo en el documento, que es el
    # estado que `ingreso_real` debe saber leer (exclusión de neutros POR PARTE).
    ac, _ = api
    recaudo = await _rubro("Recaudo de cartera")
    reversas = await _rubro("Reversas y devoluciones")
    mc = await MesControl.find_one(MesControl.mes == "2026-08-01")
    from app.domain.transaccion import ParteClasificacion

    tx = Transaccion(
        fecha="2026-08-03",
        descripcion="consignación mixta",
        valor=Decimal("100000.00"),
        tipo_flujo="ingreso",
        rubro_id=recaudo.id,
        mes_id=mc.id,
        banco="global66",
        id_banco="INGMIX|1",
        partes=[
            ParteClasificacion(rubro_id=recaudo.id, valor=Decimal("60000.00")),
            ParteClasificacion(rubro_id=reversas.id, valor=Decimal("40000.00")),
        ],
    )
    await tx.insert()
    # Solo la parte NO neutra cuenta como ingreso real del mes.
    assert await ingreso_real("2026-08") == Decimal("60000.00")

    # Y por el endpoint, una división de ingreso entre rubros VÁLIDOS funciona:
    h = await _token(ac)
    iniciales = await _rubro("Cuotas iniciales")
    tx2 = Transaccion(
        fecha="2026-08-04",
        descripcion="consignación mixta 2",
        valor=Decimal("50000.00"),
        tipo_flujo="ingreso",
        rubro_id=recaudo.id,
        mes_id=mc.id,
        banco="global66",
        id_banco="INGMIX|2",
    )
    await tx2.insert()
    r = await ac.post(
        f"/api/v1/transacciones/{tx2.id}/dividir",
        json={
            "partes": [
                {"rubro_id": str(recaudo.id), "valor": "30000.00"},
                {"rubro_id": str(iniciales.id), "valor": "20000.00"},
            ]
        },
        headers=h,
    )
    assert r.status_code == 200, r.text
    assert await ingreso_real("2026-08") == Decimal("110000.00")  # 60k + 50k
