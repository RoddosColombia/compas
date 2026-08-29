# backend/tests/test_reglas_semilla_service.py
"""RF-F1 paso 2 — servicio de propuesta (LECTURA PURA): lee la curaduría real de Mongo,
corre el generador y arma el reporte revisable. NO escribe nada (persistir es otro paso,
con aprobación del CEO). Aprende SOLO de rubros no-sistema (excluye «Por clasificar» y
los automáticos). Ignora transacciones divididas (una descripción en varios rubros)."""

from decimal import Decimal

import pytest
import pytest_asyncio
from app.domain import DOMAIN_DOCUMENTS
from app.domain.rubro import Rubro
from app.domain.transaccion import ParteClasificacion, Transaccion
from app.reglas.semilla_service import proponer_semilla
from beanie import PydanticObjectId, init_beanie
from mongomock_motor import AsyncMongoMockClient


@pytest_asyncio.fixture
async def db():
    c = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
    yield


async def _rubro(nombre, *, sistema=False, grupo="operacion"):
    r = Rubro(grupo=grupo, nombre=nombre, orden=1, es_sistema=sistema)
    await r.insert()
    return r


async def _tx(desc, rubro, tipo="egreso", *, partes=None):
    import app.core.ulid as u

    await Transaccion(
        fecha="2026-08-10",
        descripcion=desc,
        valor=Decimal("100000"),
        tipo_flujo=tipo,
        rubro_id=rubro.id,
        mes_id=PydanticObjectId(),
        banco="global66",
        id_banco=f"MAN-{u.new_ulid()}",
        partes=partes,
    ).insert()


@pytest.mark.asyncio
async def test_reporte_aprende_de_rubros_no_sistema(db):
    arr = await _rubro("Arriendos")
    porclasif = await _rubro("Por clasificar", sistema=True, grupo="otros")
    for _ in range(3):
        await _tx("Pago arriendo bodega norte", arr)
    await _tx("Movimiento sin clasificar equis", porclasif)

    rep = await proponer_semilla(min_evidencia=3)
    assert rep["total_movimientos"] == 3  # los de Por clasificar (sistema) NO cuentan
    pats = {p["patron"]: p for p in rep["propuestas"]}
    assert "arriendo" in pats
    r = pats["arriendo"]
    assert r["rubro"] == "Arriendos"
    assert r["evidencia"] == 3
    assert r["pureza"] == "1"
    assert r["colisiona"] is False
    assert any("arriendo" in e.lower() for e in r["ejemplos"])  # ejemplos reales


@pytest.mark.asyncio
async def test_ignora_transacciones_divididas(db):
    arr = await _rubro("Arriendos")
    nom = await _rubro("Sueldos", grupo="nomina")
    partes = [
        ParteClasificacion(rubro_id=arr.id, valor=Decimal("60000")),
        ParteClasificacion(rubro_id=nom.id, valor=Decimal("40000")),
    ]
    await _tx("Pago mixto arriendo y sueldo", arr, partes=partes)
    for _ in range(3):
        await _tx("Pago arriendo limpio", arr)

    rep = await proponer_semilla(min_evidencia=3)
    assert rep["total_movimientos"] == 3  # la dividida no entra
    pats = {p["patron"] for p in rep["propuestas"]}
    assert "arriendo" in pats
    assert "sueldo" not in pats  # solo venía de la dividida (ignorada)


@pytest.mark.asyncio
async def test_marca_colision_con_regla_activa_existente(db):
    from app.audit.service import configure_audit, reset_audit
    from app.reglas.service import crear_regla

    c = AsyncMongoMockClient(tz_aware=True)
    configure_audit(c, "compas_test")
    arr = await _rubro("Arriendos")
    for _ in range(3):
        await _tx("Pago arriendo bodega", arr)
    from app.domain.rubro import TipoFlujo

    await crear_regla(
        patron="arriendo",
        rubro_id=str(arr.id),
        tipo_flujo=TipoFlujo.EGRESO,
        prioridad=50,
        usuario_id="u-andres",
    )

    rep = await proponer_semilla(min_evidencia=3)
    r = next(p for p in rep["propuestas"] if p["patron"] == "arriendo")
    assert r["colisiona"] is True  # ya hay una regla activa con ese patrón
    reset_audit()


@pytest.mark.asyncio
async def test_sin_datos_reporte_vacio(db):
    rep = await proponer_semilla(min_evidencia=3)
    assert rep["total_movimientos"] == 0
    assert rep["propuestas"] == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
