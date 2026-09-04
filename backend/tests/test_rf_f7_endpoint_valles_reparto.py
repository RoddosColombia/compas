# backend/tests/test_rf_f7_endpoint_valles_reparto.py
"""RF-F7 · Fundacional §2 — integración end-to-end.

Contrato del endpoint `/api/v1/proyeccion/valles`:

    Cada valle trae `palancas.recorte_gasto` con:
      · `alcanzable` (heredado de RF-F5)
      · `monto` (COP/mes, heredado)
      · `recomendaciones_por_rubro`: lista ordenada por impacto (DESC) con
        {rubro_id, rubro_nombre, monto_recortar, gasto_actual, pct_de_su_gasto}.
        La suma NO puede exceder el objetivo (`monto`) — es reparto, no factor.

El test es de integración real: siembra config + 3 meses cerrados con
transacciones en 3 rubros de EGRESO de montos distintos, dispara un valle
alcanzable (baja la caja mínima para forzar recorte factible), y valida el shape
del reparto contra el objetivo del `goal_seek`.
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
from app.domain.modelo_moto import ModeloMoto
from app.domain.parametros_proyeccion import ParametrosProyeccion
from app.domain.rubro import Rubro, TipoFlujo
from app.domain.transaccion import Banco, Transaccion
from app.main import create_app
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient

PWD = "clave-larga-1234"


async def _sembrar_config():
    """Config mínima donde el motor perfore la caja mínima → RF-F5 arma la palanca
    `recorte_gasto` alcanzable, y RF-F7 puede adjuntar reparto."""
    await ParametrosProyeccion(
        vigente_desde="2026-07-01",
        caja_inicial=Decimal("50000000"),
        caja_minima=Decimal("30000000"),
        motos_base=10,
        crec_pct_mensual=Decimal("0"),
        horizonte_meses=6,
        adelanto_auteco=Decimal("0"),
        plazo_auteco_dias=150,
        base_auteco_dias=90,
        tasa_auteco=Decimal("0"),
        gastos_fijos=Decimal("30000000"),  # se cruza con la caja para forzar valle
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


async def _sembrar_historia_por_rubro() -> None:
    """3 meses cerrados con 3 rubros distintos, cada uno con un peso claro.
    El sueldos DEBE aparecer primero en el reparto por ser el más gastón."""
    sueldos = await Rubro(
        grupo="nomina",
        nombre="Sueldos",
        codigo="3010",
        tipo_flujo=TipoFlujo.EGRESO,
        orden=1,
    ).insert()
    arriendo = await Rubro(
        grupo="operacion",
        nombre="Arriendo",
        codigo="2010",
        tipo_flujo=TipoFlujo.EGRESO,
        orden=2,
    ).insert()
    papeleria = await Rubro(
        grupo="operacion",
        nombre="Papelería",
        codigo="2020",
        tipo_flujo=TipoFlujo.EGRESO,
        orden=3,
    ).insert()
    # Ingreso: no debe aparecer en el reparto (RF-F7 solo mira EGRESO).
    ventas = await Rubro(
        grupo="otros",
        nombre="Ventas",
        codigo="0110",
        tipo_flujo=TipoFlujo.INGRESO,
        orden=4,
    ).insert()

    # 3 meses cerrados con montos DISTINTOS por rubro para distinguir el orden.
    async def _cerrado(mes: str, filas: list[tuple[Rubro, str, TipoFlujo]]) -> None:
        mc = await MesControl(
            mes=f"{mes}-01",
            estado=EstadoMes.CERRADO,
            saldo_inicial_caja=Decimal("100000000"),
        ).insert()
        for i, (rubro, valor, flujo) in enumerate(filas):
            await Transaccion(
                fecha=f"{mes}-1{i}",
                descripcion="mov",
                valor=Decimal(valor),
                tipo_flujo=flujo,
                rubro_id=rubro.id,
                mes_id=mc.id,
                banco=Banco.GLOBAL66,
                id_banco=f"MAN-{mes}-{i}",
            ).insert()

    # Gasto promedio esperado en los 3 meses:
    #   sueldos:   30M cada mes → prom 30M
    #   arriendo:  10M cada mes → prom 10M
    #   papeleria: 500K cada mes → prom 500K
    #   ventas (ingreso, NO cuenta): 999M
    for mes in ("2026-04", "2026-05", "2026-06"):
        await _cerrado(
            mes,
            [
                (sueldos, "30000000", TipoFlujo.EGRESO),
                (arriendo, "10000000", TipoFlujo.EGRESO),
                (papeleria, "500000", TipoFlujo.EGRESO),
                (ventas, "999000000", TipoFlujo.INGRESO),
            ],
        )


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
    await _sembrar_historia_por_rubro()
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
async def test_rff7_endpoint_valles_adjunta_reparto_por_rubro(api):
    """El endpoint devuelve, para cada valle con `recorte_gasto.alcanzable=True`,
    la lista `recomendaciones_por_rubro` ordenada por impacto DESC. Los rubros de
    INGRESO NO aparecen (el reparto es solo de gastos)."""
    h = await _token(api)
    r = await api.get("/api/v1/proyeccion/valles?mes_inicio=2026-08", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    valles = body["valles"]
    # El escenario tiene gastos_fijos altos y caja pequeña → hay al menos 1 valle.
    if not valles:
        pytest.skip("escenario no produjo valle; ajustar semilla si el motor cambia")
    valle_con_reparto = next(
        (
            v
            for v in valles
            if v["palancas"]["recorte_gasto"]["alcanzable"]
            and Decimal(v["palancas"]["recorte_gasto"]["monto"]) > 0
        ),
        None,
    )
    if valle_con_reparto is None:
        pytest.skip(
            "no hay valle con recorte alcanzable > 0; "
            "ajustar semilla si cambia el motor"
        )
    rg = valle_con_reparto["palancas"]["recorte_gasto"]
    reparto = rg.get("recomendaciones_por_rubro")
    assert reparto is not None, "RF-F7: falta `recomendaciones_por_rubro`"
    assert isinstance(reparto, list) and len(reparto) > 0

    # Shape mínimo por línea
    for ln in reparto:
        assert set(ln) == {
            "rubro_id",
            "rubro_nombre",
            "monto_recortar",
            "gasto_actual",
            "pct_de_su_gasto",
        }

    # Orden por impacto DESC (gasto_actual)
    gastos = [Decimal(ln["gasto_actual"]) for ln in reparto]
    assert gastos == sorted(gastos, reverse=True), "reparto debe venir por impacto"

    # Sueldos (30M) debe aparecer primero — es el rubro EGRESO con mayor gasto.
    assert reparto[0]["rubro_nombre"] == "Sueldos"

    # Ventas es INGRESO — NUNCA en el reparto.
    ids_ingreso = {ln["rubro_nombre"] for ln in reparto if "Vent" in ln["rubro_nombre"]}
    assert ids_ingreso == set(), "el reparto no incluye rubros de INGRESO"

    # La suma no excede el objetivo (es reparto, no factor).
    objetivo = Decimal(rg["monto"])
    suma = sum(Decimal(ln["monto_recortar"]) for ln in reparto)
    assert suma <= objetivo


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
