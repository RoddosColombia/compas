# backend/tests/test_rf_f8_simular_negociacion.py
"""RF-F8 · Fundacional §2 — Obligaciones factura a factura: «negocia esta deuda».

Insight del mapa (spec-miner):
  · Auteco YA se proyecta factura a factura vía
    `obligaciones/reconciliacion.reconciliar`
    (D2 vive; `service._facturas_reconciliar` alimenta el pipeline en `_resultado_con`).
  · `_resultado_con(..., facturas_override=...)` inyecta una lista alternativa de
    `FacturaReconciliar` SIN escribir Mongo — es la puerta pública que RF-F8 necesita
    para simular "qué pasaría si negociara esta factura".
  · Motor sin tocar; regla 4 (histórico inmutable) intacta; regla 11 (catálogo audit
    cerrado) intacta — la simulación NO persiste, NO emite eventos audit.

Rebanada mínima (esta): SIMULACIÓN compute-only. El CEO explora "¿qué pasa si esta
factura pasa a 90 días?" y ve el impacto en piso y valles. La renegociación PERSISTIDA
queda para CR-RF-F8-B (necesita catálogo audit nuevo `factura_obligacion.editada`).

Contrato de `simular_negociacion_factura`:
  · Entrada: `factura_id` + al menos uno de `plazo_elegido_dias_nuevo` o
    `fecha_factura_nueva`. Sin cambios → 422 "nada que simular".
  · La factura debe existir, estar activa y NO estar pagada (409: negociación de
    factura pagada no tiene sentido; el pago ya salió de caja).
  · La obligación debe ser de naturaleza `facturacion` (no `cuotas`).
  · `plazo_elegido_dias_nuevo` debe estar en `[plazo_base_dias, plazo_max_dias]` (422).
  · Salida: `{piso_actual, piso_negociado, delta_piso, valles_actuales,
    valles_negociados, mes_pago_actual, mes_pago_negociado}` — todo string COP (regla 1)
    salvo listas.
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
from app.core.time import now_bogota
from app.domain import DOMAIN_DOCUMENTS
from app.domain.modelo_moto import ModeloMoto
from app.domain.obligacion import FacturaObligacion, Obligacion
from app.domain.parametros_proyeccion import ParametrosProyeccion
from app.main import create_app
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient

PWD = "clave-larga-1234"


async def _sembrar_config():
    """Config mínima para que el motor corra + una obligación de facturación con
    una factura pendiente que podamos "negociar"."""
    await ParametrosProyeccion(
        vigente_desde="2026-07-01",
        caja_inicial=Decimal("50000000"),
        caja_minima=Decimal("30000000"),
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


async def _sembrar_obligacion_con_factura() -> tuple[Obligacion, FacturaObligacion]:
    obl = await Obligacion(
        nombre="Auteco",
        acreedor="Auteco",
        naturaleza="facturacion",
        activo=True,
        es_sistema=False,
        creado_por="test",
        actualizado_at=now_bogota(),
        plazo_base_dias=90,
        plazo_max_dias=180,
        tasa_excedente_mensual=Decimal("0.016"),
    ).insert()
    factura = await FacturaObligacion(
        obligacion_id=obl.id,
        numero="F-001",
        fecha_factura="2026-09-01",
        valor=Decimal("100000000"),
        plazo_elegido_dias=90,
        activo=True,
        registrada_por="test",
        registrada_at=now_bogota(),
    ).insert()
    return obl, factura


async def _sembrar_obligacion_cuotas() -> Obligacion:
    return await Obligacion(
        nombre="Crédito banco",
        acreedor="Banco X",
        naturaleza="cuotas",
        activo=True,
        es_sistema=False,
        creado_por="test",
        actualizado_at=now_bogota(),
        monto_total=Decimal("50000000"),
        n_cuotas=12,
        periodicidad_meses=1,
        tasa_mensual=Decimal("0.02"),
        fecha_inicio="2026-09-01",
        meses_gracia=0,
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


# ─────────────────────────── contrato del servicio ───────────────────────────


@pytest.mark.asyncio
async def test_rff8_sin_cambios_es_422(api):
    """Al menos uno de plazo/fecha debe cambiar. Sin cambios: nada que simular."""
    from app.obligaciones.service import (
        ObligacionesError,
        simular_negociacion_factura,
    )

    _, factura = await _sembrar_obligacion_con_factura()
    with pytest.raises(ObligacionesError) as ex:
        await simular_negociacion_factura(
            factura_id=str(factura.id),
            plazo_elegido_dias_nuevo=None,
            fecha_factura_nueva=None,
        )
    assert ex.value.status == 422
    assert "nada" in ex.value.detalle.lower()


@pytest.mark.asyncio
async def test_rff8_factura_pagada_es_409(api):
    """No se negocia una factura ya pagada — el pago ya salió de caja."""
    from app.obligaciones.service import (
        ObligacionesError,
        simular_negociacion_factura,
    )

    _, factura = await _sembrar_obligacion_con_factura()
    factura.pagada_desde = "roddos"
    factura.pagada_at = "2026-11-30"
    factura.pagada_valor = factura.valor
    await factura.save()
    with pytest.raises(ObligacionesError) as ex:
        await simular_negociacion_factura(
            factura_id=str(factura.id),
            plazo_elegido_dias_nuevo=120,
        )
    assert ex.value.status == 409
    assert "pagada" in ex.value.detalle.lower()


@pytest.mark.asyncio
async def test_rff8_obligacion_de_cuotas_es_409(api):
    """La renegociación factura-a-factura solo aplica a naturaleza `facturacion`.
    Una obligación de tipo `cuotas` no tiene facturas registrables (mapper de
    service.py)."""
    from app.obligaciones.service import (
        ObligacionesError,
        simular_negociacion_factura,
    )

    obl_cuotas = await _sembrar_obligacion_cuotas()
    # Semilla artificial: una factura huérfana apuntando a la obligación cuotas —
    # protege contra data inconsistente en prod.
    f = await FacturaObligacion(
        obligacion_id=obl_cuotas.id,
        fecha_factura="2026-09-01",
        valor=Decimal("1000000"),
        plazo_elegido_dias=30,
        activo=True,
        registrada_por="test",
        registrada_at=now_bogota(),
    ).insert()
    with pytest.raises(ObligacionesError) as ex:
        await simular_negociacion_factura(
            factura_id=str(f.id),
            plazo_elegido_dias_nuevo=60,
        )
    assert ex.value.status == 409
    assert "facturacion" in ex.value.detalle.lower()


@pytest.mark.asyncio
async def test_rff8_plazo_fuera_de_rango_es_422(api):
    """`plazo_elegido_dias_nuevo` fuera de [plazo_base, plazo_max] de la obligación."""
    from app.obligaciones.service import (
        ObligacionesError,
        simular_negociacion_factura,
    )

    _, factura = await _sembrar_obligacion_con_factura()  # base=90, max=180
    with pytest.raises(ObligacionesError) as ex:
        await simular_negociacion_factura(
            factura_id=str(factura.id),
            plazo_elegido_dias_nuevo=210,
        )
    assert ex.value.status == 422
    assert "[90, 180]" in ex.value.detalle or "plazo" in ex.value.detalle.lower()


@pytest.mark.asyncio
async def test_rff8_alargar_plazo_no_persiste_cambios(api):
    """El compute-only NO escribe: tras simular, la factura queda EXACTAMENTE como
    estaba. Es la garantía de que RF-F8 es simulación pura."""
    from app.obligaciones.service import simular_negociacion_factura

    _, factura = await _sembrar_obligacion_con_factura()
    valor_original = factura.valor
    plazo_original = factura.plazo_elegido_dias
    fecha_original = factura.fecha_factura
    await simular_negociacion_factura(
        factura_id=str(factura.id),
        plazo_elegido_dias_nuevo=150,
    )
    tras = await FacturaObligacion.get(factura.id)
    assert tras is not None
    assert tras.valor == valor_original
    assert tras.plazo_elegido_dias == plazo_original
    assert tras.fecha_factura == fecha_original


@pytest.mark.asyncio
async def test_rff8_shape_de_salida(api):
    """La simulación devuelve: piso_actual, piso_negociado, delta_piso (COP str),
    mes_pago_actual, mes_pago_negociado (YYYY-MM), y listas de valles.

    Ojo semántica del delta: delta_piso = piso_negociado - piso_actual. Positivo
    significa que negociar MEJORA el piso (alargar plazo suele hacerlo)."""
    from app.obligaciones.service import simular_negociacion_factura

    _, factura = await _sembrar_obligacion_con_factura()
    r = await simular_negociacion_factura(
        factura_id=str(factura.id),
        plazo_elegido_dias_nuevo=180,
    )
    assert set(r) >= {
        "piso_actual",
        "piso_negociado",
        "delta_piso",
        "mes_pago_actual",
        "mes_pago_negociado",
        "valles_actuales",
        "valles_negociados",
    }
    # Los tres montos son strings decimales.
    for k in ("piso_actual", "piso_negociado", "delta_piso"):
        Decimal(r[k])  # no debe lanzar
    # El mes de pago cambia: 90 días desde 2026-09-01 → dic-2026;
    # 180 días desde 2026-09-01 → feb/mar-2027.
    assert r["mes_pago_actual"] != r["mes_pago_negociado"]
    # Convención YYYY-MM
    assert len(r["mes_pago_actual"]) == 7 and r["mes_pago_actual"][4] == "-"
    assert len(r["mes_pago_negociado"]) == 7


@pytest.mark.asyncio
async def test_rff8_alargar_plazo_mejora_piso_o_lo_deja_igual(api):
    """Alargar el plazo mueve el egreso a un mes posterior. En una proyección con
    piso en el corto plazo, el piso puede subir; en el peor caso queda igual (nunca
    peor: es la lectura financiera básica). Test blando: delta_piso >= 0."""
    from app.obligaciones.service import simular_negociacion_factura

    _, factura = await _sembrar_obligacion_con_factura()
    r = await simular_negociacion_factura(
        factura_id=str(factura.id),
        plazo_elegido_dias_nuevo=180,
    )
    assert Decimal(r["delta_piso"]) >= Decimal("0")


# ─────────────────────────── endpoint (integración) ───────────────────────────


@pytest.mark.asyncio
async def test_endpoint_simular_negociacion_devuelve_shape(api):
    """POST /obligaciones/{obl_id}/facturas/{fid}/simular con
    body {plazo_elegido_dias_nuevo} devuelve el shape completo.
    RBAC dashboard:leer (es lectura simulada)."""
    obl, factura = await _sembrar_obligacion_con_factura()
    h = await _token(api)
    r = await api.post(
        f"/api/v1/obligaciones/{obl.id}/facturas/{factura.id}/simular",
        headers=h,
        json={"plazo_elegido_dias_nuevo": 150},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) >= {
        "piso_actual",
        "piso_negociado",
        "delta_piso",
        "mes_pago_actual",
        "mes_pago_negociado",
        "valles_actuales",
        "valles_negociados",
    }


@pytest.mark.asyncio
async def test_endpoint_simular_negociacion_sin_cambios_es_422(api):
    obl, factura = await _sembrar_obligacion_con_factura()
    h = await _token(api)
    r = await api.post(
        f"/api/v1/obligaciones/{obl.id}/facturas/{factura.id}/simular",
        headers=h,
        json={},
    )
    assert r.status_code == 422


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
