# backend/tests/test_facturas_cargar.py
"""E2 §4.3 — POST /api/v1/facturas/cargar (ingesta de PDFs DIAN por lote).

Contrato por archivo: creada | duplicada | rechazada_no_dian |
rechazada_tipo_no_soportado | requiere_confirmacion | error (interno inesperado —
exigido por el resultado PARCIAL: si el archivo 7 falla, los otros 19 se procesan).
Idempotencia (A2), tope de lote (A16), mapeo emitida→venta / recibida→compra,
FacturaDian.inc → Factura.inc_valor (candado del rename: INC>0 NUNCA queda en 0.00),
requiere_confirmacion NO persiste, RBAC iva:gestionar.

El parseo real (pdfplumber) se cubre con el PDF real en el test E2E; el resto
monkeypatchea la costura `ingesta._extraer_bytes` y dispatchea por CONTENIDO del
archivo (el nombre original no llega al extractor)."""

import hashlib
from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from app.audit.service import configure_audit, reset_audit
from app.auth import passwords, repository
from app.auth.models import User
from app.auth.roles import Role
from app.config import get_settings
from app.domain import DOMAIN_DOCUMENTS
from app.domain.configuracion import Configuracion
from app.domain.factura import Factura
from app.facturas import ingesta
from app.facturas.extraccion import DocumentoNoDian, FacturaDian, TipoNoSoportado
from app.main import create_app
from mongomock_motor import AsyncMongoMockClient

PWD = "clave-larga-1234"
NIT_RODDOS = "901012622"
NIT_AUTECO = "860024781"
URL = "/api/v1/facturas/cargar"


def _dian(**kw) -> FacturaDian:
    """FacturaDian sintética coherente (base 1.000 + IVA 190 + INC 100 = 1.290)."""
    campos = dict(
        tipo_documento="FACTURA ELECTRÓNICA DE VENTA",
        cufe="cufe-defecto",
        numero="UI90-1",
        fecha=date(2026, 5, 28),
        nit_emisor="890900608",
        nombre_emisor="ALMACENES ÉXITO S.A",
        nit_adquiriente=NIT_RODDOS,
        tipo="recibida",
        tipo_contribuyente_contraparte="persona_juridica",
        base_gravable=Decimal("1000.00"),
        iva=Decimal("190.00"),
        inc=Decimal("100.00"),
        bolsas=Decimal("0.00"),
        otros_impuestos=Decimal("0.00"),
        total_impuesto=Decimal("290.00"),
        total_factura=Decimal("1290.00"),
        rete_fuente=Decimal("0.00"),
        rete_iva=Decimal("0.00"),
        rete_ica=Decimal("0.00"),
    )
    campos.update(kw)
    return FacturaDian(**campos)


def _cufe_de(contenido: bytes) -> str:
    return "cufe-" + hashlib.sha256(contenido).hexdigest()[:40]


def _fake_extraer_bytes(contenido: bytes, nombre: str, nit_propio: str) -> FacturaDian:
    """Doble de `ingesta._extraer_bytes`: dispatch por contenido. Mismo contenido →
    mismo CUFE (indispensable para el test de idempotencia)."""
    cufe = _cufe_de(contenido)
    if contenido == b"PDF-NC":
        raise TipoNoSoportado("NOTA CREDITO: tipo no procesado en E2")
    if contenido == b"PDF-AJENO":
        raise DocumentoNoDian("no parece Representación Gráfica DIAN")
    if contenido == b"PDF-CRASH":
        raise RuntimeError("boom interno")
    if contenido == b"PDF-INCOHERENTE":
        return _dian(cufe=cufe, numero="UI90-9", total_factura=Decimal("9999.00"))
    if contenido == b"PDF-EMITIDA":
        return _dian(
            cufe=cufe,
            numero="FV-77",
            tipo="emitida",
            nit_emisor=NIT_RODDOS,
            nombre_emisor="RODDOS S.A.S.",
            nit_adquiriente="800111222",
        )
    if contenido == b"PDF-AUTECO":
        return _dian(
            cufe=cufe,
            numero="AU-1",
            nit_emisor=NIT_AUTECO,
            nombre_emisor="AUTECO S.A.S.",
        )
    return _dian(cufe=cufe, numero=f"UI90-{cufe[-6:]}")


