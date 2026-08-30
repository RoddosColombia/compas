# backend/tests/proyeccion/test_impacto_palanca_raw.py
"""inc4 rebanada 2 (Task 1) — `impacto_palanca_raw` re-corre el pipeline COMPLETO
(`_resultado_con`: motor → E1 → D2) con un override de `ModeloMoto` (plazo/cuota
inicial/cuota semanal) y devuelve `PalancaImpacto` (piso_sin, piso_con, mes_quiebre,
impacto) en tipos planos (Decimal/str) — sin que `cfo/calc` tenga que importar
`app.domain.*` (aislamiento S1). Aquí se monkeypatchea `_resultado_con` y
`modelos_service.listar_modelos`/`parametros_service.obtener_vigente` para no tocar
Mongo/motor real."""

from dataclasses import dataclass
from decimal import Decimal

import pytest
from app.domain.modelo_moto import ModeloMoto
from app.domain.parametros_proyeccion import ParametrosProyeccion
from app.proyeccion import service as svc


async def _aw(value):
    """Coroutine mínima que resuelve a `value` — para monkeypatchear funciones
    async con `lambda ...: _aw(valor)`."""
    return value


def _vig() -> ParametrosProyeccion:
    """Un `ParametrosProyeccion` mínimo válido (mismo patrón que
    `tests/test_e1_pipeline.py::_params`)."""
    return ParametrosProyeccion(
        vigente_desde="2026-09-01",
        caja_inicial=Decimal("500000"),
        caja_minima=Decimal("10000"),
        motos_base=2,
        crec_pct_mensual=Decimal("0"),
        horizonte_meses=12,
        adelanto_auteco=Decimal("0"),
        plazo_auteco_dias=60,
        base_auteco_dias=30,
        tasa_auteco=Decimal("0.016"),
        gastos_fijos=Decimal("1000"),
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
    )


def _modelo(
    nombre: str, plazo: int = 52, ci: str = "500000", cs: str = "80000"
) -> ModeloMoto:
    """Un `ModeloMoto` mínimo válido (mismo patrón que
    `tests/test_e1_pipeline.py::_modelos`)."""
    return ModeloMoto(
        nombre=nombre,
        costo_auteco=Decimal("1"),
        precio_venta_con_iva=Decimal("1"),
        cuota_inicial=Decimal(ci),
        cuota_semanal=Decimal(cs),
        plazo_semanas=plazo,
        matricula=Decimal("0"),
        participacion_mix=Decimal("0.5"),
        orden=1,
    )


@dataclass
class _Mes:
    mes: str
    estado: str


@dataclass
class _R:
    piso_caja: Decimal
    meses: list


@pytest.mark.asyncio
async def test_impacto_palanca_plazo_todos(monkeypatch):
    modelos = [_modelo("Raider", 52), _modelo("Apache", 52)]
    monkeypatch.setattr(
        svc.modelos_service, "listar_modelos", lambda activo=True: _aw(modelos)
    )
    monkeypatch.setattr(svc.parametros_service, "obtener_vigente", lambda: _aw(_vig()))
    llamadas = []

    async def fake_rc(params, mods, *, escenario, mes_inicio, horizonte_meses, **kw):
        # base: plazo 52 -> piso 100M ; con: algún modelo a 78 -> piso 120M + nunca
        plazos = tuple(m.plazo_semanas for m in mods)
        llamadas.append(plazos)
        piso = Decimal("120000000") if 78 in plazos else Decimal("100000000")
        return (_R(piso, [_Mes("2026-09", "ok")]), None, [], None, None, None)

    monkeypatch.setattr(svc, "_resultado_con", fake_rc)
    out = await svc.impacto_palanca_raw(
        palanca="plazo_semanas",
        nuevo_valor=Decimal("78"),
        modelo="todos",
        escenario="base",
        mes_inicio=(2026, 9),
        horizonte_meses=None,
    )
    assert out.piso_sin == Decimal("100000000")
    assert out.piso_con == Decimal("120000000")
    assert out.impacto == Decimal("20000000")
    assert out.mes_quiebre == "nunca"
    assert llamadas[1] == (78, 78)  # "todos" -> ambos modelos a 78


@pytest.mark.asyncio
async def test_impacto_palanca_modelo_especifico(monkeypatch):
    modelos = [_modelo("Raider", 52), _modelo("Apache", 52)]
    monkeypatch.setattr(
        svc.modelos_service, "listar_modelos", lambda activo=True: _aw(modelos)
    )
    monkeypatch.setattr(svc.parametros_service, "obtener_vigente", lambda: _aw(_vig()))
    vistos = []

    async def fake_rc(params, mods, **kw):
        vistos.append(tuple((m.nombre, m.plazo_semanas) for m in mods))
        return (
            _R(Decimal("50000000"), [_Mes("2026-11", "critico")]),
            None,
            [],
            None,
            None,
            None,
        )

    monkeypatch.setattr(svc, "_resultado_con", fake_rc)
    out = await svc.impacto_palanca_raw(
        palanca="plazo_semanas",
        nuevo_valor=Decimal("78"),
        modelo="Raider",
        escenario="base",
        mes_inicio=(2026, 9),
        horizonte_meses=None,
    )
    assert vistos[1] == (("Raider", 78), ("Apache", 52))  # solo Raider cambió
    assert out.mes_quiebre == "2026-11"


@pytest.mark.asyncio
async def test_impacto_palanca_modelo_desconocido_abstiene(monkeypatch):
    monkeypatch.setattr(
        svc.modelos_service,
        "listar_modelos",
        lambda activo=True: _aw([_modelo("Raider")]),
    )
    monkeypatch.setattr(svc.parametros_service, "obtener_vigente", lambda: _aw(_vig()))
    with pytest.raises(svc.ProyeccionError):
        await svc.impacto_palanca_raw(
            palanca="plazo_semanas",
            nuevo_valor=Decimal("78"),
            modelo="Ghost",
            escenario="base",
            mes_inicio=(2026, 9),
            horizonte_meses=None,
        )
