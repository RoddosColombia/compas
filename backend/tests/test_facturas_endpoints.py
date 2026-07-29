# backend/tests/test_facturas_endpoints.py
"""IVA C11 (PR-2a) — /api/v1/facturas (carga de facturas + liquidación cuatrimestral).

RBAC: GET con `dashboard:leer` (todos); mutaciones con `iva:gestionar` = {financiero,
admin} → consulta/directivo reciben 403. Montos como string (regla 1). La liquidación
se calcula en el backend y se sirve por GET /facturas/liquidacion (lo consume la vista).
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
        ("admin@roddos.com", Role.admin),
    ]:
        await repository.create_user(
            User(email=correo, password_hash=passwords.hash_password(PWD), rol=rol)
        )
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


def _compra(**kw) -> dict:
    body = {
        "tipo": "compra",
        "origen": "auteco",
        "numero": "FC-001",
        "tercero_nombre": "Auteco S.A.S.",
        "tercero_nit": "860024781",
        "fecha": "2026-02-10",
        "base_gravable": "1000000",
        "tarifa_iva": "0.19",
        "deducible": True,
    }
    body.update(kw)
    return body


async def test_crear_factura_201_calcula_iva(api):
    ac, _ = api
    h = await _token(ac)
    r = await ac.post("/api/v1/facturas", json=_compra(), headers=h)
    assert r.status_code == 201
    data = r.json()
    assert data["iva_valor"] == "190000.00"
    assert data["total"] == "1190000.00"
    assert data["periodo"] == "2026-C1"  # derivado de la fecha (cuatrimestral default)


async def test_crear_factura_tarifa_no_legal_es_422(api):
    """Pieza 6: endurecer tarifa_iva a las tarifas IVA legales en Colombia
    (0, 0.05, 0.19). 0.16 (tarifa vieja) → 422, no se guarda."""
    ac, _ = api
    h = await _token(ac)
    r = await ac.post("/api/v1/facturas", json=_compra(tarifa_iva="0.16"), headers=h)
    assert r.status_code == 422
    assert "tarifa" in r.json()["detail"].lower()


async def test_crear_factura_tarifa_exenta_cero_ok(api):
    ac, _ = api
    h = await _token(ac)
    r = await ac.post(
        "/api/v1/facturas",
        json=_compra(numero="FC-EX", tarifa_iva="0", base_gravable="1000000"),
        headers=h,
    )
    assert r.status_code == 201
    assert r.json()["iva_valor"] == "0.00"


async def test_crear_factura_tarifa_reducida_5pct_ok(api):
    ac, _ = api
    h = await _token(ac)
    r = await ac.post(
        "/api/v1/facturas",
        json=_compra(numero="FC-5", tarifa_iva="0.05", base_gravable="1000000"),
        headers=h,
    )
    assert r.status_code == 201
    assert r.json()["iva_valor"] == "50000.00"


async def test_crear_factura_consulta_es_403(api):
    ac, _ = api
    h = await _token(ac, "consulta@roddos.com")
    r = await ac.post("/api/v1/facturas", json=_compra(), headers=h)
    assert r.status_code == 403


async def test_crear_factura_duplicada_409(api):
    ac, _ = api
    h = await _token(ac)
    r1 = await ac.post("/api/v1/facturas", json=_compra(), headers=h)
    assert r1.status_code == 201
    r = await ac.post("/api/v1/facturas", json=_compra(), headers=h)
    assert r.status_code == 409


async def test_listar_y_anular(api):
    ac, _ = api
    h = await _token(ac)
    r = await ac.post("/api/v1/facturas", json=_compra(), headers=h)
    fid = r.json()["id"]
    # anular
    ra = await ac.post(f"/api/v1/facturas/{fid}/anular", headers=h)
    assert ra.status_code == 200
    assert ra.json()["activo"] is False
    # listar activas → vacío
    rl = await ac.get("/api/v1/facturas?activo=true", headers=h)
    assert rl.status_code == 200
    assert rl.json() == []


# ── A17 / punto 4: PII (Ley 1581) — facturas:ver_detalle {financiero, admin} ──
async def test_listado_minimiza_pii_sin_ver_detalle(api):
    """consulta tiene dashboard:leer pero NO facturas:ver_detalle → el listado le
    oculta tercero_nombre/tercero_nit (PII); el resto de campos visibles."""
    ac, _ = api
    hfin = await _token(ac)
    await ac.post("/api/v1/facturas", json=_compra(), headers=hfin)

    hcon = await _token(ac, "consulta@roddos.com")
    r = await ac.get("/api/v1/facturas", headers=hcon)
    assert r.status_code == 200
    fila = r.json()[0]
    assert fila["tercero_nombre"] is None
    assert fila["tercero_nit"] is None
    assert fila["iva_valor"] == "190000.00"  # el número de IVA sí es visible


async def test_listado_muestra_pii_con_ver_detalle(api):
    ac, _ = api
    h = await _token(ac)  # financiero
    await ac.post("/api/v1/facturas", json=_compra(), headers=h)
    r = await ac.get("/api/v1/facturas", headers=h)
    fila = r.json()[0]
    assert fila["tercero_nombre"] == "Auteco S.A.S."
    assert fila["tercero_nit"] == "860024781"


async def test_detalle_factura_requiere_ver_detalle(api):
    ac, _ = api
    h = await _token(ac)
    fid = (await ac.post("/api/v1/facturas", json=_compra(), headers=h)).json()["id"]

    rcon = await ac.get(
        f"/api/v1/facturas/{fid}", headers=await _token(ac, "consulta@roddos.com")
    )
    assert rcon.status_code == 403

    rfin = await ac.get(f"/api/v1/facturas/{fid}", headers=h)
    assert rfin.status_code == 200
    assert rfin.json()["tercero_nit"] == "860024781"  # PII completa para autorizado


async def test_liquidacion_visible_para_directivo(api):
    """GET /liquidacion se queda bajo dashboard:leer: el directivo ve el número de
    IVA (lo que NO ve es la contraparte, cubierto por el listado/detalle)."""
    ac, _ = api
    r = await ac.get(
        "/api/v1/facturas/liquidacion", headers=await _token(ac, "consulta@roddos.com")
    )
    assert r.status_code == 200


async def test_a10_ejemplo_aritmetico_spec_6_end_to_end(api):
    """A10: el ejemplo §6 reproduce EXACTO el arrastre y el pago, vía el endpoint
    real GET /facturas/liquidacion. IVA exacto (sin base×tarifa) insertando facturas
    estilo DIAN (base_gravable=None). La NO deducible queda registrada pero excluida
    del descontable."""
    from app.domain.factura import Factura

    async def _ins(numero, tipo, fecha, iva, deducible):
        await Factura(
            tipo=tipo,
            origen="sin_clasificar",
            numero=numero,
            tercero_nombre="Contraparte",
            tercero_nit="900",
            fecha=fecha,
            base_gravable=None,
            total_bruto=None,
            tarifa_iva=None,
            iva_valor=Decimal(iva),
            total=Decimal(iva),
            deducible=deducible,
        ).insert()

    # C2-2026 (may–ago)
    await _ins("R-1", "compra", "2026-05-28", "1452.94", True)
    await _ins("R-2", "compra", "2026-06-15", "19000000.00", True)
    await _ins("E-1", "venta", "2026-05-10", "8000000.00", False)
    # C3-2026 (sep–dic)
    await _ins("E-2", "venta", "2026-09-15", "15000000.00", False)
    await _ins("R-3", "compra", "2026-10-01", "2000000.00", True)
    await _ins("R-4", "compra", "2026-11-01", "500000.00", False)  # NO deducible

    ac, _ = api
    h = await _token(ac)
    r = await ac.get("/api/v1/facturas/liquidacion", headers=h)
    assert r.status_code == 200
    periodos = {p["etiqueta"]: p for p in r.json()["periodos"]}

    c2 = periodos["2026-C2"]
    assert c2["generado"] == "8000000.00"
    assert c2["descontable"] == "19001452.94"  # 1452.94 + 19.000.000
    assert c2["neto_a_pagar"] == "0.00"  # saldo a favor, nunca pago negativo
    assert c2["saldo_favor_nuevo"] == "11001452.94"  # se arrastra

    c3 = periodos["2026-C3"]
    assert c3["generado"] == "15000000.00"
    assert c3["descontable"] == "2000000.00"  # los 500.000 NO deducibles quedan fuera
    assert c3["saldo_favor_previo"] == "11001452.94"  # arrastre del C2
    assert c3["neto_a_pagar"] == "1998547.06"
    assert c3["saldo_favor_nuevo"] == "0.00"  # arrastre agotado

    # la NO deducible SÍ está registrada (excluida del descontable, no del registro)
    rl = await ac.get("/api/v1/facturas?activo=true", headers=h)
    assert any(f["numero"] == "R-4" for f in rl.json())


async def test_liquidacion_cuatrimestral(api):
    ac, _ = api
    h = await _token(ac)
    # venta C1: genera 190000
    await ac.post(
        "/api/v1/facturas",
        json={
            "tipo": "venta",
            "origen": "moto",
            "numero": "FV-1",
            "tercero_nombre": "Cliente",
            "tercero_nit": "79",
            "fecha": "2026-02-01",
            "base_gravable": "1000000",
            "tarifa_iva": "0.19",
            "deducible": False,
        },
        headers=h,
    )
    # compra deducible C1: descontable 95000 → neto 95000
    await ac.post(
        "/api/v1/facturas",
        json=_compra(numero="FC-9", base_gravable="500000"),
        headers=h,
    )
    r = await ac.get("/api/v1/facturas/liquidacion", headers=h)
    assert r.status_code == 200
    data = r.json()
    assert data["periodicidad"] == "cuatrimestral"
    periodos = data["periodos"]
    assert len(periodos) == 1
    c = periodos[0]
    assert c["anio"] == 2026
    assert c["periodo"] == 1
    assert c["etiqueta"] == "2026-C1"
    assert c["generado"] == "190000.00"
    assert c["descontable"] == "95000.00"
    assert c["neto_a_pagar"] == "95000.00"