@pytest_asyncio.fixture
async def api(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    monkeypatch.setenv("COOKIE_SECURE", "False")
    monkeypatch.delenv("RUN_SCHEDULER", raising=False)
    get_settings.cache_clear()

    app = create_app()
    c = AsyncMongoMockClient(tz_aware=True)
    await init_db(c)
    for correo, rol in [
        ("consulta@roddos.com", Role.consulta),
        ("fin@roddos.com", Role.financiero),
    ]:
        await repository.create_user(
            User(email=correo, password_hash=passwords.hash_password(PWD), rol=rol)
        )
    for clave, nit in [("NIT_RODDOS", NIT_RODDOS), ("NIT_AUTECO", NIT_AUTECO)]:
        await Configuracion(
            clave=clave, valor_json={"nit": nit}, vigente_desde="2026-01-01"
        ).insert()
    monkeypatch.setattr(ingesta, "_extraer_bytes", _fake_extraer_bytes)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, c
    repository.reset_auth()
    reset_audit()
    get_settings.cache_clear()


async def init_db(c) -> None:
    from beanie import init_beanie

    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
    repository.configure_auth(c, "compas_test")
    configure_audit(c, "compas_test")


async def _token(ac, email="fin@roddos.com") -> dict:
    r = await ac.post("/api/v1/auth/login", json={"email": email, "password": PWD})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _archivos(*contenidos: bytes, nombres: list[str] | None = None) -> list:
    return [
        (
            "archivos",
            ((nombres[i] if nombres else f"doc{i}.pdf"), cont, "application/pdf"),
        )
        for i, cont in enumerate(contenidos)
    ]


# ── RBAC: cargar exige iva:gestionar ({financiero, admin}), no dashboard:leer ──
async def test_cargar_consulta_es_403(api):
    ac, _ = api
    h = await _token(ac, "consulta@roddos.com")
    r = await ac.post(URL, files=_archivos(b"PDF-OK"), headers=h)
    assert r.status_code == 403


# ── Tope de lote: 20 archivos máximo (coherente con POST /api/v1/cargas) ──
async def test_mas_de_20_archivos_413(api):
    ac, _ = api
    h = await _token(ac)
    lote = _archivos(*[f"PDF-{i}".encode() for i in range(21)])
    r = await ac.post(URL, files=lote, headers=h)
    assert r.status_code == 413


async def test_archivo_de_mas_de_10mb_se_rechaza_y_el_resto_se_procesa(api):
    ac, _ = api
    h = await _token(ac)
    gordo = b"x" * (10 * 1024 * 1024 + 1)
    r = await ac.post(URL, files=_archivos(gordo, b"PDF-OK"), headers=h)
    assert r.status_code == 200
    res = r.json()["resultados"]
    assert res[0]["estado"] == "rechazada_no_dian"
    assert "10 MB" in res[0]["motivo"]
    assert res[1]["estado"] == "creada"


async def test_extension_no_pdf_se_rechaza(api):
    ac, _ = api
    h = await _token(ac)
    r = await ac.post(
        URL, files=_archivos(b"PDF-OK", nombres=["extracto.xlsx"]), headers=h
    )
    assert r.status_code == 200
    res = r.json()["resultados"][0]
    assert res["estado"] == "rechazada_no_dian"
    assert ".pdf" in res["motivo"]
    assert await Factura.count() == 0


# ── Camino feliz: crea la factura con los campos DIAN mapeados ──
async def test_cargar_recibida_crea_factura(api):
    ac, _ = api
    h = await _token(ac)
    r = await ac.post(URL, files=_archivos(b"PDF-OK"), headers=h)
    assert r.status_code == 200
    data = r.json()
    assert data["resumen"]["creadas"] == 1
    res = data["resultados"][0]
    assert res["estado"] == "creada"
    assert res["factura_id"]
    # montos como string (regla 1)
    assert res["datos_extraidos"]["iva_valor"] == "190.00"
    assert res["datos_extraidos"]["total_factura"] == "1290.00"

    f = await Factura.find_one(Factura.cufe == _cufe_de(b"PDF-OK"))
    assert f is not None
    assert f.tipo.value == "compra"  # recibida → compra
    assert f.origen.value == "sin_clasificar"  # NIT no-Auteco → sin_clasificar
    assert f.tercero_nit == "890900608"
    assert f.tercero_nombre == "ALMACENES ÉXITO S.A"
    assert f.iva_valor == Decimal("190.00")  # el IVA extraído, NO base×tarifa
    assert f.total == Decimal("1290.00")
    assert f.tarifa_iva is None  # DIAN puede mezclar tarifas; no se inventa una
    # el Total Bruto DIAN va a total_bruto; base_gravable (base GRAVADA real) NO se
    # conoce sin parsear líneas → None (R5: no se inventa). El "1000" del _dian es
    # Total Bruto, no base gravada.
    assert f.total_bruto == Decimal("1000.00")
    assert f.base_gravable is None
    assert f.archivo_ref is not None and "sha256:" in f.archivo_ref
    assert f.deducible is False  # decisión explícita pendiente (pieza 7)


# ── Candado del rename inc→inc_valor: INC>0 NUNCA se guarda en 0.00 ──
async def test_inc_mayor_a_cero_queda_en_inc_valor(api):
    ac, _ = api
    h = await _token(ac)
    r = await ac.post(URL, files=_archivos(b"PDF-OK"), headers=h)
    assert r.status_code == 200
    f = await Factura.find_one(Factura.cufe == _cufe_de(b"PDF-OK"))
    assert f.inc_valor == Decimal("100.00")
    assert f.inc_valor != Decimal("0.00")


# ── Pieza 5: PRECEDENCIA del iva_valor extraído sobre base×tarifa (D-13/§3.2) ──
async def test_iva_extraido_manda_sobre_base_por_tarifa(api, monkeypatch):
    """El iva_valor del bloque de totales DIAN se guarda tal cual; NO se recalcula
    como base×0.19. Números del A1 real: base_gravable (Total Bruto, incluye líneas
    sin IVA) 31.447,06 con IVA 1.452,94 → base×0.19 daría 5.974,94. Se guarda
    1.452,94 y tarifa_iva=None (la DIAN puede mezclar tarifas)."""

    def _mixta(contenido, nombre, nit_propio):
        return _dian(
            cufe=_cufe_de(contenido),
            numero="MIX-1",
            base_gravable=Decimal("31447.06"),
            iva=Decimal("1452.94"),
            inc=Decimal("0.00"),
            total_impuesto=Decimal("1452.94"),
            total_factura=Decimal("32900.00"),
        )

    monkeypatch.setattr(ingesta, "_extraer_bytes", _mixta)
    ac, _ = api
    h = await _token(ac)
    r = await ac.post(URL, files=_archivos(b"PDF-MIXTA"), headers=h)
    assert r.status_code == 200
    assert r.json()["resultados"][0]["estado"] == "creada"
    f = await Factura.find_one(Factura.cufe == _cufe_de(b"PDF-MIXTA"))
    assert f.iva_valor == Decimal("1452.94")  # el extraído
    assert f.iva_valor != Decimal("31447.06") * Decimal("0.19")  # NO total_bruto×tarifa
    assert f.total_bruto == Decimal("31447.06")  # Total Bruto, no base gravada
    assert f.base_gravable is None
    assert f.tarifa_iva is None


def test_campos_desde_dian_mapea_inc_a_inc_valor():
    """Costura pura: el desajuste FacturaDian.inc→Factura.inc_valor guardaría un
    cero en silencio; este test lo hace imposible."""
    campos = ingesta.campos_desde_dian(_dian(), nit_auteco=NIT_AUTECO)
    assert campos["inc_valor"] == Decimal("100.00")
    assert "inc" not in campos  # el campo del Document se llama inc_valor


def test_campos_desde_dian_total_bruto_no_base_gravable():
    """Total Bruto DIAN → total_bruto; base_gravable=None (no es la base gravada)."""
    campos = ingesta.campos_desde_dian(
        _dian(base_gravable=Decimal("31447.06")), nit_auteco=NIT_AUTECO
    )
    assert campos["total_bruto"] == Decimal("31447.06")
    assert campos["base_gravable"] is None


async def test_datos_extraidos_muestra_total_bruto_no_base(api):
    """El resultado por archivo rotula el Total Bruto como tal; base_gravable None."""
    ac, _ = api
    h = await _token(ac)
    r = await ac.post(URL, files=_archivos(b"PDF-OK"), headers=h)
    datos = r.json()["resultados"][0]["datos_extraidos"]
    assert datos["total_bruto"] == "1000.00"
    assert datos["base_gravable"] is None


# ── Mapeos: emitida→venta · Auteco→origen auteco ──
async def test_emitida_es_venta_con_tercero_adquiriente(api):
    ac, _ = api
    h = await _token(ac)
    r = await ac.post(URL, files=_archivos(b"PDF-EMITIDA"), headers=h)
    assert r.status_code == 200
    f = await Factura.find_one(Factura.cufe == _cufe_de(b"PDF-EMITIDA"))
    assert f.tipo.value == "venta"
    assert f.tercero_nit == "800111222"  # el adquiriente, no RODDOS
    # el extractor no captura el nombre del adquiriente: se etiqueta con el NIT
    # real (R5: no se inventa), la pantalla de confirmación lo corrige (pieza 7)
    assert f.tercero_nombre == "NIT 800111222"
    assert f.origen.value == "sin_clasificar"


async def test_recibida_de_auteco_queda_origen_auteco(api):
    ac, _ = api
    h = await _token(ac)
    r = await ac.post(URL, files=_archivos(b"PDF-AUTECO"), headers=h)
    assert r.status_code == 200
    f = await Factura.find_one(Factura.cufe == _cufe_de(b"PDF-AUTECO"))
    assert f.origen.value == "auteco"


# ── Idempotencia (A2): mismo lote dos veces → todas duplicadas, ninguna nueva ──
async def test_mismo_lote_dos_veces_todas_duplicadas(api):
    ac, _ = api
    h = await _token(ac)
    lote = _archivos(b"PDF-OK", b"PDF-EMITIDA")
    r1 = await ac.post(URL, files=lote, headers=h)
    assert r1.json()["resumen"]["creadas"] == 2
    r2 = await ac.post(URL, files=lote, headers=h)
    assert r2.status_code == 200
    assert [x["estado"] for x in r2.json()["resultados"]] == [
        "duplicada",
        "duplicada",
    ]
    assert r2.json()["resumen"]["creadas"] == 0
    assert await Factura.count() == 2


# ── Resultado PARCIAL con estados distinguibles (§2 bis: el radar de NC) ──
async def test_resultado_parcial_y_estados_distinguibles(api):
    ac, _ = api
    h = await _token(ac)
    r = await ac.post(
        URL,
        files=_archivos(b"PDF-OK", b"PDF-NC", b"PDF-AJENO", b"PDF-CRASH"),
        headers=h,
    )
    assert r.status_code == 200
    estados = [x["estado"] for x in r.json()["resultados"]]
    assert estados == [
        "creada",
        "rechazada_tipo_no_soportado",  # alimenta el contador del §2 bis
        "rechazada_no_dian",
        "error",
    ]
    resumen = r.json()["resumen"]
    assert resumen["creadas"] == 1
    assert resumen["rechazadas_tipo_no_soportado"] == 1
    assert resumen["rechazadas_no_dian"] == 1
    assert resumen["errores"] == 1
    assert await Factura.count() == 1  # el crash del archivo 4 no frenó al 1


# ── A6: incoherente → requiere_confirmacion, NADA se persiste ──
async def test_incoherente_requiere_confirmacion_sin_persistir(api):
    ac, _ = api
    h = await _token(ac)
    r = await ac.post(URL, files=_archivos(b"PDF-INCOHERENTE"), headers=h)
    assert r.status_code == 200
    res = r.json()["resultados"][0]
    assert res["estado"] == "requiere_confirmacion"
    assert res["factura_id"] is None
    # los datos extraídos viajan al cliente para la pantalla de confirmación
    assert res["datos_extraidos"]["total_factura"] == "9999.00"
    assert res["datos_extraidos"]["iva_valor"] == "190.00"
    assert await Factura.count() == 0  # ningún documento fiscal a medio registrar


# ── Config ausente: sin NIT_RODDOS no se puede deducir el tipo → 409 accionable ──
async def test_sin_nit_roddos_configurado_409(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    monkeypatch.setenv("COOKIE_SECURE", "False")
    monkeypatch.delenv("RUN_SCHEDULER", raising=False)
    get_settings.cache_clear()
    app = create_app()
    c = AsyncMongoMockClient(tz_aware=True)
    await init_db(c)  # SIN sembrar NIT_RODDOS
    await repository.create_user(
        User(
            email="fin@roddos.com",
            password_hash=passwords.hash_password(PWD),
            rol=Role.financiero,
        )
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        h = await _token(ac)
        r = await ac.post(URL, files=_archivos(b"PDF-OK"), headers=h)
        assert r.status_code == 409
        assert "NIT_RODDOS" in r.json()["detail"]
    repository.reset_auth()
    reset_audit()


# ── Auditoría: factura.creada por cada creada; fail-closed → compensar ──
async def test_cargar_emite_factura_creada(api):
    ac, c = api
    h = await _token(ac)
    await ac.post(URL, files=_archivos(b"PDF-OK"), headers=h)
    eventos = await c["compas_test"]["audit_log"].find(
        {"evento": "factura.creada"}
    ).to_list(10)
    assert len(eventos) == 1


async def test_audit_caido_no_deja_factura(api, monkeypatch):
    async def _explota(*a, **kw):
        raise RuntimeError("audit caído")

    monkeypatch.setattr(ingesta, "emit_audit", _explota)
    ac, _ = api
    h = await _token(ac)
    r = await ac.post(URL, files=_archivos(b"PDF-OK"), headers=h)
    assert r.status_code == 200
    assert r.json()["resultados"][0]["estado"] == "error"
    assert await Factura.count() == 0  # saga O1: sin rastro no hay alta


# ── E2E con el PDF real (cubre _extraer_bytes + threadpool de verdad, A16) ──
_FIXTURE = (
    Path(__file__).parent / "fixtures" / "dian_factura_venta_exito_2026-05-28.pdf"
)


# Capturado ANTES de que el fixture `api` monkeypatchee el módulo: el E2E lo
# restaura para cubrir pdfplumber + temp file + threadpool de verdad.
_REAL_EXTRAER = ingesta._extraer_bytes


@pytest.mark.skipif(
    not _FIXTURE.exists(),
    reason="falta el PDF de muestra en backend/tests/fixtures/",
)
async def test_e2e_pdf_real_crea_y_deduplica(api, monkeypatch):
    monkeypatch.setattr(ingesta, "_extraer_bytes", _REAL_EXTRAER)
    ac, _ = api
    h = await _token(ac)
    contenido = _FIXTURE.read_bytes()
    files = _archivos(contenido, nombres=[_FIXTURE.name])
    r1 = await ac.post(URL, files=files, headers=h)
    assert r1.status_code == 200
    res = r1.json()["resultados"][0]
    assert res["estado"] == "creada"
    assert res["datos_extraidos"]["iva_valor"] == "1452.94"  # A1
    r2 = await ac.post(URL, files=files, headers=h)
    assert r2.json()["resultados"][0]["estado"] == "duplicada"
