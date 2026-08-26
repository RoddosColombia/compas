from decimal import Decimal

import pytest
from app.cfo.calc import escenario
from app.core.time import now_bogota


def _ref_horizonte() -> str:
    ahora = now_bogota()
    return f"{ahora.year:04d}-{ahora.month:02d}"


@pytest.mark.asyncio
async def test_impacto_arma_conceptos_y_mes_de_quiebre(monkeypatch):
    async def fake_impactos(*, ajustes, escenario, mes_inicio, horizonte_meses):
        return {
            "base": {"piso_caja": "100000000"},
            "ajustada": {
                "piso_caja": "40000000",
                "meses": [
                    {"mes": "2026-09", "estado": "ok", "caja": "90000000"},
                    {"mes": "2026-10", "estado": "ok", "caja": "60000000"},
                    {"mes": "2026-11", "estado": "critico", "caja": "40000000"},
                ],
            },
            "delta_por_mes": ["-20000000", "-20000000", "-20000000"],
        }

    monkeypatch.setattr(escenario.proy_service, "proyectar_impactos", fake_impactos)
    rs = await escenario.impacto_escenario(
        naturaleza="gasto", monto=Decimal("20000000"), mes_inicio="2026-09"
    )
    by = {r.concepto: r for r in rs}
    assert by["piso_sin"].valor == Decimal("100000000")
    assert by["piso_con"].valor == Decimal("40000000")
    assert by["piso_con"].evidencia.ref == "quiebre:2026-11"
    assert by["impacto_mensual"].valor == Decimal("20000000")
    assert all(r.disponible for r in rs)
    # Integridad de evidencia: piso_sin es la proyección BASE (independiente del
    # ajuste) — su ref es el ancla del HORIZONTE (mes de hoy, como runway.py), no el
    # mes_inicio del escenario hipotético ("2026-09"), que sugeriría falsamente que
    # el caso base varía con el escenario.
    ref_horizonte = _ref_horizonte()
    assert by["piso_sin"].evidencia.ref == ref_horizonte
    # impacto_mensual es el monto de ENTRADA ecoado (no algo que proyectar_impactos
    # calculó): su fuente debe decirlo, no atribuirlo al motor de proyección.
    assert by["impacto_mensual"].evidencia.fuente == "escenario (entrada)"
    assert by["impacto_mensual"].evidencia.ref == ref_horizonte
    # piso_con sí es un resultado real de proyectar_impactos: su fuente no cambia.
    assert by["piso_con"].evidencia.fuente == "proyeccion.service.proyectar_impactos"


@pytest.mark.asyncio
async def test_impacto_quiebre_nunca_si_ningun_mes_rompe(monkeypatch):
    async def fake_impactos(*, ajustes, escenario, mes_inicio, horizonte_meses):
        return {
            "base": {"piso_caja": "100000000"},
            "ajustada": {
                "piso_caja": "80000000",
                "meses": [
                    {"mes": "2026-09", "estado": "ok", "caja": "90000000"},
                    {"mes": "2026-10", "estado": "ok", "caja": "85000000"},
                    {"mes": "2026-11", "estado": "ok", "caja": "80000000"},
                ],
            },
            "delta_por_mes": ["-5000000", "-5000000", "-5000000"],
        }

    monkeypatch.setattr(escenario.proy_service, "proyectar_impactos", fake_impactos)
    rs = await escenario.impacto_escenario(
        naturaleza="gasto", monto=Decimal("5000000"), mes_inicio="2026-09"
    )
    by = {r.concepto: r for r in rs}
    assert by["piso_con"].evidencia.ref == "quiebre:nunca"


@pytest.mark.asyncio
async def test_impacto_quiebre_en_primer_mes_sin_off_by_one(monkeypatch):
    async def fake_impactos(*, ajustes, escenario, mes_inicio, horizonte_meses):
        return {
            "base": {"piso_caja": "100000000"},
            "ajustada": {
                "piso_caja": "10000000",
                "meses": [
                    {"mes": "2026-09", "estado": "critico", "caja": "10000000"},
                    {"mes": "2026-10", "estado": "critico", "caja": "5000000"},
                    {"mes": "2026-11", "estado": "negativo", "caja": "-1000000"},
                ],
            },
            "delta_por_mes": ["-90000000", "-90000000", "-90000000"],
        }

    monkeypatch.setattr(escenario.proy_service, "proyectar_impactos", fake_impactos)
    rs = await escenario.impacto_escenario(
        naturaleza="gasto", monto=Decimal("90000000"), mes_inicio="2026-09"
    )
    by = {r.concepto: r for r in rs}
    # El primer mes de la serie YA rompe: el quiebre es ese, no uno posterior.
    assert by["piso_con"].evidencia.ref == "quiebre:2026-09"


@pytest.mark.asyncio
async def test_impacto_abstiene_sin_config(monkeypatch):
    async def boom(**kw):
        raise escenario.ProyeccionError("sin config")

    monkeypatch.setattr(escenario.proy_service, "proyectar_impactos", boom)
    rs = await escenario.impacto_escenario(
        naturaleza="gasto", monto=Decimal("20000000"), mes_inicio="2026-09"
    )
    assert len(rs) == 1 and rs[0].disponible is False
