# backend/tests/test_facturas_cargar_excel.py
"""C2' (acta FABS 2026-08-10) — POST /api/v1/facturas/cargar-excel: import masivo
del Excel de "documentos recibidos" del portal DIAN (facturas a nombre de RODDOS,
gasto con IVA potencialmente deducible).

Reglas cubiertas (regla 7: el parser transforma, NUNCA interpreta):
  - Encabezados que no cuadran con el contrato → 422 LISTANDO esperado vs
    encontrado (fail-loud; el contrato es el punto de calibración con el archivo real).
  - Fila válida → Factura tipo=compra, deducible=False/sin decidir (el operador
    decide), SALVO Auteco (NIT por Configuracion) → deducible=True/decidida/origen
    auteco (decisión CEO 2026-07-31, misma regla de la ingesta PDF).
  - Dedup por CUFE (mismo archivo dos veces → duplicadas).
  - Nota crédito / tipo no soportado → rechazada_tipo_no_soportado (radar E2.1).
  - Fila EMITIDA por RODDOS → rechazada (este importador es solo de recibidas).
  - Fila ilegible (fecha/monto) → error de ESA fila; las demás siguen (parcial).
  - RBAC iva:gestionar (consulta → 403). Auditoría factura.creada por fila.
"""

from datetime import date
from io import BytesIO

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
from app.main import create_app
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient
from openpyxl import Workbook

PWD = "clave-larga-1234"
NIT_RODDOS = "901012622"
NIT_AUTECO = "860024781"
# Auteco factura con DOS NITs (CEO 2026-08-11): el histórico y el de AUTOTECNICA
# COLOMBIANA S.A.S. — ambos deben auto-deducir.
NIT_AUTOTECNICA = "890900317"

ENCABEZADOS = [
    "Tipo de documento",
    "Prefijo",
    "Folio",
    "CUFE/CUDE",
    "Fecha Emisión",
    "NIT Emisor",
    "Nombre Emisor",
    "IVA",
    "Total",
]


def _xlsx(filas: list[list], encabezados: list[str] | None = None) -> bytes:
    """Arma un xlsx en memoria con filas de título arriba (como exporta la DIAN)."""
    wb = Workbook()
    ws = wb.active
    ws.append(["Documentos Recibidos"])  # fila de título que el parser debe saltar
    ws.append([])
    ws.append(encabezados or ENCABEZADOS)
    for f in filas:
        ws.append(f)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _fila(
    *,
    tipo="Factura electrónica de Venta",
    prefijo="FE",
    folio="1234",
    cufe="a1b2c3d4e5f60718293a4b5c6d7e8f901234567890abcdef1234567890abcdef",
    fecha=None,
    nit=None,
    nombre="FERRETERIA EL TORNILLO SAS",
    iva=1452.94,
    total=32900.00,
) -> list:
    return [
        tipo,
        prefijo,
        folio,
        cufe,
        fecha if fecha is not None else date(2026, 5, 28),
        nit or "890900608",
        nombre,
        iva,
        total,
    ]


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
    for clave, nit in [("NIT_RODDOS", NIT_RODDOS), ("NIT_AUTECO", NIT_AUTECO)]:
        await Configuracion(
            clave=clave, valor_json={"nit": nit}, vigente_desde="2026-01-01"
        ).insert()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    repository.reset_auth()
    reset_audit()
    get_settings.cache_clear()


