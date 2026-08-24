# backend/tests/test_p2_arranque_heredado.py
"""P2 del ciclo mensual — EL ARRANQUE SE HEREDA DEL CIERRE.

Contrato: `docs/COMPAS_Ciclo_Mensual.md` §«Paso 0 · Arranque del mes».

    "No podemos perpetuar los datos de caja de junio para la proyección cuando ya vamos
    en agosto y la operación ya demandó inversiones y gastos que hacen que la caja
    disminuya." (CEO 2026-08-23)

En PROD la proyección arrancaba de `caja_inicial` = 704.722.003 (tecleado, el neto
acumulado mar–jul) mientras el ciclo tenía guardado el efectivo real del cierre de
julio:
665.715.578. El dato correcto existía y nadie lo leía.

**No hace falta pieza nueva:** el ciclo mensual ya deriva `saldo_inicial_caja` del
consolidado bancario del mes anterior (M-1/F-14) y ya permite tecleárselo con motivo y
evento de auditoría (`saldo_inicial.editado`, FIX-F). P2 es solo que la proyección lo
LEA, y que diga de dónde salió.

El arranque es `saldo_inicial_caja + tránsito heredado` — **la misma definición que
muestra la pantalla del ciclo** (`caja_inicial_total`). Si las dos pantallas dijeran
números distintos para "la plata con la que arranco el mes", el tejido estaría roto.
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
from app.domain.mes_control import EstadoMes, MesControl, SaldoBanco
from app.main import create_app
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient

PWD = "clave-larga-1234"
SEMILLA = "704722003"  # el `caja_inicial` tecleado que había en PROD
CIERRE_JULIO = Decimal("665715578")  # el efectivo real del cierre de julio


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
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _modelo_body():
    return {
        "nombre": "Raider",
        "costo_auteco": "6720557",
        "precio_venta_con_iva": "8000000",
        "cuota_inicial": "1620000",
        "cuota_semanal": "184900",
        "plazo_semanas": 78,
        "matricula": "500000",
        "participacion_mix": "1",
    }


def _params():
    return {
        "vigente_desde": "2026-08-01",
        "caja_inicial": SEMILLA,
        "caja_minima": "30000000",
        "motos_base": 60,
        "crec_pct_mensual": "0.10",
        "horizonte_meses": 12,
        "adelanto_auteco": "0",
        "plazo_auteco_dias": 150,
        "base_auteco_dias": 90,
        "tasa_auteco": "0.016",
        "gastos_fijos": "208000000",
        "gps_moto": "33201",
        "costo_moto_nueva": "691500",
        "deuda": "25000000",
        "tasa_deuda": "0.1157",
        "mes_inicio_deuda": 2,
        "meses_deuda": 14,
        "pct_mora": "0.08",
        "pct_recuperacion": "0.65",
        "pct_default": "0.03",
        "pct_provision": "0.02",
    }


async def _setup(ac) -> dict:
    h = await _token(ac)
    assert (
        await ac.post("/api/v1/modelos-moto", json=_modelo_body(), headers=h)
    ).status_code == 201
    assert (
        await ac.put("/api/v1/parametros-proyeccion", json=_params(), headers=h)
    ).status_code == 200
    return h


async def _sembrar_taxonomia() -> None:
    """Los 9 códigos del mapeo de E1 (B12 falla ruidoso al anclar si falta alguno). En
    PROD existen; en el test hay que sembrarlos para que el anclaje pueda correr."""
    from app.domain.rubro import Rubro, TipoFlujo

    plan = [
        ("0110", "ingresos_operativos", TipoFlujo.INGRESO),
        ("1010", "costo_producto", TipoFlujo.EGRESO),
        ("1020", "costo_producto", TipoFlujo.EGRESO),
        ("1030", "costo_producto", TipoFlujo.EGRESO),
        ("4010", "deudas_obligaciones", TipoFlujo.EGRESO),
        ("4020", "deudas_obligaciones", TipoFlujo.EGRESO),
        ("4030", "deudas_obligaciones", TipoFlujo.EGRESO),
        ("4040", "deudas_obligaciones", TipoFlujo.EGRESO),
        ("4050", "deudas_obligaciones", TipoFlujo.EGRESO),
        ("4070", "deudas_obligaciones", TipoFlujo.EGRESO),
        ("5060", "otros", TipoFlujo.EGRESO),
    ]
    for i, (cod, grupo, flujo) in enumerate(plan):
        await Rubro(
            grupo=grupo, nombre=f"Rubro {cod}", codigo=cod, tipo_flujo=flujo, orden=i
        ).insert()


async def _abrir_ciclo(*, transito: Decimal = Decimal("0")) -> None:
    """Julio CERRADO + agosto EN EJECUCIÓN con el efectivo real del cierre (la foto de
    PROD). `transito` = tránsito Wava declarado al cerrar julio (CR-WAVA)."""
    await _sembrar_taxonomia()
    await MesControl(
        mes="2026-07-01",
        estado=EstadoMes.CERRADO,
        saldo_inicial_caja=Decimal("814796138.93"),
        transito_wava=transito,
        saldos_banco=[
            SaldoBanco(banco="global66", saldo=CIERRE_JULIO, fecha_reporte="2026-07-31")
        ],
    ).insert()
    await MesControl(
        mes="2026-08-01",
        estado=EstadoMes.EN_EJECUCION,
        saldo_inicial_caja=CIERRE_JULIO,
        saldos_banco=[
            SaldoBanco(banco="global66", saldo=CIERRE_JULIO, fecha_reporte="2026-08-01")
        ],
    ).insert()


_Q = "horizonte_meses=12&mes_inicio=2026-08"


# ─────────────────────── el arranque sale del ciclo ───────────────────────


@pytest.mark.asyncio
async def test_la_proyeccion_arranca_del_efectivo_real_del_cierre(api):
    """El caso exacto de PROD: la semilla decía 704.722.003 y el cierre 665.715.578."""
    h = await _setup(api)
    await _abrir_ciclo()
    r = await api.get(f"/api/v1/proyeccion?{_Q}", headers=h)
    assert r.status_code == 200
    d = r.json()
    assert d["arranque"]["valor"] == "665715578.00"
    assert d["arranque"]["origen"] == "ciclo"
    assert d["arranque"]["mes"] == "2026-08"


@pytest.mark.asyncio
async def test_sin_ciclo_abierto_usa_la_semilla_y_lo_declara(api):
    """Sin MesControl del mes de inicio no se inventa nada: se usa `caja_inicial` y la
    respuesta dice que viene de la semilla (para que la pantalla pueda avisarlo)."""
    h = await _setup(api)
    r = await api.get(f"/api/v1/proyeccion?{_Q}", headers=h)
    assert r.status_code == 200
    d = r.json()
    assert d["arranque"]["valor"] == "704722003.00"
    assert d["arranque"]["origen"] == "semilla"


@pytest.mark.asyncio
async def test_el_arranque_incluye_el_transito_heredado(api):
    """CR-WAVA: la plata cobrada que aún no está en el banco es parte del arranque. Debe
    ser la MISMA definición que `caja_inicial_total` de la pantalla del ciclo."""
    h = await _setup(api)
    await _abrir_ciclo(transito=Decimal("12000000"))
    d = (await api.get(f"/api/v1/proyeccion?{_Q}", headers=h)).json()
    assert d["arranque"]["valor"] == "677715578.00"  # 665.715.578 + 12.000.000
    assert d["arranque"]["transito_heredado"] == "12000000.00"
    # y coincide con lo que reporta la pantalla del ciclo mensual
    ciclo = (await api.get("/api/v1/meses", headers=h)).json()
    agosto = next(m for m in ciclo["items"] if m["mes"].startswith("2026-08"))
    assert agosto["caja_inicial_total"] == d["arranque"]["valor"]


@pytest.mark.asyncio
async def test_teclear_el_saldo_mueve_la_proyeccion(api):
    """ "Se puede teclear si no coincide con la ejecución presupuestal" (CEO). El
    override
    ya existía (FIX-F, con motivo + evento `saldo_inicial.editado`); lo que P2 agrega es
    que la proyección lo respete."""
    h = await _setup(api)
    await _abrir_ciclo()
    antes = (await api.get(f"/api/v1/proyeccion?{_Q}", headers=h)).json()
    assert antes["arranque"]["valor"] == "665715578.00"

    mc = await MesControl.find_one(MesControl.mes == "2026-08-01")
    assert mc is not None
    from app.ciclo import service as ciclo_service

    await ciclo_service.editar_saldo_inicial(
        mes="2026-08-01",
        saldo_inicial_caja=Decimal("650000000"),
        motivo="arqueo del CEO: diferencia con la ejecución presupuestal",
        usuario_id="fin@roddos.com",
    )
    despues = (await api.get(f"/api/v1/proyeccion?{_Q}", headers=h)).json()
    assert despues["arranque"]["valor"] == "650000000.00"
    assert despues["arranque"]["origen"] == "ciclo"


# ─────────────────────── el arranque manda en la serie ───────────────────────


async def _mover_saldo(nuevo: Decimal) -> None:
    from app.ciclo import service as ciclo_service

    await ciclo_service.editar_saldo_inicial(
        mes="2026-08-01",
        saldo_inicial_caja=nuevo,
        motivo="prueba del candado",
        usuario_id="fin@roddos.com",
    )


@pytest.mark.asyncio
async def test_toda_la_serie_se_recalcula_sobre_el_nuevo_arranque(api):
    """No es un rótulo: mover el arranque mueve la caja de TODOS los meses exactamente
    esa diferencia, y no toca ni un peso de ingreso o egreso.

    Se aísla moviendo el saldo del ciclo (no comparando ciclo-abierto contra
    ciclo-cerrado: abrir el ciclo también enciende el anclaje E1, que sí cambia los
    egresos — son dos efectos distintos)."""
    h = await _setup(api)
    await _abrir_ciclo()
    antes = (await api.get(f"/api/v1/proyeccion?{_Q}", headers=h)).json()
    await _mover_saldo(CIERRE_JULIO - Decimal("39006425"))
    despues = (await api.get(f"/api/v1/proyeccion?{_Q}", headers=h)).json()

    for a, b in zip(antes["meses"], despues["meses"], strict=True):
        assert Decimal(a["caja"]) - Decimal(b["caja"]) == Decimal("39006425"), a["mes"]
        # el arranque NO toca ingresos ni egresos: solo el nivel de la caja
        assert a["neto"] == b["neto"]
        assert a["egresos"] == b["egresos"]
        assert a["flujo"] == b["flujo"]


@pytest.mark.asyncio
async def test_el_piso_y_el_capital_requerido_tambien_bajan(api):
    """Los KPI de decisión salen de la misma serie: si el arranque baja, el piso baja y
    el capital requerido sube. Si no se movieran, la pantalla estaría desincronizada de
    su propia tabla."""
    h = await _setup(api)
    await _abrir_ciclo()
    antes = (await api.get(f"/api/v1/proyeccion?{_Q}", headers=h)).json()
    await _mover_saldo(CIERRE_JULIO - Decimal("39006425"))
    despues = (await api.get(f"/api/v1/proyeccion?{_Q}", headers=h)).json()
    assert Decimal(antes["piso_caja"]) - Decimal(despues["piso_caja"]) == Decimal(
        "39006425"
    )
    assert Decimal(despues["capital_requerido"]) >= Decimal(antes["capital_requerido"])


@pytest.mark.asyncio
async def test_el_preview_usa_el_mismo_arranque_que_la_vigente(api):
    """C3: preview y vigente en paridad. Si el preview siguiera arrancando de la
    semilla,
    el panel de impacto mostraría deltas falsos."""
    h = await _setup(api)
    await _abrir_ciclo()
    vigente = (await api.get(f"/api/v1/proyeccion?{_Q}", headers=h)).json()
    campos = {k: v for k, v in _params().items() if k != "vigente_desde"}
    r = await api.post(
        f"/api/v1/proyeccion/preview?{_Q}",
        json={"parametros": campos},
        headers=h,
    )
    assert r.status_code == 200, r.text
    preview = r.json()
    assert preview["arranque"]["valor"] == vigente["arranque"]["valor"]
    assert [m["caja"] for m in preview["meses"]] == [
        m["caja"] for m in vigente["meses"]
    ]


@pytest.mark.asyncio
async def test_el_candado_aritmetico_se_sostiene_con_el_arranque_heredado(api):
    """P1 sobre la serie real del endpoint: caja(mes) = caja(mes−1) + flujo(mes) de el
    segundo mes en adelante (el primero es P3, declarado como xfail allá)."""
    h = await _setup(api)
    await _abrir_ciclo()
    meses = (await api.get(f"/api/v1/proyeccion?{_Q}", headers=h)).json()["meses"]
    for previo, fila in zip(meses, meses[1:], strict=False):
        esperado = (Decimal(previo["caja"]) + Decimal(fila["flujo"])).quantize(
            Decimal("0.01")
        )
        assert Decimal(fila["caja"]) == esperado, fila["mes"]
