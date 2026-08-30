# backend/tests/test_rf_f10_agregacion.py
"""RF-F10 · Fundacional §2 — «Horizonte a 240 meses con agregación por año/trimestre».

Contexto (mapa):
  · Hoy `HORIZONTE_MAX = 180` (15 años, tope de infraestructura) en
    proyeccion/service.py:72; validado también en el dominio
    ParametrosProyeccion.horizonte_meses (`le=180`).
  · Mostrar 240 puntos mensuales es ruido para lecturas de largo plazo — la
    agregación por trimestre/año es lo que hace usable el horizonte largo.
  · El motor genera series MENSUALES; no se toca (regla del motor intocable,
    golden-master 176 meses). La agregación es capa post-motor pura.

RF-F10 introduce `agregar_por_periodo(meses, granularidad)`:
  · `granularidad = "trimestre" | "anual"` (mensual no necesita agregador).
  · Semántica CONSERVADORA:
      - `caja_final`: caja del ÚLTIMO mes del periodo (es STOCK — no se suma).
      - `piso`: MIN caja durante el periodo (útil para «el trimestre peor»).
      - `flujo` / `ingreso_bruto` / `egresos`: SUMA (son FLUJO — se acumulan).
      - `motos`: SUMA (unidades vendidas en el periodo).
      - `etiqueta`: `"2027"` (anual) o `"2027-Q3"` (trimestre).
      - `desde` / `hasta`: primer y último mes YYYY-MM del periodo.
  · Todos los montos como Decimal (regla 1); COP como string en la salida
    serializable a JSON.

Motor sin tocar. Ajuste HORIZONTE_MAX 180 → 240 se prueba aparte (endpoint).
"""

from decimal import Decimal

import pytest
from app.proyeccion.agregacion import agregar_por_periodo
from app.proyeccion.motor import MesProyeccion, _estado_caja


def _mes(
    y: int, m: int, caja: str, flujo: str, ing: str, egr: str, motos: int,
) -> MesProyeccion:
    caja_dec = Decimal(caja)
    return MesProyeccion(
        mes=f"{y:04d}-{m:02d}",
        motos=motos,
        cartera=0,
        recaudo_credito=Decimal("0"),
        cuotas_iniciales=Decimal("0"),
        ingreso_bruto=Decimal(ing),
        neto=Decimal("0"),
        provision=Decimal("0"),
        gastos_fijos=Decimal("0"),
        gps=Decimal("0"),
        costo_nueva=Decimal("0"),
        adelanto=Decimal("0"),
        pago_inventario=Decimal("0"),
        fondeo=Decimal("0"),
        int_deuda=Decimal("0"),
        egresos=Decimal(egr),
        flujo=Decimal(flujo),
        caja=caja_dec,
        estado=_estado_caja(caja_dec, Decimal("0")),
        iva=Decimal("0"),
        aval=Decimal("0"),
        mora=Decimal("0"),
        recuperacion=Decimal("0"),
        default=Decimal("0"),
    )


def _serie_de_prueba() -> list[MesProyeccion]:
    """15 meses arrancando en 2026-11 → cubre trimestres 2026-Q4 (nov-dic),
    2027-Q1/Q2/Q3/Q4 (parcial), y años 2026 (parcial) y 2027."""
    valores = [
        # (y, m, caja, flujo, ing, egr, motos)
        (2026, 11, "100", "10", "50", "40", 10),
        (2026, 12, "110", "10", "50", "40", 10),
        (2027, 1, "115", "5", "60", "55", 12),
        (2027, 2, "120", "5", "60", "55", 12),
        (2027, 3, "90", "-30", "20", "50", 5),
        (2027, 4, "95", "5", "60", "55", 12),
        (2027, 5, "100", "5", "60", "55", 12),
        (2027, 6, "105", "5", "60", "55", 12),
        (2027, 7, "110", "5", "60", "55", 12),
        (2027, 8, "115", "5", "60", "55", 12),
        (2027, 9, "120", "5", "60", "55", 12),
        (2027, 10, "125", "5", "60", "55", 12),
        (2027, 11, "130", "5", "60", "55", 12),
        (2027, 12, "135", "5", "60", "55", 12),
        (2028, 1, "140", "5", "60", "55", 12),
    ]
    return [_mes(*args) for args in valores]


# ─────────────────────────── contrato del agregador ───────────────────────────


def test_rff10_granularidad_invalida_lanza_error():
    """La granularidad soportada es solo `trimestre` | `anual`. Con `mensual`
    debemos devolver la serie tal cual (identidad) — pero solo si el caller la
    pide explícita; un valor desconocido rompe."""
    with pytest.raises(ValueError):
        agregar_por_periodo(_serie_de_prueba(), granularidad="dia")


def test_rff10_serie_vacia_devuelve_lista_vacia():
    """Serie sin meses → cero periodos. No divide por cero, no lanza."""
    assert agregar_por_periodo([], granularidad="anual") == []
    assert agregar_por_periodo([], granularidad="trimestre") == []


