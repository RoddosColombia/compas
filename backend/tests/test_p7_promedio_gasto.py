# backend/tests/test_p7_promedio_gasto.py
"""P7 del ciclo mensual — EL PROMEDIO DE GASTO REAL SUGIERE EL SUPUESTO.

Contrato: `docs/COMPAS_Ciclo_Mensual.md` §«Paso 4 · Recálculo».

    "gasto hacia adelante = informado por el promedio de gasto real de los meses
    cerrados". Decisión del CEO 2026-08-23: promedio de los **3 meses cerrados** más
    recientes, y **SUGIERE** — el CEO lo aprueba en Supuestos, nunca lo reemplaza en
    silencio.

Hoy `gastos_fijos` es un número tecleado (208.000.000 en PROD) que nadie vuelve a mirar.
Esto le pone al lado la evidencia: lo que de verdad se gastó, promediado.

Dos decisiones de diseño que hacen la cifra comparable y honesta:

  · **El promedio es del CONCEPTO `gastos_fijos`, no del gasto total del mes.** Se
    calcula mapeando rubro→concepto con el MISMO mapeo de E1: el gasto total de un mes
    incluye Auteco, deudas y costo de producto, que el motor proyecta por otras vías.
    Comparar el total contra el supuesto de gastos fijos sería comparar peras con
    manzanas.
  · **Se dice sobre cuántos meses se promedió y cuáles.** Con menos de 3 cerrados se
    promedia lo que hay y se declara (hoy en PROD solo julio está cerrado). Sin ningún
    mes cerrado no hay sugerencia — no se inventa una.
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
from app.domain.rubro import Rubro, TipoFlujo
from app.domain.transaccion import Banco, Transaccion
from app.main import create_app
from app.parametros_proyeccion.sugerencias import promedio
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient

PWD = "clave-larga-1234"


# ─────────────────────────── la parte pura ───────────────────────────


def test_el_promedio_es_de_los_3_ULTIMOS_meses():
    """Ordenados de más viejo a más nuevo, se promedian los 3 finales."""
    valores = [
        ("2026-04", Decimal("100")),
        ("2026-05", Decimal("200")),
        ("2026-06", Decimal("300")),
        ("2026-07", Decimal("400")),
    ]
    r = promedio(valores, ventana=3)
    assert r is not None
    assert r["valor"] == Decimal("300.00")  # (200 + 300 + 400) / 3
    assert r["meses"] == ["2026-05", "2026-06", "2026-07"]


def test_con_menos_meses_promedia_los_que_hay_y_lo_declara():
    """PROD hoy: solo julio cerrado. Se promedia 1 mes y se dice que es 1."""
    r = promedio([("2026-07", Decimal("372200776.84"))], ventana=3)
    assert r is not None
    assert r["valor"] == Decimal("372200776.84")
    assert r["meses"] == ["2026-07"]
    assert r["n"] == 1


def test_sin_meses_cerrados_no_hay_sugerencia():
    """Regla 7: no se inventa un promedio de la nada."""
    assert promedio([], ventana=3) is None


def test_el_promedio_es_decimal_con_dos_decimales():
    """Regla 1: dinero en Decimal, nunca float; el redondeo es explícito."""
    r = promedio(
        [
            ("2026-05", Decimal("100")),
            ("2026-06", Decimal("100")),
            ("2026-07", Decimal("101")),
        ],
        ventana=3,
    )
    assert r is not None
    assert r["valor"] == Decimal("100.33")  # 301/3 = 100,333… → 2 decimales


# ─────────────────────────── el endpoint ───────────────────────────


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
        ("fin@roddos.com", Role.financiero),
        ("consulta@roddos.com", Role.consulta),
    ]:
        await repository.create_user(
            User(email=correo, password_hash=passwords.hash_password(PWD), rol=rol)
        )
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


async def _rubro(codigo: str, grupo: str, flujo=TipoFlujo.EGRESO) -> Rubro:
    return await Rubro(
        grupo=grupo, nombre=f"Rubro {codigo}", codigo=codigo, tipo_flujo=flujo, orden=1
    ).insert()


async def _sembrar_taxonomia() -> None:
    """Los códigos del mapeo rubro→concepto (B12 falla ruidoso si falta alguno). En PROD
    existen por C1; aquí hay que sembrarlos para que el mapeo pueda correr."""
    from app.proyeccion.ejecucion.lectura import _CONCEPTO_POR_CODIGO

    for cod in _CONCEPTO_POR_CODIGO:
        await Rubro(
            grupo="otros",
            nombre=f"Sistema {cod}",
            codigo=cod,
            tipo_flujo=TipoFlujo.EGRESO,
            orden=90,
        ).insert()


async def _mes_cerrado(mes: str, gastos: list[tuple[Rubro, str]]) -> MesControl:
    mc = await MesControl(
        mes=f"{mes}-01",
        estado=EstadoMes.CERRADO,
        saldo_inicial_caja=Decimal("100000000"),
    ).insert()
    for i, (rubro, valor) in enumerate(gastos):
        await Transaccion(
            fecha=f"{mes}-1{i}",
            descripcion="gasto",
            valor=Decimal(valor),
            tipo_flujo=TipoFlujo.EGRESO,
            rubro_id=rubro.id,
            mes_id=mc.id,
            banco=Banco.GLOBAL66,
            id_banco=f"MAN-{mes}-{i}",
        ).insert()
    return mc


@pytest.mark.asyncio
async def test_la_sugerencia_promedia_solo_el_concepto_gastos_fijos(api):
    """El gasto total del mes incluye Auteco/deudas/costo de producto, que el motor
    proyecta por otras vías. La sugerencia toma SOLO lo que el supuesto representa."""
    h = await _token(api)
    await _sembrar_taxonomia()
    arriendo = await _rubro("2010", "operacion")  # → concepto gastos_fijos
    auteco = await _rubro("1010", "costo_producto")  # → otra vía del motor
    deuda = await _rubro("4010", "deudas_obligaciones")  # → otra vía del motor
    await _mes_cerrado(
        "2026-07",
        [(arriendo, "200000000"), (auteco, "150000000"), (deuda, "45000000")],
    )
    r = await api.get("/api/v1/parametros-proyeccion/sugerencias", headers=h)
    assert r.status_code == 200
    s = r.json()["gastos_fijos"]
    assert s["valor"] == "200000000.00"  # solo el arriendo, no los 395 M totales
    assert s["meses"] == ["2026-07"]
    assert s["n"] == 1


@pytest.mark.asyncio
async def test_la_sugerencia_trae_el_detalle_mes_a_mes_y_el_vigente(api):
    """Para que el CEO decida viendo de dónde sale, no una cifra caída del cielo."""
    h = await _token(api)
    await _sembrar_taxonomia()
    arriendo = await _rubro("2010", "operacion")
    await _mes_cerrado("2026-05", [(arriendo, "180000000")])
    await _mes_cerrado("2026-06", [(arriendo, "200000000")])
    await _mes_cerrado("2026-07", [(arriendo, "220000000")])
    s = (await api.get("/api/v1/parametros-proyeccion/sugerencias", headers=h)).json()[
        "gastos_fijos"
    ]
    assert s["valor"] == "200000000.00"  # (180 + 200 + 220) / 3
    assert s["n"] == 3
    assert s["detalle"] == [
        {"mes": "2026-05", "valor": "180000000.00"},
        {"mes": "2026-06", "valor": "200000000.00"},
        {"mes": "2026-07", "valor": "220000000.00"},
    ]


@pytest.mark.asyncio
async def test_solo_cuenta_los_meses_CERRADOS(api):
    """Un mes en ejecución está a medias: su gasto parcial ensuciaría el promedio."""
    h = await _token(api)
    await _sembrar_taxonomia()
    arriendo = await _rubro("2010", "operacion")
    await _mes_cerrado("2026-07", [(arriendo, "200000000")])
    mc_ago = await MesControl(
        mes="2026-08-01",
        estado=EstadoMes.EN_EJECUCION,
        saldo_inicial_caja=Decimal("100000000"),
    ).insert()
    await Transaccion(
        fecha="2026-08-12",
        descripcion="parcial",
        valor=Decimal("50000000"),
        tipo_flujo=TipoFlujo.EGRESO,
        rubro_id=arriendo.id,
        mes_id=mc_ago.id,
        banco=Banco.GLOBAL66,
        id_banco="MAN-AGO",
    ).insert()
    s = (await api.get("/api/v1/parametros-proyeccion/sugerencias", headers=h)).json()[
        "gastos_fijos"
    ]
    assert s["meses"] == ["2026-07"]  # agosto NO entra
    assert s["valor"] == "200000000.00"


@pytest.mark.asyncio
async def test_sin_meses_cerrados_la_sugerencia_es_null(api):
    h = await _token(api)
    s = (await api.get("/api/v1/parametros-proyeccion/sugerencias", headers=h)).json()
    assert s["gastos_fijos"] is None


@pytest.mark.asyncio
async def test_la_sugerencia_NO_escribe_nada(api):
    """Lo esencial de P7: SUGIERE. El supuesto vigente no se toca: lo aprueba el
    CEO."""
    from app.domain.parametros_proyeccion import ParametrosProyeccion

    h = await _token(api)
    await _sembrar_taxonomia()
    arriendo = await _rubro("2010", "operacion")
    await _mes_cerrado("2026-07", [(arriendo, "200000000")])
    antes = await ParametrosProyeccion.find_all().to_list()
    await api.get("/api/v1/parametros-proyeccion/sugerencias", headers=h)
    despues = await ParametrosProyeccion.find_all().to_list()
    assert [p.model_dump() for p in antes] == [p.model_dump() for p in despues]


@pytest.mark.asyncio
async def test_rbac_la_sugerencia_pide_el_permiso_de_editar(api):
    """Es un insumo para EDITAR los supuestos: mismo permiso que el editor (C3)."""
    h = await _token(api, "consulta@roddos.com")
    r = await api.get("/api/v1/parametros-proyeccion/sugerencias", headers=h)
    assert r.status_code == 403
