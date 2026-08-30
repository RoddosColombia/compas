# backend/tests/test_rf_f4_techo_ventana.py
"""RF-F4 — Techo de gasto en VENTANA (Fundacional §2 RF-F4).

`techo_gasto_ventana(mes_inicio, ventana=9, referencia)` mira solo los primeros N
meses desde el arranque y usa el umbral de ATENCIÓN (D-1) como referencia — no el
mínimo. Levanta bandera roja si el valle DENTRO de la ventana perfora la atención,
aunque el horizonte completo cierre bien.

Este test es puro: le paso un `ResultadoProyeccion` esqueleto con la serie de caja
que quiero y verifico la matemática. El motor NO se toca (capa aditiva, igual patrón
que `techo_gasto`).
"""

from decimal import Decimal

import pytest
from app.proyeccion.motor import MesProyeccion, ResultadoProyeccion, _estado_caja
from app.proyeccion.solvers import techo_gasto_ventana

MIN = Decimal("30000000")  # crítico
ATN = Decimal("100000000")  # atención (D-1)


def _mes(idx: int, caja: Decimal, flujo: Decimal) -> MesProyeccion:
    y, m = 2026 + idx // 12, (idx % 12) + 1
    return MesProyeccion(
        mes=f"{y}-{m:02d}",
        motos=0,
        cartera=0,
        recaudo_credito=Decimal("0"),
        cuotas_iniciales=Decimal("0"),
        ingreso_bruto=Decimal("0"),
        neto=Decimal("0"),
        provision=Decimal("0"),
        gastos_fijos=Decimal("0"),
        gps=Decimal("0"),
        costo_nueva=Decimal("0"),
        adelanto=Decimal("0"),
        pago_inventario=Decimal("0"),
        fondeo=Decimal("0"),
        int_deuda=Decimal("0"),
        egresos=Decimal("0"),
        flujo=flujo,
        caja=caja,
        estado=_estado_caja(caja, MIN),
        iva=Decimal("0"),
        aval=Decimal("0"),
        mora=Decimal("0"),
        recuperacion=Decimal("0"),
        default=Decimal("0"),
    )


def _resultado(cajas: list[int]) -> ResultadoProyeccion:
    """Serie sintética: caja[m] = caja[m-1] + flujo[m]. `aplicar_impactos` reacumula
    desde flujo, así que seteamos flujos consistentes con las cajas objetivo (delta
    entre meses; flujo[0] = 0 porque el arranque es caja[0])."""
    valores = [Decimal(str(v * 1_000_000)) for v in cajas]
    meses = []
    for i, c in enumerate(valores):
        flujo = Decimal("0") if i == 0 else c - valores[i - 1]
        meses.append(_mes(i, c, flujo))
    return ResultadoProyeccion(
        meses=meses,
        piso_caja=min(m.caja for m in meses),
        mes_mas_ajustado=min(meses, key=lambda m: m.caja).mes,
        caja_final=meses[-1].caja,
        capital_requerido=Decimal("0"),
        runway_meses=None,
        meses_bajo_minimo=sum(1 for m in meses if m.caja < MIN),
    )


def test_rff4_ventana_ignora_meses_fuera_de_ventana():
    """La caja cae DESPUÉS de la ventana → dentro de la ventana no hay problema:
    hay holgura y no se perfora la atención."""
    # ventana 9 · caja se mantiene alta en 0..8 y cae en 9..
    r = _resultado([200] * 9 + [50] * 6)
    t = techo_gasto_ventana(r, MIN, ventana=9, referencia=ATN)
    assert t.perfora_atencion is False
    assert t.hay_holgura is True  # cabe algo de gasto en la ventana
    assert t.ventana == 9
    assert t.referencia == ATN


def test_rff4_valle_en_ventana_perfora_atencion_levanta_bandera():
    """El valle CAE dentro de la ventana bajo el umbral de atención (100M) aunque no
    perfore el crítico (30M): la bandera roja se levanta."""
    # mes 4 = 80M · < atención (100) pero > crítico (30) → perfora atención
    r = _resultado([200, 180, 150, 120, 80, 130, 150, 180, 200, 220, 240])
    t = techo_gasto_ventana(r, MIN, ventana=9, referencia=ATN)
    assert t.perfora_atencion is True
    # el mes limitante es el fondo dentro de la ventana
    assert t.valle_limitante_mes == "2026-05"  # index 4 → mayo (base 2026-01)