def test_rff10_agregacion_anual_etiquetas_y_ventanas():
    """Anual: hay 3 años en la serie de prueba (2026 parcial, 2027 completo,
    2028 parcial). Etiquetas son 'YYYY'. `desde`/`hasta` son primer/último mes
    del año con datos, no bordes del calendario (2026 parcial arranca en nov)."""
    r = agregar_por_periodo(_serie_de_prueba(), granularidad="anual")
    etiquetas = [p["etiqueta"] for p in r]
    assert etiquetas == ["2026", "2027", "2028"]
    assert r[0]["desde"] == "2026-11" and r[0]["hasta"] == "2026-12"
    assert r[1]["desde"] == "2027-01" and r[1]["hasta"] == "2027-12"
    assert r[2]["desde"] == "2028-01" and r[2]["hasta"] == "2028-01"


def test_rff10_agregacion_anual_semantica_stock_vs_flujo():
    """`caja_final` = caja del ÚLTIMO mes del periodo (stock, no suma).
    `piso` = min caja durante el periodo (STOCK, muestra el punto más bajo).
    `flujo` = SUMA de flujos mensuales.
    `motos` = SUMA de unidades.
    """
    r = agregar_por_periodo(_serie_de_prueba(), granularidad="anual")
    # 2026 parcial (nov=100, dic=110): caja_final=110, piso=100, flujo=20, motos=20.
    p26 = next(p for p in r if p["etiqueta"] == "2026")
    assert Decimal(p26["caja_final"]) == Decimal("110")
    assert Decimal(p26["piso"]) == Decimal("100")
    assert Decimal(p26["flujo"]) == Decimal("20")
    assert p26["motos"] == 20
    # 2027 completo: caja_final=135 (dic), piso=90 (mar), motos=137 (11 meses
    # a 12 + mar=5 = 132+5).
    p27 = next(p for p in r if p["etiqueta"] == "2027")
    assert Decimal(p27["caja_final"]) == Decimal("135")
    assert Decimal(p27["piso"]) == Decimal("90")
    assert p27["motos"] == 137


def test_rff10_agregacion_trimestral_etiquetas_ordenadas():
    """Trimestre: etiquetas 'YYYY-Qn' (n=1..4). Van en orden cronológico y
    solo aparecen los trimestres con datos."""
    r = agregar_por_periodo(_serie_de_prueba(), granularidad="trimestre")
    etiquetas = [p["etiqueta"] for p in r]
    assert etiquetas == [
        "2026-Q4",
        "2027-Q1",
        "2027-Q2",
        "2027-Q3",
        "2027-Q4",
        "2028-Q1",
    ]


def test_rff10_agregacion_trimestral_piso_es_min_del_trimestre():
    """2027-Q1 (ene=115, feb=120, mar=90): piso=90 (mar), caja_final=90 (mar es
    el último mes del trimestre)."""
    r = agregar_por_periodo(_serie_de_prueba(), granularidad="trimestre")
    q1 = next(p for p in r if p["etiqueta"] == "2027-Q1")
    assert Decimal(q1["piso"]) == Decimal("90")
    assert Decimal(q1["caja_final"]) == Decimal("90")
    # ingreso_bruto Q1 = 60+60+20 = 140; egresos Q1 = 55+55+50 = 160.
    assert Decimal(q1["ingreso_bruto"]) == Decimal("140")
    assert Decimal(q1["egresos"]) == Decimal("160")


def test_rff10_montos_como_string_decimal_no_float():
    """Regla 1: montos serializables como string; nunca float. Se puede parsear
    con Decimal() sin pérdida."""
    r = agregar_por_periodo(_serie_de_prueba(), granularidad="anual")
    for p in r:
        for campo in ("caja_final", "piso", "flujo", "ingreso_bruto", "egresos"):
            assert isinstance(p[campo], str), campo
            Decimal(p[campo])  # no debe lanzar


def test_rff10_periodo_incompleto_lo_declara():
    """2026 solo tiene nov y dic (no completo); 2027 tiene los 12 meses; 2028
    solo tiene enero. El caller debe poder distinguir «año parcial» de «año
    completo» — cada periodo trae `meses_en_periodo`."""
    r = agregar_por_periodo(_serie_de_prueba(), granularidad="anual")
    ns = {p["etiqueta"]: p["meses_en_periodo"] for p in r}
    assert ns == {"2026": 2, "2027": 12, "2028": 1}


# ─────────────────────────── endpoint (integración) ───────────────────────────


import httpx  # noqa: E402
import pytest_asyncio  # noqa: E402
from app.audit.service import configure_audit, reset_audit  # noqa: E402
from app.auth import passwords, repository  # noqa: E402
from app.auth.models import User  # noqa: E402
from app.auth.roles import Role  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.domain import DOMAIN_DOCUMENTS  # noqa: E402
from app.domain.modelo_moto import ModeloMoto  # noqa: E402
from app.domain.parametros_proyeccion import ParametrosProyeccion  # noqa: E402
from app.main import create_app  # noqa: E402
from beanie import init_beanie  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

