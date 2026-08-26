from decimal import Decimal
from types import SimpleNamespace

import pytest
from app.cfo.calc import escenario
from app.core.time import now_bogota


def _ref_horizonte() -> str:
    ahora = now_bogota()
    return f"{ahora.year:04d}-{ahora.month:02d}"


def _fake_vigente(
    *,
    caja_minima: Decimal,
    motos_base: int = 78,
    horizonte_meses: int = 60,
):
    """Factory para parchar `escenario.params_service.obtener_vigente`: un objeto
    liviano con `.caja_minima`/`.motos_base`/`.horizonte_meses` (lo que
    `motos_para_evitar_umbral` lee de `vig` ANTES de delegar en `_proyectar_fn_para`,
    que en estos tests va fakeado aparte). Devuelve el callable async de 0 args que
    monkeypatch necesita para reemplazar `obtener_vigente`."""
    vig = SimpleNamespace(
        caja_minima=caja_minima,
        motos_base=motos_base,
        horizonte_meses=horizonte_meses,
    )

    async def _obtener():
        return vig

    return _obtener


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


@pytest.mark.asyncio
async def test_motos_devuelve_unidades_y_piso(monkeypatch):
    """Fix round 1: `_proyectar_fn_para` y `resolver_unidades_para_umbral` son ASYNC
    ahora (corren el pipeline completo por candidato) — los fakes también lo son."""
    from app.proyeccion.solver_unidades import UnidadesResultado

    async def fake_proyectar_fn_para(vig, esc, mi, hm):
        async def proyectar_fn(n):
            return n

        return proyectar_fn

    async def fake_resolver(proyectar_fn, ajustes, caja_minima, **kw):
        return UnidadesResultado(
            unidades_extra=12,
            alcanzable=True,
            piso_resultante=Decimal("5000000"),
            meta=Decimal("0"),
        )

    monkeypatch.setattr(escenario, "_proyectar_fn_para", fake_proyectar_fn_para)
    monkeypatch.setattr(escenario, "resolver_unidades_para_umbral", fake_resolver)
    monkeypatch.setattr(
        escenario.params_service,
        "obtener_vigente",
        _fake_vigente(caja_minima=Decimal("0")),
    )
    rs = await escenario.motos_para_evitar_umbral(
        naturaleza="gasto", monto=Decimal("20000000"), mes_inicio="2026-09"
    )
    by = {r.concepto: r for r in rs}
    assert (
        by["unidades_extra"].valor == Decimal("12")
        and by["unidades_extra"].unidad == "unidades"
    )
    assert by["piso_con_unidades"].valor == Decimal("5000000")
    # Integridad de evidencia: mismo ancla de horizonte que impacto_escenario (mes de
    # HOY), no el mes_inicio del escenario hipotético ("2026-09").
    ref_horizonte = _ref_horizonte()
    assert by["unidades_extra"].evidencia.ref == ref_horizonte
    assert by["piso_con_unidades"].evidencia.ref == ref_horizonte
    assert by["unidades_extra"].disponible and by["piso_con_unidades"].disponible


@pytest.mark.asyncio
async def test_motos_no_alcanzable_abstiene_sin_inventar_numero(monkeypatch):
    """El solver puede no encontrar N dentro de su tope (`alcanzable=False`) — la
    abstención debe ganarle a cualquier valor parcial, nunca se inventa un N."""
    from app.proyeccion.solver_unidades import UnidadesResultado

    async def fake_proyectar_fn_para(vig, esc, mi, hm):
        async def proyectar_fn(n):
            return n

        return proyectar_fn

    async def fake_resolver(proyectar_fn, ajustes, caja_minima, **kw):
        return UnidadesResultado(
            unidades_extra=0,
            alcanzable=False,
            piso_resultante=None,
            meta=Decimal("100000000"),
        )

    monkeypatch.setattr(escenario, "_proyectar_fn_para", fake_proyectar_fn_para)
    monkeypatch.setattr(escenario, "resolver_unidades_para_umbral", fake_resolver)
    monkeypatch.setattr(
        escenario.params_service,
        "obtener_vigente",
        _fake_vigente(caja_minima=Decimal("100000000")),
    )
    rs = await escenario.motos_para_evitar_umbral(
        naturaleza="gasto", monto=Decimal("500000000"), mes_inicio="2026-09"
    )
    assert len(rs) == 1
    assert rs[0].concepto == "unidades_extra"
    assert rs[0].disponible is False and rs[0].valor is None
    assert rs[0].evidencia.ref.startswith("no-alcanzable:")


@pytest.mark.asyncio
async def test_motos_abstiene_sin_config(monkeypatch):
    async def sin_config():
        return None

    monkeypatch.setattr(escenario.params_service, "obtener_vigente", sin_config)
    rs = await escenario.motos_para_evitar_umbral(
        naturaleza="gasto", monto=Decimal("20000000"), mes_inicio="2026-09"
    )
    assert len(rs) == 1
    assert rs[0].disponible is False and rs[0].valor is None
    assert rs[0].evidencia.ref == "sin-config"


