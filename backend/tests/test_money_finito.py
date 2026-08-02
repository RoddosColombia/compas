# backend/tests/test_money_finito.py
"""FIX-A / A-3 (P1-8): rechazar montos no-finitos (Infinity/-Infinity/NaN).

MARCADO PARA AUDITORÍA KIMI (gate PR-FIX-A; hallazgo P1-8).

Decimal("Infinity") NO lanza InvalidOperation — es un Decimal válido — así que los
parsers lo aceptaban y envenenaba el mes (Infinity <= 0 es False → pasa las guardas;
queda en BSON; toda lectura posterior → 500 permanente). Defensa en dos capas:
core/money.py (dominio, ningún campo Money acepta veneno) + cada parser del API (422
limpio, no 500).
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
from app.core.money import Money, _coerce_decimal
from app.domain import DOMAIN_DOCUMENTS
from app.domain.mes_control import MesControl
from app.domain.rubro import Rubro
from app.domain.transaccion import Transaccion
from app.main import create_app
from beanie import init_beanie
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient
from pydantic import BaseModel

NO_FINITOS = ["Infinity", "-Infinity", "NaN"]


# ───────────────────────── capa 1: dominio (Money) ─────────────────────────


class _M(BaseModel):
    valor: Money


@pytest.mark.parametrize("txt", NO_FINITOS)
def test_coerce_decimal_rechaza_no_finito(txt):
    with pytest.raises(ValueError):
        _coerce_decimal(Decimal(txt))


@pytest.mark.parametrize("txt", NO_FINITOS)
def test_money_field_rechaza_no_finito(txt):
    with pytest.raises(ValueError):
        _M(valor=Decimal(txt))


def test_money_field_acepta_finito():
    assert _M(valor=Decimal("1000.00")).valor == Decimal("1000.00")


# ───────────────── capa 2: cada parser del API (422 limpio) ─────────────────
# Un representante por router (import directo del helper — sin DB).


@pytest.mark.parametrize("txt", NO_FINITOS)
def test_todos_los_parsers_rechazan_no_finito(txt):
    from app.ciclo.router import _decimal as ciclo_dec
    from app.facturas.router import _dec as fac_dec
    from app.gastos_recurrentes.router import _parse_monto as gastos_monto
    from app.metas_ingreso.router import _dec as metas_dec
    from app.modelos_moto.router import _dec as modelos_dec
    from app.obligaciones.router import _dec as obl_dec
    from app.pagos.router import _monto as pagos_monto
    from app.presupuesto.router import _parse_monto as presu_monto
    from app.proyeccion.router import _a_decimal as proy_dec
    from app.transacciones.router import _parse_valor as tx_valor

    llamadas = [
        lambda: tx_valor(txt),
        lambda: ciclo_dec(txt, "saldo"),
        lambda: fac_dec(txt, "iva_valor"),
        lambda: obl_dec(txt, "valor"),
        lambda: metas_dec(txt, "valor"),
        lambda: gastos_monto(txt),
        lambda: modelos_dec(txt, "precio"),
        lambda: presu_monto(txt),
        lambda: pagos_monto(txt),
        lambda: proy_dec(txt, "objetivo"),
    ]
    for llamar in llamadas:
        with pytest.raises(HTTPException) as ei:
            llamar()
        assert ei.value.status_code == 422


# ───────────────── el caso de la auditoría (endpoint real) ─────────────────


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
            password_hash=passwords.hash_password("clave-larga-1234"),
            rol=Role.financiero,
        )
    )
    await Rubro(
        grupo="otros", nombre="Por clasificar", orden=97, es_sistema=True
    ).insert()
    await MesControl(mes="2026-03-01", saldo_inicial_caja=Decimal("0")).insert()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, c
    repository.reset_auth()
    reset_audit()
    get_settings.cache_clear()


async def test_post_transaccion_infinity_es_422_sin_insert(api):
    # El caso exacto de la auditoría: hoy 500 con la tx persistida; debe ser 422 y 0.
    ac, _ = api
    r = await ac.post(
        "/api/v1/auth/login",
        json={"email": "fin@roddos.com", "password": "clave-larga-1234"},
    )
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    resp = await ac.post(
        "/api/v1/transacciones",
        json={
            "fecha": "2026-03-15",
            "descripcion": "VENENO",
            "valor": "Infinity",
            "tipo_flujo": "egreso",
        },
        headers={**h, "Idempotency-Key": "inf-001"},
    )
    assert resp.status_code == 422
    assert await Transaccion.find_one() is None
