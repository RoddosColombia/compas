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


# ── PASO 1 (CR-E2-EDITAR): PATCH /facturas/{id} {deducible?, origen?} ──
async def _crear(ac, h, **kw) -> str:
    r = await ac.post("/api/v1/facturas", json=_compra(**kw), headers=h)
    assert r.status_code == 201
    return r.json()["id"]


async def test_patch_marca_deducible_y_audita(api):
    ac, c = api
    h = await _token(ac)
    fid = await _crear(ac, h, deducible=False)
    r = await ac.patch(f"/api/v1/facturas/{fid}", json={"deducible": True}, headers=h)
    assert r.status_code == 200
    assert r.json()["deducible"] is True
    eventos = (
        await c["compas_test"]["audit_log"]
        .find({"evento": "factura.actualizada"})
        .to_list(10)
    )
    assert len(eventos) == 1
    # sin PII en la metadata (Ley 1581): ni nombre ni NIT del tercero
    meta = eventos[0]["metadata"]
    assert meta["deducible"] == {"antes": False, "despues": True}
    assert "tercero_nit" not in meta and "tercero_nombre" not in meta


async def test_patch_reclasifica_origen(api):
    ac, _ = api
    h = await _token(ac)
    fid = await _crear(ac, h, origen="sin_clasificar")
    r = await ac.patch(
        f"/api/v1/facturas/{fid}", json={"origen": "repuesto"}, headers=h
    )
    assert r.status_code == 200
    assert r.json()["origen"] == "repuesto"