@pytest.mark.asyncio
async def test_motos_abstiene_sin_modelos_activos(monkeypatch):
    """`_proyectar_fn_para` real levanta ProyeccionError sin modelos activos (mismo
    guard que `proyectar_preview`); el wrapper lo convierte en abstención honesta, no
    en una excepción que reviente al caller."""

    async def sin_modelos(*a, **kw):
        raise escenario.ProyeccionError("no hay modelos de moto activos", 409)

    monkeypatch.setattr(escenario, "_proyectar_fn_para", sin_modelos)
    monkeypatch.setattr(
        escenario.params_service,
        "obtener_vigente",
        _fake_vigente(caja_minima=Decimal("0")),
    )
    rs = await escenario.motos_para_evitar_umbral(
        naturaleza="gasto", monto=Decimal("20000000"), mes_inicio="2026-09"
    )
    assert len(rs) == 1
    assert rs[0].disponible is False and rs[0].valor is None
    assert rs[0].evidencia.ref == "sin-config"


@pytest.mark.asyncio
async def test_motos_reconcilia_con_impacto_escenario_en_n_cero(monkeypatch):
    """Fix round 1 (revisión Opus): el solver de unidades y `impacto_escenario` deben
    dar el MISMO piso para el mismo escenario+params cuando N=0 — ambos corren sobre
    el pipeline completo (paramétrico → E1 → D2), no dos bases distintas. Deja correr
    `aplicar_impactos`/`resolver_unidades_para_umbral` DE VERDAD (no se fakea ninguno
    de los dos) para no tautologizar la aserción — solo se fakea la fuente de datos de
    cada camino (`proy_service.proyectar_impactos` / `_proyectar_fn_para`), y esas dos
    fuentes describen la MISMA proyección base a mano."""
    from app.core.money import money_str
    from app.proyeccion.motor import MesProyeccion, ResultadoProyeccion

    def _mes(mes: str, flujo: Decimal, caja: Decimal) -> MesProyeccion:
        return MesProyeccion(
            mes=mes,
            motos=10,
            cartera=10,
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
            iva=Decimal("0"),
            egresos=Decimal("0"),
            flujo=flujo,
            caja=caja,
            estado="ok",
        )

    # La MISMA base "cruda" de 2 meses que ambos caminos deben ver: sin ajuste, mes0
    # arranca de una caja de 100M (98M - flujo(-2M)) y cae a 95M en mes1.
    base = ResultadoProyeccion(
        meses=[
            _mes("2026-09", Decimal("-2000000"), Decimal("98000000")),
            _mes("2026-10", Decimal("-3000000"), Decimal("95000000")),
        ],
        piso_caja=Decimal("95000000"),
        mes_mas_ajustado="2026-10",
        meses_bajo_minimo=0,
        caja_final=Decimal("95000000"),
        capital_requerido=Decimal("0"),
        runway_meses=None,
    )
    # A mano (reacumular con primer_mes_acumula=True — la convención del servicio,
    # ver test_piso_con_ajustes_acumula_desde_el_primer_mes en
    # tests/proyeccion/test_solver_unidades.py, que fija el mismo número de forma
    # aislada): arranque = 98M - (-2M) = 100M; mes0 = 100M + (-2M-10M) = 88M;
    # mes1 = 88M + (-3M-10M) = 75M; piso = 75M. Este es el número que los DOS caminos
    # deben compartir.
    PISO_CON_ESPERADO = Decimal("75000000")

    async def fake_proyectar_impactos(
        *, ajustes, escenario, mes_inicio, horizonte_meses
    ):
        # Lo que produciría proyectar_impactos DE VERDAD sobre `base` con el mismo
        # ajuste (gasto absoluto $10M desde 2026-09): lo codifico a mano una vez
        # arriba, no lo re-derivo aquí, para no ocultar un error de cálculo detrás de
        # la misma fórmula usada dos veces.
        return {
            "base": {"piso_caja": money_str(base.piso_caja)},
            "ajustada": {
                "piso_caja": money_str(PISO_CON_ESPERADO),
                "meses": [
                    {"mes": "2026-09", "estado": "ok"},
                    {"mes": "2026-10", "estado": "ok"},
                ],
            },
            "delta_por_mes": ["-12000000.00", "-13000000.00"],
        }

    async def fake_proyectar_fn_para(vig, esc, mi, hm):
        async def proyectar_fn(n: int) -> ResultadoProyeccion:
            return base  # n=0 alcanza la meta de inmediato, nunca se llama con n>0

        return proyectar_fn

    monkeypatch.setattr(
        escenario.proy_service, "proyectar_impactos", fake_proyectar_impactos
    )
    monkeypatch.setattr(escenario, "_proyectar_fn_para", fake_proyectar_fn_para)
    monkeypatch.setattr(
        escenario.params_service,
        "obtener_vigente",
        _fake_vigente(caja_minima=Decimal("50000000")),
    )

    kwargs = {
        "naturaleza": "gasto",
        "monto": Decimal("10000000"),
        "mes_inicio": "2026-09",
    }
    impacto = await escenario.impacto_escenario(**kwargs)
    motos = await escenario.motos_para_evitar_umbral(**kwargs)

    piso_con = {r.concepto: r for r in impacto}["piso_con"].valor
    piso_con_unidades = {r.concepto: r for r in motos}["piso_con_unidades"].valor
    assert piso_con == PISO_CON_ESPERADO
    assert piso_con_unidades == PISO_CON_ESPERADO
    # La propiedad que este test existe para fijar: los dos tools reconcilian.
    assert piso_con == piso_con_unidades
