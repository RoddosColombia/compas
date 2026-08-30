# backend/tests/test_rf_f5_palancas_valles.py
"""RF-F5 · Fundacional §2 — Cada valle llega con sus 3 palancas listas para actuar.

`palancas_por_valle` es pura: dada una serie proyectada + un valle detectado, devuelve
el trío (recorte de gasto, ingreso extra, unidades extra) que llevaría el piso a la
referencia (atención si existe, si no crítico). Los solvers ya existen (RF-F4 usó
`goal_seek`, `techo_gasto`, `solver_unidades`): esta pieza solo enchufa los 3 sobre el
mismo valle y presenta una respuesta común.

Motor sin tocar; capa aditiva sobre `aplicar_impactos`. Golden-master intacto.
"""

from decimal import Decimal

import pytest
from app.proyeccion.motor import MesProyeccion, ResultadoProyeccion, _estado_caja
from app.proyeccion.service import _palancas_por_valle

MIN = Decimal("30000000")
ATN = Decimal("100000000")


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


def _valle(mes: str, caja: str) -> dict:
    """Shape mínimo que `_palancas_por_valle` necesita: solo el mes fondo."""
    return {"mes": mes, "caja": caja}


def test_rff5_palancas_devuelve_las_tres():
    """El contrato: siempre 3 palancas con nombres estables — recorte_gasto,
    ingreso_extra, unidades_extra."""
    r = _resultado([200, 180, 120, 80, 130, 180, 200])
    p = _palancas_por_valle(r, _valle("2026-04", "80000000"), MIN, ATN)
    assert set(p) == {"recorte_gasto", "ingreso_extra", "unidades_extra"}


def test_rff5_recorte_gasto_cierra_el_valle():
    """La palanca de gasto es un `goal_seek` con variable=gasto_absoluto: cuánto
    recortar/mes para que el piso quede en la referencia. Reporta el monto (COP) y
    alcanzable=True/False."""
    r = _resultado([200, 180, 120, 80, 130, 180, 200])
    p = _palancas_por_valle(r, _valle("2026-04", "80000000"), MIN, ATN)
    g = p["recorte_gasto"]
    assert g["alcanzable"] is True
    # necesita > 0 para subir de 80M a 100M
    assert Decimal(g["monto"]) > Decimal("0")
    assert g["unidad"] == "COP/mes"


def test_rff5_ingreso_extra_cierra_el_valle():
    r = _resultado([200, 180, 120, 80, 130, 180, 200])
    p = _palancas_por_valle(r, _valle("2026-04", "80000000"), MIN, ATN)
    i = p["ingreso_extra"]
    assert i["alcanzable"] is True
    assert Decimal(i["monto"]) > Decimal("0")
    assert i["unidad"] == "COP/mes"


def test_rff5_valle_holgado_devuelve_alcanzable_true_con_0():
    """Si el piso ya está sobre la referencia, no hace falta ajustar: monto=0."""
    r = _resultado([200, 180, 150, 130, 150, 180, 200])
    p = _palancas_por_valle(r, _valle("2026-04", "130000000"), MIN, ATN)
    # caja 130 > atención 100 → no perfora → montos = 0
    assert p["recorte_gasto"]["monto"] == "0" or p["recorte_gasto"]["monto"] == "0.00"
    assert p["ingreso_extra"]["monto"] == "0" or p["ingreso_extra"]["monto"] == "0.00"


def test_rff5_referencia_sin_atencion_cae_al_critico():
    """Sin `caja_atencion`, la referencia = crítico (comportamiento equivalente al
    techo clásico). Un valle a 80M > 30M crítico → alcanzable con montos=0."""
    r = _resultado([200, 180, 120, 80, 130, 180, 200])
    p = _palancas_por_valle(r, _valle("2026-04", "80000000"), MIN, caja_atencion=None)
    # 80M > 30M crítico → no hace falta actuar
    assert Decimal(p["recorte_gasto"]["monto"]) == Decimal("0")
    assert Decimal(p["ingreso_extra"]["monto"]) == Decimal("0")


# ─────────────────────── Endpoint (integración pipeline) ───────────────────────


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


async def _sembrar_config():
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
async def test_endpoint_valles_incluye_palancas_por_valle(api):
    """/proyeccion/valles ahora trae `palancas` (con las 3 claves) en cada valle."""
    h = await _token(api)
    r = await api.get("/api/v1/proyeccion/valles?mes_inicio=2026-08", headers=h)
    assert r.status_code == 200
    body = r.json()
    for v in body["valles"]:
        assert "palancas" in v
        assert set(v["palancas"]) == {
            "recorte_gasto",
            "ingreso_extra",
            "unidades_extra",
        }
        # Las de solvers deben traer monto/unidad/alcanzable; la de unidades
        # declara `disponible=False` (stub honesto).
        assert v["palancas"]["recorte_gasto"]["unidad"] == "COP/mes"
        assert v["palancas"]["unidades_extra"]["disponible"] is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