def test_rff4_sin_holgura_devuelve_techo_0_pero_reporta_estado():
    """La ventana ya perfora la atención SIN ajuste → techo = 0 pero seguimos
    reportando piso_actual y el mes limitante para la UI."""
    r = _resultado([200, 90, 60, 40, 200, 200, 200, 200, 200, 200])
    t = techo_gasto_ventana(r, MIN, ventana=9, referencia=ATN)
    assert t.hay_holgura is False
    assert t.techo_mensual == Decimal("0.00")
    assert t.perfora_atencion is True
    assert t.piso_resultante < ATN


def test_rff4_default_ventana_es_9():
    """El fundacional dice ventana=9 por default."""
    r = _resultado([200] * 12)
    t = techo_gasto_ventana(r, MIN, referencia=ATN)
    assert t.ventana == 9


def test_rff4_ventana_mas_larga_que_horizonte_se_recorta():
    """Si el caller pide ventana mayor al horizonte, se recorta silenciosamente al
    horizonte real (no truena, no adivina meses)."""
    r = _resultado([200] * 5)  # solo 5 meses
    t = techo_gasto_ventana(r, MIN, ventana=9, referencia=ATN)
    assert t.ventana == 5  # recortado al real


def test_rff4_referencia_none_cae_al_critico():
    """Si el CEO no configuró el umbral de atención, `referencia=None` significa
    'compórtate como techo_gasto de siempre' (referencia = crítico)."""
    # caja bajo atención (bajo 100M) pero sobre crítico (30M) → si referencia es None
    # (= crítico), no debe marcar bandera
    r = _resultado([200, 180, 150, 120, 80, 130, 150, 180, 200])
    t = techo_gasto_ventana(r, MIN, ventana=9, referencia=None)
    assert t.perfora_atencion is False  # 80 > 30 (crítico) → no perfora
    assert t.referencia == MIN


# ─────────────────────── Endpoint (integración pipeline) ───────────────────────


import httpx  # noqa: E402
import pytest_asyncio  # noqa: E402
from app.audit.service import configure_audit, reset_audit  # noqa: E402
from app.auth import passwords, repository  # noqa: E402
from app.auth.models import User  # noqa: E402
from app.auth.roles import Role  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.domain import DOMAIN_DOCUMENTS  # noqa: E402
from app.domain.configuracion import ClaveConfig, Configuracion  # noqa: E402
from app.domain.modelo_moto import ModeloMoto  # noqa: E402
from app.domain.parametros_proyeccion import ParametrosProyeccion  # noqa: E402
from app.main import create_app  # noqa: E402
from beanie import init_beanie  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

PWD = "clave-larga-1234"


async def _sembrar_config():
    """Config mínimo para correr proyectar_vigente y luego el solver de ventana."""
    await ParametrosProyeccion(
        vigente_desde="2026-07-01",
        caja_inicial=Decimal("50000000"),
        caja_minima=MIN,
        motos_base=10,
        crec_pct_mensual=Decimal("0"),
        horizonte_meses=12,
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
    await _sembrar_config()
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
async def test_endpoint_resolver_techo_gasto_ventana_devuelve_los_campos(api):
    """POST /proyeccion/resolver con objetivo=techo_gasto_ventana entrega todos los
    campos del RF-F4."""
    h = await _token(api)
    r = await api.post(
        "/api/v1/proyeccion/resolver?mes_inicio=2026-08",
        json={"objetivo": "techo_gasto_ventana", "ventana_meses": 9},
        headers=h,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["objetivo"] == "techo_gasto_ventana"
    for k in (
        "techo_mensual",
        "valle_limitante_mes",
        "piso_resultante",
        "referencia",
        "ventana",
        "hay_holgura",
        "perfora_atencion",
    ):
        assert k in body, f"falta {k}"
    assert body["ventana"] == 9


@pytest.mark.asyncio
async def test_endpoint_referencia_sube_a_atencion_cuando_esta_configurada(api):
    """Sin config: referencia = crítico. Con UMBRAL_ATENCION configurado alto: la
    referencia sube al umbral configurado — es la señal de RF-F3 · P1 enchufada
    con RF-F4."""
    h = await _token(api)
    r_sin = await api.post(
        "/api/v1/proyeccion/resolver?mes_inicio=2026-08",
        json={"objetivo": "techo_gasto_ventana"},
        headers=h,
    )
    assert r_sin.json()["referencia"] == str(MIN.quantize(Decimal("0.01")))

    await Configuracion(
        clave=ClaveConfig.UMBRAL_ATENCION,
        valor_decimal=Decimal("200000000"),
        vigente_desde="2026-08-01",
        modificado_por="u",
    ).insert()

    r_con = await api.post(
        "/api/v1/proyeccion/resolver?mes_inicio=2026-08",
        json={"objetivo": "techo_gasto_ventana"},
        headers=h,
    )
    assert r_con.json()["referencia"] == "200000000.00"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