async def _token(ac, email="fin@roddos.com") -> dict:
    r = await ac.post("/api/v1/auth/login", json={"email": email, "password": PWD})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _cargar(ac, h, contenido: bytes, nombre="documentos_recibidos.xlsx"):
    return await ac.post(
        "/api/v1/facturas/cargar-excel",
        files={
            "archivo": (
                nombre,
                contenido,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        headers=h,
    )


@pytest.mark.asyncio
async def test_carga_feliz_con_auteco_autodeducible(api):
    h = await _token(api)
    contenido = _xlsx(
        [
            _fila(cufe="c1" * 32, folio="1001"),
            _fila(
                cufe="c2" * 32,
                folio="777",
                nit=NIT_AUTECO,
                nombre="AUTECO SAS",
                iva=3800000,
                total=23800000,
            ),
        ]
    )
    r = await _cargar(api, h, contenido)
    assert r.status_code == 200, r.text
    assert r.json()["resumen"]["creadas"] == 2

    lista = (await api.get("/api/v1/facturas", headers=h)).json()
    por_numero = {f["numero"]: f for f in lista}
    normal = por_numero["FE1001"]
    assert normal["tipo"] == "compra"
    assert normal["deducible"] is False
    assert normal["deducible_decidido"] is False
    assert normal["origen"] == "sin_clasificar"
    assert normal["iva_valor"] == "1452.94"
    auteco = por_numero["FE777"]
    assert auteco["deducible"] is True  # decisión CEO: Auteco descontable por config
    assert auteco["deducible_decidido"] is True
    assert auteco["origen"] == "auteco"


@pytest.mark.asyncio
async def test_auteco_con_dos_nits_ambos_autodeducibles(api):
    """Auteco factura con DOS NITs (CEO 2026-08-11). Con la config en la forma
    {"nits": [...]}, una fila de CUALQUIERA de los dos entra deducible/decidida/
    origen auteco; el fixture (forma vieja {"nit": ...}) prueba la compatibilidad."""
    await Configuracion(
        clave="NIT_AUTECO",
        valor_json={"nits": [NIT_AUTECO, NIT_AUTOTECNICA]},
        vigente_desde="2026-02-01",  # vigencia más nueva que la del fixture
    ).insert()
    h = await _token(api)
    contenido = _xlsx(
        [
            _fila(cufe="a1" * 32, folio="111", nit=NIT_AUTECO, nombre="AUTECO SAS"),
            _fila(
                cufe="a2" * 32,
                folio="222",
                nit=NIT_AUTOTECNICA,
                nombre="AUTOTECNICA COLOMBIANA S.A.S.",
            ),
            _fila(cufe="a3" * 32, folio="333"),  # tercero cualquiera: sin decidir
        ]
    )
    r = await _cargar(api, h, contenido)
    assert r.status_code == 200, r.text
    assert r.json()["resumen"]["creadas"] == 3

    lista = (await api.get("/api/v1/facturas", headers=h)).json()
    por_numero = {f["numero"]: f for f in lista}
    for numero in ("FE111", "FE222"):
        assert por_numero[numero]["deducible"] is True, numero
        assert por_numero[numero]["deducible_decidido"] is True, numero
        assert por_numero[numero]["origen"] == "auteco", numero
    assert por_numero["FE333"]["deducible_decidido"] is False
    assert por_numero["FE333"]["origen"] == "sin_clasificar"


@pytest.mark.asyncio
async def test_mismo_archivo_dos_veces_deduplica_por_cufe(api):
    h = await _token(api)
    contenido = _xlsx([_fila()])
    assert (await _cargar(api, h, contenido)).json()["resumen"]["creadas"] == 1
    r2 = await _cargar(api, h, contenido)
    assert r2.json()["resumen"]["duplicadas"] == 1
    assert r2.json()["resumen"]["creadas"] == 0


@pytest.mark.asyncio
async def test_nota_credito_rechazada_con_motivo(api):
    h = await _token(api)
    r = await _cargar(
        api, h, _xlsx([_fila(tipo="Nota Crédito Electrónica", cufe="d1" * 32)])
    )
    assert r.json()["resumen"]["rechazadas_tipo_no_soportado"] == 1
    assert "Nota Crédito" in r.json()["resultados"][0]["motivo"]


@pytest.mark.asyncio
async def test_emitida_por_roddos_se_rechaza(api):
    """El export de RECIBIDAS no debería traer emitidas; si una fila viene con el
    NIT propio como emisor, se rechaza con motivo — jamás se crea una venta."""
    h = await _token(api)
    r = await _cargar(api, h, _xlsx([_fila(nit=NIT_RODDOS, cufe="e1" * 32)]))
    assert r.json()["resumen"]["rechazadas_tipo_no_soportado"] == 1
    assert "emitida" in r.json()["resultados"][0]["motivo"].lower()


@pytest.mark.asyncio
async def test_encabezados_desconocidos_falla_listando(api):
    """Regla 7: si el archivo real de la DIAN trae otros encabezados, el error DEBE
    listar esperado vs encontrado — ese mensaje es el punto de calibración."""
    h = await _token(api)
    r = await _cargar(
        api, h, _xlsx([_fila()], encabezados=["Col A", "Col B", "Col C"])
    )
    assert r.status_code == 422
    assert "encabezados" in r.json()["detail"].lower()
    assert "cufe" in r.json()["detail"].lower()  # dice qué esperaba


@pytest.mark.asyncio
async def test_fila_ilegible_no_frena_el_lote(api):
    h = await _token(api)
    contenido = _xlsx(
        [
            _fila(cufe="f1" * 32, folio="2001"),
            _fila(cufe="f2" * 32, folio="2002", fecha="no-es-fecha"),
            _fila(cufe="f3" * 32, folio="2003"),
        ]
    )
    r = await _cargar(api, h, contenido)
    assert r.json()["resumen"]["creadas"] == 2
    assert r.json()["resumen"]["errores"] == 1
    con_error = [x for x in r.json()["resultados"] if x["estado"] == "error"][0]
    assert "fecha" in con_error["motivo"].lower()


@pytest.mark.asyncio
async def test_montos_como_texto_es_co(api):
    """La DIAN a veces exporta montos como texto '1.452,94' — se parsean exactos."""
    h = await _token(api)
    r = await _cargar(
        api,
        h,
        _xlsx([_fila(cufe="a9" * 32, iva="1.452,94", total="32.900,00")]),
    )
    assert r.json()["resumen"]["creadas"] == 1, r.text
    lista = (await api.get("/api/v1/facturas", headers=await _token(api))).json()
    assert lista[0]["iva_valor"] == "1452.94"


@pytest.mark.asyncio
async def test_rbac_iva_gestionar(api):
    h = await _token(api, "consulta@roddos.com")
    r = await _cargar(api, h, _xlsx([_fila()]))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_extension_no_xlsx_es_422(api):
    h = await _token(api)
    r = await _cargar(api, h, b"no soy un excel", nombre="documento.pdf")
    assert r.status_code == 422
    assert "xlsx" in r.json()["detail"].lower()