PWD = "clave-larga-1234"


async def _sembrar_config(horizonte: int = 12):
    """Config mínima que corre el motor con un horizonte pedido."""
    await ParametrosProyeccion(
        vigente_desde="2026-07-01",
        caja_inicial=Decimal("50000000"),
        caja_minima=Decimal("30000000"),
        motos_base=10,
        crec_pct_mensual=Decimal("0"),
        horizonte_meses=horizonte,
        adelanto_auteco=Decimal("0"),
        plazo_auteco_dias=150,
        base_auteco_dias=90,
        tasa_auteco=Decimal("0"),
        gastos_fijos=Decimal("30000000"),
        gps_moto=Decimal("0"),
        costo_moto_nueva=Decimal("0"),
        deuda=Decimal("0"),
        tasa_deuda=Decimal("0"),
        mes_inicio_deuda=0,
        meses_deuda=0,
        pct_mora=Decimal("0"),
        pct_recuperacion=Decimal("0"),
        pct_default=Decimal("0"),
        pct_provision=Decimal("0"),
    ).insert()
    await ModeloMoto(
        nombre="Raider",
        costo_auteco=Decimal("0"),
        precio_venta_con_iva=Decimal("0"),
        cuota_inicial=Decimal("1000000"),
        cuota_semanal=Decimal("100000"),
        plazo_semanas=78,
        matricula=Decimal("0"),
        participacion_mix=Decimal("1"),
        orden=0,
    ).insert()


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
    await repository.create_user(
        User(
            email="fin@roddos.com",
            password_hash=passwords.hash_password(PWD),
            rol=Role.financiero,
        )
    )
    await _sembrar_config(horizonte=12)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    repository.reset_auth()
    reset_audit()
    get_settings.cache_clear()


async def _token(ac) -> dict:
    r = await ac.post(
        "/api/v1/auth/login", json={"email": "fin@roddos.com", "password": PWD}
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.mark.asyncio
async def test_endpoint_agregada_anual_devuelve_periodos(api):
    """GET /proyeccion/agregada?granularidad=anual → `{periodos: [...]}` con
    etiquetas 'YYYY' y shape completo por periodo."""
    h = await _token(api)
    r = await api.get(
        "/api/v1/proyeccion/agregada?granularidad=anual&mes_inicio=2026-08",
        headers=h,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "periodos" in body
    periodos = body["periodos"]
    assert len(periodos) >= 1
    # Etiqueta 'YYYY', montos como string COP.
    for p in periodos:
        assert set(p) >= {
            "etiqueta",
            "desde",
            "hasta",
            "meses_en_periodo",
            "caja_final",
            "piso",
            "flujo",
            "ingreso_bruto",
            "egresos",
            "motos",
        }
        assert len(p["etiqueta"]) == 4  # 'YYYY'
        Decimal(p["caja_final"])  # no debe lanzar


@pytest.mark.asyncio
async def test_endpoint_agregada_trimestre_etiquetas_Qn(api):
    h = await _token(api)
    r = await api.get(
        "/api/v1/proyeccion/agregada?granularidad=trimestre&mes_inicio=2026-08",
        headers=h,
    )
    assert r.status_code == 200
    for p in r.json()["periodos"]:
        assert "-Q" in p["etiqueta"]  # 'YYYY-Q1'..'YYYY-Q4'


@pytest.mark.asyncio
async def test_endpoint_agregada_granularidad_mensual_es_422(api):
    """`mensual` no se sirve por este endpoint (se usa GET /proyeccion directo).
    Endpoint solo para agregaciones — pedirlo con 'mensual' es error de uso."""
    h = await _token(api)
    r = await api.get(
        "/api/v1/proyeccion/agregada?granularidad=mensual&mes_inicio=2026-08",
        headers=h,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_endpoint_agregada_horizonte_240_ok(api):
    """RF-F10 sube HORIZONTE_MAX de 180 → 240. Confirma que el endpoint acepta
    240 meses (piezas críticas son el motor + la agregación — no debe romper)."""
    h = await _token(api)
    r = await api.get(
        "/api/v1/proyeccion/agregada?granularidad=anual"
        "&mes_inicio=2026-08&horizonte_meses=240",
        headers=h,
    )
    assert r.status_code == 200
    # 240 meses / 12 = 20 años, empezando en agosto 2026 → 2026..2046 (21 años
    # parciales/completos, al menos 20).
    assert len(r.json()["periodos"]) >= 20


@pytest.mark.asyncio
async def test_endpoint_agregada_horizonte_mayor_a_240_es_422(api):
    h = await _token(api)
    r = await api.get(
        "/api/v1/proyeccion/agregada?granularidad=anual"
        "&mes_inicio=2026-08&horizonte_meses=241",
        headers=h,
    )
    assert r.status_code == 422


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