async def test_patch_deducible_en_venta_es_422(api):
    ac, _ = api
    h = await _token(ac)
    r = await ac.post(
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
    fid = r.json()["id"]
    rp = await ac.patch(f"/api/v1/facturas/{fid}", json={"deducible": True}, headers=h)
    assert rp.status_code == 422
    assert "venta" in rp.json()["detail"].lower()


async def test_patch_rechaza_campos_fiscales(api):
    """La factura es inmutable en lo fiscal: solo deducible/origen. Un intento de
    tocar un monto (o fecha/tipo) → 422 (body strict, extra=forbid)."""
    ac, _ = api
    h = await _token(ac)
    fid = await _crear(ac, h)
    for payload in (
        {"iva_valor": "999.00"},
        {"base_gravable": "999.00"},
        {"fecha": "2026-01-01"},
        {"tipo": "venta"},
        {"total": "1.00"},
    ):
        rp = await ac.patch(f"/api/v1/facturas/{fid}", json=payload, headers=h)
        assert rp.status_code == 422, payload


async def test_patch_sin_cambios_es_422(api):
    ac, _ = api
    h = await _token(ac)
    fid = await _crear(ac, h)
    rp = await ac.patch(f"/api/v1/facturas/{fid}", json={}, headers=h)
    assert rp.status_code == 422


async def test_patch_consulta_es_403(api):
    ac, _ = api
    h = await _token(ac)
    fid = await _crear(ac, h)
    rp = await ac.patch(
        f"/api/v1/facturas/{fid}",
        json={"deducible": True},
        headers=await _token(ac, "consulta@roddos.com"),
    )
    assert rp.status_code == 403


# ── PASO 1b: PATCH /facturas/deducibilidad — lote, tolerante a fallos parciales ──
async def test_patch_lote_marca_varias(api):
    ac, _ = api
    h = await _token(ac)
    ids = [
        await _crear(ac, h, numero=f"FC-{i}", tercero_nit="900", deducible=False)
        for i in range(3)
    ]
    r = await ac.patch(
        "/api/v1/facturas/deducibilidad",
        json={"ids": ids, "deducible": True},
        headers=h,
    )
    assert r.status_code == 200
    res = r.json()["resultados"]
    assert all(x["estado"] == "actualizada" for x in res)
    assert r.json()["resumen"]["actualizadas"] == 3


async def test_patch_lote_venta_erra_solo_esa(api):
    ac, _ = api
    h = await _token(ac)
    compra = await _crear(ac, h, numero="C-1", tercero_nit="900", deducible=False)
    rv = await ac.post(
        "/api/v1/facturas",
        json={
            "tipo": "venta",
            "origen": "moto",
            "numero": "V-1",
            "tercero_nombre": "Cliente",
            "tercero_nit": "79",
            "fecha": "2026-02-01",
            "base_gravable": "1000000",
            "tarifa_iva": "0.19",
            "deducible": False,
        },
        headers=h,
    )
    venta = rv.json()["id"]
    r = await ac.patch(
        "/api/v1/facturas/deducibilidad",
        json={"ids": [compra, venta], "deducible": True},
        headers=h,
    )
    res = {x["id"]: x for x in r.json()["resultados"]}
    assert res[compra]["estado"] == "actualizada"
    assert res[venta]["estado"] == "error"
    assert "venta" in res[venta]["motivo"].lower()


async def test_patch_lote_fail_closed_por_factura(api, monkeypatch):
    """El emit del evento de UNA factura falla → SOLO esa se revierte y sale con
    error; las demás siguen (refinamiento CEO)."""
    ac, _ = api
    h = await _token(ac)
    bomba = await _crear(ac, h, numero="BOMBA", tercero_nit="900", deducible=False)
    buena = await _crear(ac, h, numero="BUENA", tercero_nit="900", deducible=False)

    from app.facturas import service as svc

    real_emit = svc.emit_audit

    async def emit_selectivo(evento, **kw):
        if kw.get("metadata", {}).get("numero") == "BOMBA":
            raise RuntimeError("audit caído para BOMBA")
        return await real_emit(evento, **kw)

    monkeypatch.setattr(svc, "emit_audit", emit_selectivo)

    r = await ac.patch(
        "/api/v1/facturas/deducibilidad",
        json={"ids": [bomba, buena], "deducible": True},
        headers=h,
    )
    res = {x["id"]: x for x in r.json()["resultados"]}
    assert res[bomba]["estado"] == "error"
    assert res[buena]["estado"] == "actualizada"
    # la bomba quedó revertida (deducible sigue False), la buena sí cambió
    from app.domain.factura import Factura
    from beanie import PydanticObjectId

    assert (await Factura.get(PydanticObjectId(bomba))).deducible is False
    assert (await Factura.get(PydanticObjectId(buena))).deducible is True


async def test_patch_lote_id_desconocido_erra_solo_ese(api):
    ac, _ = api
    h = await _token(ac)
    ok = await _crear(ac, h, numero="OK-1", tercero_nit="900", deducible=False)
    r = await ac.patch(
        "/api/v1/facturas/deducibilidad",
        json={"ids": [ok, "deadbeef"], "deducible": True},
        headers=h,
    )
    res = {x["id"]: x for x in r.json()["resultados"]}
    assert res[ok]["estado"] == "actualizada"
    assert res["deadbeef"]["estado"] == "error"


async def test_patch_lote_consulta_403(api):
    ac, _ = api
    h = await _token(ac)
    fid = await _crear(ac, h)
    r = await ac.patch(
        "/api/v1/facturas/deducibilidad",
        json={"ids": [fid], "deducible": True},
        headers=await _token(ac, "consulta@roddos.com"),
    )
    assert r.status_code == 403


# ── deducible_decidido: 3 estados (Sí / No / Sin decidir) para el §2 ──
async def test_serializador_expone_deducible_decidido(api):
    """El listado expone el flag para que el cliente distinga los 3 estados de la
    columna y cuente las recibidas sin decidir (§2). Manual → decidido True."""
    ac, _ = api
    h = await _token(ac)
    await ac.post("/api/v1/facturas", json=_compra(), headers=h)
    r = await ac.get("/api/v1/facturas", headers=h)
    assert r.json()[0]["deducible_decidido"] is True


async def test_patch_no_deducible_sobre_sin_decidir_es_cambio(api):
    """Marcar 'No es deducible' sobre una factura DIAN sin decidir (deducible=False,
    decidido=False) ES un cambio real: registra la decisión aunque el bool no varíe.
    Segunda vez idéntica → no-op, no vuelve a auditar."""
    from app.domain.factura import Factura
    from beanie import PydanticObjectId

    ac, c = api
    h = await _token(ac)
    await _insert_factura("D-1", "persona_juridica")  # DIAN: decidido=False
    fid = str((await Factura.find_one(Factura.numero == "D-1")).id)

    r = await ac.patch(f"/api/v1/facturas/{fid}", json={"deducible": False}, headers=h)
    assert r.status_code == 200
    assert r.json()["deducible"] is False
    assert r.json()["deducible_decidido"] is True
    f = await Factura.get(PydanticObjectId(fid))
    assert f.deducible is False and f.deducible_decidido is True
    evs = (
        await c["compas_test"]["audit_log"]
        .find({"evento": "factura.actualizada"})
        .to_list(10)
    )
    assert len(evs) == 1  # la decisión se auditó

    r2 = await ac.patch(f"/api/v1/facturas/{fid}", json={"deducible": False}, headers=h)
    assert r2.status_code == 200
    evs2 = (
        await c["compas_test"]["audit_log"]
        .find({"evento": "factura.actualizada"})
        .to_list(10)
    )
    assert len(evs2) == 1  # sigue en 1: no-op, no re-audita


async def test_patch_lote_no_deducible_sobre_sin_decidir_actualiza(api):
    """El lote que marca 'No' sobre DIAN sin decidir da 'actualizada' (no
    'sin_cambio'): el resumen real refleja que la decisión se registró."""
    from app.domain.factura import Factura

    ac, _ = api
    h = await _token(ac)
    await _insert_factura("L-1", "persona_juridica")
    await _insert_factura("L-2", "persona_juridica")
    ids = [
        str((await Factura.find_one(Factura.numero == n)).id) for n in ("L-1", "L-2")
    ]
    r = await ac.patch(
        "/api/v1/facturas/deducibilidad",
        json={"ids": ids, "deducible": False},
        headers=h,
    )
    assert r.status_code == 200
    assert r.json()["resumen"]["actualizadas"] == 2
    assert r.json()["resumen"]["sin_cambio"] == 0


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


async def _insert_factura(numero, tipo_contribuyente):
    from app.domain.factura import Factura

    await Factura(
        tipo="compra",
        origen="sin_clasificar",
        numero=numero,
        tercero_nombre="Contraparte X",
        tercero_nit="900123",
        fecha="2026-05-10",
        base_gravable=None,
        total_bruto=Decimal("1000.00"),
        tarifa_iva=None,
        iva_valor=Decimal("190.00"),
        total=Decimal("1190.00"),
        deducible=False,
        tipo_contribuyente=tipo_contribuyente,
    ).insert()


async def test_listado_persona_juridica_visible_para_consulta(api):
    """La razón social de una persona jurídica NO es PII → visible para consulta
    aunque no tenga facturas:ver_detalle."""
    ac, _ = api
    await _token(ac)  # asegura beanie/app arriba
    await _insert_factura("J-1", "persona_juridica")
    r = await ac.get(
        "/api/v1/facturas", headers=await _token(ac, "consulta@roddos.com")
    )
    fila = next(f for f in r.json() if f["numero"] == "J-1")
    assert fila["tercero_nombre"] == "Contraparte X"
    assert fila["tercero_nit"] == "900123"


async def test_listado_persona_natural_enmascarada_para_consulta(api):
    ac, _ = api
    await _token(ac)
    await _insert_factura("N-1", "persona_natural")
    # consulta (sin ver_detalle) → enmascarada
    rc = await ac.get(
        "/api/v1/facturas", headers=await _token(ac, "consulta@roddos.com")
    )
    fc = next(f for f in rc.json() if f["numero"] == "N-1")
    assert fc["tercero_nombre"] is None and fc["tercero_nit"] is None
    # financiero (con ver_detalle) → visible
    rf = await ac.get("/api/v1/facturas", headers=await _token(ac))
    ff = next(f for f in rf.json() if f["numero"] == "N-1")
    assert ff["tercero_nombre"] == "Contraparte X"


async def test_listado_contribuyente_desconocido_enmascarado_para_consulta(api):
    """None (captura manual o PDF sin dato) → PII por precaución."""
    ac, _ = api
    await _token(ac)
    await _insert_factura("U-1", None)
    r = await ac.get(
        "/api/v1/facturas", headers=await _token(ac, "consulta@roddos.com")
    )
    fila = next(f for f in r.json() if f["numero"] == "U-1")
    assert fila["tercero_nombre"] is None and fila["tercero_nit"] is None


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
        iva_d = Decimal(iva)
        # total_bruto plausible (base 19% = iva/0.19) y total = total_bruto + iva:
        # una factura aritméticamente válida (no total == solo el impuesto). Las
        # aserciones de la liquidación dependen de iva_valor+deducible, no de esto.
        bruto = (iva_d / Decimal("0.19")).quantize(Decimal("0.01"))
        await Factura(
            tipo=tipo,
            origen="sin_clasificar",
            numero=numero,
            tercero_nombre="Contraparte",
            tercero_nit="900",
            fecha=fecha,
            base_gravable=None,
            total_bruto=bruto,
            tarifa_iva=None,
            iva_valor=iva_d,
            total=bruto + iva_d,
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


# ── PASO 1c: proximo_pago {fecha, dias} en /liquidacion desde CALENDARIO_DIAN ──
async def test_liquidacion_incluye_proximo_pago_dian(api):
    from datetime import date

    from app.core.time import today_bogota
    from app.domain.configuracion import Configuracion

    ac, _ = api
    h = await _token(ac)
    await Configuracion(
        clave="CALENDARIO_DIAN",
        valor_json={
            "2026": {
                "ene_abr": "2026-05-13",
                "may_ago": "2026-09-10",
                "sep_dic": "2027-01-14",
            }
        },
        vigente_desde="2026-01-01",
    ).insert()
    await _crear(ac, h, numero="C2f", fecha="2026-06-15", deducible=True)  # C2
    r = await ac.get("/api/v1/facturas/liquidacion", headers=h)
    per = {p["etiqueta"]: p for p in r.json()["periodos"]}
    pp = per["2026-C2"]["proximo_pago"]
    assert pp["fecha"] == "2026-09-10"
    assert pp["dias"] == (date(2026, 9, 10) - today_bogota()).days


async def test_liquidacion_proximo_pago_null_sin_calendario(api):
    """Sin fecha en CALENDARIO_DIAN → null, NO se inventa una fecha (R5)."""
    ac, _ = api
    h = await _token(ac)
    await _crear(ac, h, numero="C1f", fecha="2026-02-10", deducible=True)  # C1
    r = await ac.get("/api/v1/facturas/liquidacion", headers=h)
    assert r.json()["periodos"][0]["proximo_pago"] is None


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
