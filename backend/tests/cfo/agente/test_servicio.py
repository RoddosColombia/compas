# backend/tests/cfo/agente/test_servicio.py
from decimal import Decimal

import pytest
from app.cfo.agente import servicio as srv
from app.cfo.agente import tools
from app.cfo.agente.cliente import BloqueTexto, BloqueToolUse, RespuestaLLM
from app.cfo.calc.evidencia import Evidencia, ResultadoCFO
from tests.cfo.agente.fakes import ClienteFake


@pytest.fixture(autouse=True)
def _audit(monkeypatch):
    eventos = []

    async def fake_emit(evento, entidad, entidad_id=None, actor_id=None, metadata=None):
        eventos.append((str(evento), metadata))

    monkeypatch.setattr(srv, "emit_audit", fake_emit)
    return eventos


def _res():
    return ResultadoCFO(
        concepto="caja_hoy",
        valor=Decimal("704722003"),
        unidad="COP",
        disponible=True,
        evidencia=Evidencia(fuente="f", fecha_corte="2026-08-11", ref="2026-08"),
    )


# --- inc4 T9: escenario end-to-end (impacto_escenario + motos_para_evitar_umbral) ---
# Resultados FIJOS de las dos tools de escenario, con la misma forma exacta que
# produce `app.cfo.calc.escenario` (ver tests/cfo/calc/test_escenario.py): piso_con
# lleva el mes de quiebre en `ref` ("quiebre:<mes>"), impacto_mensual/piso_con_unidades
# no (ref=ancla de horizonte, fecha_corte=None) — así `conceptos.formatear` produce el
# texto exacto que se afirma abajo, sin reinventar el formateo en el test.
_PISO_SIN = ResultadoCFO(
    concepto="piso_sin",
    valor=Decimal("100000000"),
    unidad="COP",
    disponible=True,
    evidencia=Evidencia(
        fuente="proyeccion.service.proyectar_impactos", fecha_corte=None, ref="2026-08"
    ),
)
_PISO_CON = ResultadoCFO(
    concepto="piso_con",
    valor=Decimal("40000000"),
    unidad="COP",
    disponible=True,
    evidencia=Evidencia(
        fuente="proyeccion.service.proyectar_impactos",
        fecha_corte=None,
        ref="quiebre:2026-11",
    ),
)
_IMPACTO_MENSUAL = ResultadoCFO(
    concepto="impacto_mensual",
    valor=Decimal("20000000"),
    unidad="COP",
    disponible=True,
    evidencia=Evidencia(fuente="escenario (entrada)", fecha_corte=None, ref="2026-08"),
)
_UNIDADES_EXTRA = ResultadoCFO(
    concepto="unidades_extra",
    valor=Decimal("12"),
    unidad="unidades",
    disponible=True,
    evidencia=Evidencia(
        fuente="proyeccion.solver_unidades.resolver_unidades_para_umbral",
        fecha_corte=None,
        ref="2026-08",
    ),
)
_PISO_CON_UNIDADES = ResultadoCFO(
    concepto="piso_con_unidades",
    valor=Decimal("82000000"),
    unidad="COP",
    disponible=True,
    evidencia=Evidencia(
        fuente="proyeccion.solver_unidades.resolver_unidades_para_umbral",
        fecha_corte=None,
        ref="2026-08",
    ),
)


def _entrada_bodega() -> dict:
    return {
        "naturaleza": "gasto",
        "monto": "20000000",
        "mes_inicio": "2026-09",
    }


async def _fake_tool_escenario(nombre, entrada=None):
    if nombre == "impacto_escenario":
        return [_PISO_SIN, _PISO_CON, _IMPACTO_MENSUAL]
    if nombre == "motos_para_evitar_umbral":
        return [_UNIDADES_EXTRA, _PISO_CON_UNIDADES]
    raise AssertionError(f"tool inesperada en el test: {nombre}")


@pytest.mark.asyncio
async def test_escenario_impacto_y_motos_publica_valores_sustituidos(
    monkeypatch, _audit
):
    """E2E de la garantía anti-alucinación con las dos tools de escenario (inc4): el
    modelo pide impacto_escenario Y motos_para_evitar_umbral EN EL MISMO turno (dos
    BloqueToolUse), cita los 4 conceptos con su token, el verificador los deja pasar
    (ningún crudo, todos los tokens respaldados) y el servicio sustituye — el texto
    publicado trae los VALORES formateados, nunca `[[token]]` crudo."""
    monkeypatch.setattr("app.cfo.agente.loop.ejecutar_tool", _fake_tool_escenario)
    guiones = [
        RespuestaLLM(
            "tool_use",
            [
                BloqueToolUse(
                    id="t1", nombre="impacto_escenario", input=_entrada_bodega()
                ),
                BloqueToolUse(
                    id="t2",
                    nombre="motos_para_evitar_umbral",
                    input=_entrada_bodega(),
                ),
            ],
            10,
            6,
        ),
        RespuestaLLM(
            "end_turn",
            [
                BloqueTexto(
                    texto=(
                        "Si arriendas esa bodega, tu piso de caja queda en "
                        "[[piso_con]], con un impacto mensual de "
                        "[[impacto_mensual]]. Para no cruzar el umbral "
                        "necesitas [[unidades_extra]] más al mes, lo que deja "
                        "el piso en [[piso_con_unidades]]."
                    )
                )
            ],
            8,
            20,
        ),
    ]
    r = await srv.consultar(
        "¿qué pasa si arriendo una bodega de $20M/mes desde septiembre?",
        actor_id="u1",
        cliente=ClienteFake(guiones),
    )
    assert r.abstuvo is False
    assert "[[" not in r.texto  # ningún token crudo se filtró
    assert "$40.000.000 (cruzas el umbral en 2026-11)" in r.texto
    assert "$20.000.000" in r.texto
    assert "12 motos" in r.texto
    assert "$82.000.000" in r.texto
    conceptos = {
        "piso_sin",
        "piso_con",
        "impacto_mensual",
        "unidades_extra",
        "piso_con_unidades",
    }
    assert conceptos.issubset(set(r.conceptos_usados))


@pytest.mark.asyncio
async def test_escenario_conteo_crudo_de_motos_reintenta_y_abstiene(
    monkeypatch, _audit
):
    """Contrato inc4 tarea 3 end-to-end: si el modelo escribe el conteo de motos
    CRUDO ("12 motos") en vez de citar [[unidades_extra]], el verificador lo atrapa
    (_RE_UNIDADES), dispara EL reintento correctivo (D-3: uno solo) y, si el modelo
    reincide en escribir el número crudo, el servicio se abstiene — jamás publica ni
    entra en un loop."""

    async def fake_tool(nombre, entrada=None):
        return [_UNIDADES_EXTRA]

    monkeypatch.setattr("app.cfo.agente.loop.ejecutar_tool", fake_tool)
    guiones = [
        RespuestaLLM(
            "tool_use",
            [
                BloqueToolUse(
                    id="t1",
                    nombre="motos_para_evitar_umbral",
                    input=_entrada_bodega(),
                )
            ],
            5,
            3,
        ),
        RespuestaLLM(
            "end_turn",
            [BloqueTexto(texto="Necesitas vender 12 motos más para evitarlo.")],
            4,
            8,
        ),
        RespuestaLLM(
            "end_turn",
            [BloqueTexto(texto="Perdón, serían 12 motos entonces.")],
            4,
            6,
        ),
    ]
    fake = ClienteFake(guiones)
    r = await srv.consultar(
        "¿cuántas motos más para no cruzar el umbral?", actor_id="u1", cliente=fake
    )
    assert r.abstuvo is True and r.motivo == "verificacion"
    assert fake._guiones == []  # tope D-3: exactamente 1 reintento, jamás loop


# --- inc4 rebanada 2 (Task 5): palancas de crédito end-to-end (simular_palanca) ---
# A diferencia de los e2e de escenario (que monkeypatchean `loop.ejecutar_tool`), aquí
# se deja correr el DISPATCH/tools.py REAL (parseo de `_kwargs_palanca`, enum de
# palanca/modelo, Decimal de nuevo_valor) y solo se fakea la capa de cálculo
# (`app.cfo.calc.palanca.impacto_palanca`) — así el test también cubre el wiring real
# tool→calc que las tareas 2/3 dejaron, no solo el servicio de verificación/sustitución.
_PALANCA_PISO_SIN = ResultadoCFO(
    concepto="piso_sin_palanca",
    valor=Decimal("60000000"),
    unidad="COP",
    disponible=True,
    evidencia=Evidencia(
        fuente="proyeccion.service.impacto_palanca_raw", fecha_corte=None, ref="2026-08"
    ),
)
_PALANCA_PISO_CON = ResultadoCFO(
    concepto="piso_con_palanca",
    valor=Decimal("75000000"),
    unidad="COP",
    disponible=True,
    evidencia=Evidencia(
        fuente="proyeccion.service.impacto_palanca_raw",
        fecha_corte=None,
        ref="quiebre:nunca",
    ),
)
_PALANCA_IMPACTO = ResultadoCFO(
    concepto="impacto_palanca",
    valor=Decimal("15000000"),
    unidad="COP",
    disponible=True,
    evidencia=Evidencia(
        fuente="proyeccion.service.impacto_palanca_raw", fecha_corte=None, ref="2026-08"
    ),
)


def _entrada_palanca() -> dict:
    return {"palanca": "plazo_semanas", "nuevo_valor": "78", "modelo": "todos"}


@pytest.mark.asyncio
async def test_simular_palanca_publica_valores_sustituidos(monkeypatch, _audit):
    """E2E de la garantía anti-alucinación con la tool de palancas (inc4 rebanada 2):
    el modelo pide `simular_palanca`, el DISPATCH/tools.py REAL corre (parsea la
    entrada, llama `palanca.impacto_palanca` por atributo de módulo), la calc está
    fakeada con 3 `ResultadoCFO` conocidos, el modelo cita los 3 tokens
    ([[piso_sin_palanca]]/[[piso_con_palanca]]/[[impacto_palanca]]), el verificador
    los deja pasar (ningún crudo, los 3 tokens con evidencia de este turno) y el
    servicio sustituye — el texto publicado trae los VALORES formateados, nunca
    `[[token]]` crudo. Los nombres llevan sufijo `_palanca` para nunca colisionar
    con `piso_sin`/`piso_con` de escenario (rebanada 1) si ambas tools se piden en
    el mismo turno."""

    async def fake_impacto_palanca(*, palanca, nuevo_valor, modelo="todos"):
        assert palanca == "plazo_semanas"
        assert nuevo_valor == Decimal("78")
        assert modelo == "todos"
        return [_PALANCA_PISO_SIN, _PALANCA_PISO_CON, _PALANCA_IMPACTO]

    monkeypatch.setattr("app.cfo.calc.palanca.impacto_palanca", fake_impacto_palanca)
    guiones = [
        RespuestaLLM(
            "tool_use",
            [
                BloqueToolUse(
                    id="t1", nombre="simular_palanca", input=_entrada_palanca()
                )
            ],
            10,
            6,
        ),
        RespuestaLLM(
            "end_turn",
            [
                BloqueTexto(
                    texto=(
                        "Sin el cambio tu piso queda en [[piso_sin_palanca]]; con "
                        "el plazo a 78 semanas queda en [[piso_con_palanca]], un "
                        "impacto de [[impacto_palanca]]."
                    )
                )
            ],
            8,
            20,
        ),
    ]
    r = await srv.consultar(
        "¿qué pasa si el plazo pasa a 78 semanas en todos los modelos?",
        actor_id="u1",
        cliente=ClienteFake(guiones),
    )
    assert r.abstuvo is False
    assert "[[" not in r.texto  # ningún token crudo se filtró
    assert "$60.000.000" in r.texto
    assert "$75.000.000 (no cruzas el umbral)" in r.texto
    assert "$15.000.000" in r.texto
    assert {"piso_sin_palanca", "piso_con_palanca", "impacto_palanca"}.issubset(
        set(r.conceptos_usados)
    )


@pytest.mark.asyncio
async def test_simular_palanca_cifra_cruda_reintenta_y_abstiene(monkeypatch, _audit):
    """Si el modelo escribe el impacto CRUDO ("$15.000.000") en vez de citar
    [[impacto_palanca]], el verificador lo atrapa, dispara EL reintento correctivo
    (D-3: uno solo) y, si el modelo reincide, el servicio se abstiene con
    `motivo='verificacion'` — jamás publica ni entra en un loop."""

    async def fake_impacto_palanca(*, palanca, nuevo_valor, modelo="todos"):
        return [_PALANCA_PISO_SIN, _PALANCA_PISO_CON, _PALANCA_IMPACTO]

    monkeypatch.setattr("app.cfo.calc.palanca.impacto_palanca", fake_impacto_palanca)
    guiones = [
        RespuestaLLM(
            "tool_use",
            [
                BloqueToolUse(
                    id="t1", nombre="simular_palanca", input=_entrada_palanca()
                )
            ],
            5,
            3,
        ),
        RespuestaLLM(
            "end_turn",
            [BloqueTexto(texto="El impacto sería de $15.000.000 al mes.")],
            4,
            8,
        ),
        RespuestaLLM(
            "end_turn",
            [BloqueTexto(texto="Perdón, serían $15.000.000 entonces.")],
            4,
            6,
        ),
    ]
    fake = ClienteFake(guiones)
    r = await srv.consultar(
        "¿qué pasa si el plazo pasa a 78 semanas en todos los modelos?",
        actor_id="u1",
        cliente=fake,
    )
    assert r.abstuvo is True and r.motivo == "verificacion"
    assert fake._guiones == []  # tope D-3: exactamente 1 reintento, jamás loop


# --- inc4 rebanada 3 sub-3a (Task 3): tendencias reales end-to-end (tendencia_real) --
# Igual que simular_palanca (rebanada 2): se deja correr el DISPATCH/tools.py REAL
# (parseo de metrica) y solo se fakea la capa de cálculo
# (`app.cfo.calc.tendencias.tendencia_real`) — así el test cubre el wiring real
# tool→calc, no solo el servicio de verificación/sustitución.
_TENDENCIA_GASTO_M0 = ResultadoCFO(
    concepto="gasto_real_m0",
    valor=Decimal("45000000"),
    unidad="COP",
    disponible=True,
    evidencia=Evidencia(
        fuente="proyeccion.service.actuals_mensuales", fecha_corte=None, ref="2026-08"
    ),
)
_TENDENCIA_GASTO_M1 = ResultadoCFO(
    concepto="gasto_real_m1",
    valor=Decimal("40000000"),
    unidad="COP",
    disponible=True,
    evidencia=Evidencia(
        fuente="proyeccion.service.actuals_mensuales", fecha_corte=None, ref="2026-07"
    ),
)
_TENDENCIA_GASTO_M2 = ResultadoCFO(
    concepto="gasto_real_m2",
    valor=Decimal("38000000"),
    unidad="COP",
    disponible=True,
    evidencia=Evidencia(
        fuente="proyeccion.service.actuals_mensuales", fecha_corte=None, ref="2026-06"
    ),
)
_TENDENCIA_DELTA_GASTO = ResultadoCFO(
    concepto="delta_gasto_real",
    valor=Decimal("5000000"),
    unidad="COP",
    disponible=True,
    evidencia=Evidencia(
        fuente="proyeccion.service.actuals_mensuales",
        fecha_corte=None,
        ref="direccion:sube",
    ),
)


def _entrada_tendencia() -> dict:
    return {"metrica": "gasto"}


@pytest.mark.asyncio
async def test_tendencia_real_publica_valores_sustituidos(monkeypatch, _audit):
    """E2E de la garantía anti-alucinación con la tool de tendencias (inc4
    rebanada 3, sub-3a): el modelo pide `tendencia_real`, el DISPATCH/tools.py
    REAL corre (parsea metrica, llama `tendencias.tendencia_real` por atributo
    de módulo), la calc está fakeada con 4 `ResultadoCFO` conocidos (m0/m1/m2 +
    delta), el modelo cita los 4 tokens y RELATA la dirección (que viene en el
    `ref` del delta, no la calcula él), el verificador los deja pasar (ningún
    crudo, los 4 tokens con evidencia de este turno) y el servicio sustituye —
    el texto publicado trae los VALORES formateados, nunca `[[token]]` crudo."""

    async def fake_tendencia_real(*, metrica):
        assert metrica == "gasto"
        return [
            _TENDENCIA_GASTO_M0,
            _TENDENCIA_GASTO_M1,
            _TENDENCIA_GASTO_M2,
            _TENDENCIA_DELTA_GASTO,
        ]

    monkeypatch.setattr("app.cfo.calc.tendencias.tendencia_real", fake_tendencia_real)
    guiones = [
        RespuestaLLM(
            "tool_use",
            [
                BloqueToolUse(
                    id="t1", nombre="tendencia_real", input=_entrada_tendencia()
                )
            ],
            10,
            6,
        ),
        RespuestaLLM(
            "end_turn",
            [
                BloqueTexto(
                    texto=(
                        "Tu gasto viene subiendo: este mes [[gasto_real_m0]], el "
                        "mes pasado [[gasto_real_m1]] y hace dos meses "
                        "[[gasto_real_m2]], una variación de [[delta_gasto_real]]."
                    )
                )
            ],
            8,
            20,
        ),
    ]
    r = await srv.consultar(
        "¿cómo viene el gasto vs el mes pasado?",
        actor_id="u1",
        cliente=ClienteFake(guiones),
    )
    assert r.abstuvo is False
    assert "[[" not in r.texto  # ningún token crudo se filtró
    assert "$45.000.000" in r.texto
    assert "$40.000.000" in r.texto
    assert "$38.000.000" in r.texto
    assert "$5.000.000" in r.texto
    assert {
        "gasto_real_m0",
        "gasto_real_m1",
        "gasto_real_m2",
        "delta_gasto_real",
    }.issubset(set(r.conceptos_usados))


@pytest.mark.asyncio
async def test_tendencia_real_cifra_cruda_reintenta_y_abstiene(monkeypatch, _audit):
    """Si el modelo escribe el gasto CRUDO ("$45.000.000") en vez de citar
    [[gasto_real_m0]], el verificador lo atrapa, dispara EL reintento correctivo
    (D-3: uno solo) y, si el modelo reincide, el servicio se abstiene con
    `motivo='verificacion'` — jamás publica ni entra en un loop."""

    async def fake_tendencia_real(*, metrica):
        return [
            _TENDENCIA_GASTO_M0,
            _TENDENCIA_GASTO_M1,
            _TENDENCIA_GASTO_M2,
            _TENDENCIA_DELTA_GASTO,
        ]

    monkeypatch.setattr("app.cfo.calc.tendencias.tendencia_real", fake_tendencia_real)
    guiones = [
        RespuestaLLM(
            "tool_use",
            [
                BloqueToolUse(
                    id="t1", nombre="tendencia_real", input=_entrada_tendencia()
                )
            ],
            5,
            3,
        ),
        RespuestaLLM(
            "end_turn",
            [BloqueTexto(texto="Este mes el gasto fue de $45.000.000.")],
            4,
            8,
        ),
        RespuestaLLM(
            "end_turn",
            [BloqueTexto(texto="Perdón, serían $45.000.000 entonces.")],
            4,
            6,
        ),
    ]
    fake = ClienteFake(guiones)
    r = await srv.consultar(
        "¿cómo viene el gasto vs el mes pasado?", actor_id="u1", cliente=fake
    )
    assert r.abstuvo is True and r.motivo == "verificacion"
    assert fake._guiones == []  # tope D-3: exactamente 1 reintento, jamás loop


@pytest.mark.asyncio
async def test_sin_key_abstiene(monkeypatch, _audit):
    monkeypatch.setattr(srv, "crear_cliente", lambda: None)
    r = await srv.consultar("¿caja?", actor_id="u1")
    assert r.abstuvo is True and r.motivo == "sin_api_key"
    assert [e[0] for e in _audit] == ["cfo.consulta", "cfo.respuesta"]


@pytest.mark.asyncio
async def test_camino_feliz(monkeypatch, _audit):
    async def fake_tool(nombre, entrada=None):
        return [_res()]

    monkeypatch.setattr("app.cfo.agente.loop.ejecutar_tool", fake_tool)
    # inc3 Pieza A: el modelo cita el TOKEN del concepto, nunca escribe la cifra cruda.
    guiones = [
        RespuestaLLM(
            "tool_use",
            [BloqueToolUse(id="t1", nombre="caja_disponible_hoy", input={})],
            5,
            3,
        ),
        RespuestaLLM(
            "end_turn", [BloqueTexto(texto="Tu caja hoy es [[caja_hoy]].")], 4, 8
        ),
    ]
    r = await srv.consultar("¿caja?", actor_id="u1", cliente=ClienteFake(guiones))
    assert r.abstuvo is False
    assert "[[caja_hoy]]" not in r.texto
    assert "$704.722.003 (al 2026-08-11)" in r.texto
    assert r.cifras[0].valor == "704722003"
    assert "caja_hoy" in r.conceptos_usados
    resp_meta = [m for e, m in _audit if e == "cfo.respuesta"][0]
    assert resp_meta["abstuvo"] is False


@pytest.mark.asyncio
async def test_alucinacion_reintento_falla_abstiene(monkeypatch, _audit):
    async def fake_tool(nombre, entrada=None):
        return [_res()]

    monkeypatch.setattr("app.cfo.agente.loop.ejecutar_tool", fake_tool)
    # 1ra conversación: tool + texto con cifra inventada. Reintento: sigue inventando.
    guiones = [
        RespuestaLLM(
            "tool_use",
            [BloqueToolUse(id="t1", nombre="caja_disponible_hoy", input={})],
            1,
            1,
        ),
        RespuestaLLM("end_turn", [BloqueTexto(texto="Tienes $999.999.999.")], 1, 1),
        RespuestaLLM("end_turn", [BloqueTexto(texto="Bueno, $888.888.888.")], 1, 1),
    ]
    fake = ClienteFake(guiones)
    r = await srv.consultar("¿caja?", actor_id="u1", cliente=fake)
    assert r.abstuvo is True and r.motivo == "verificacion"
    assert fake._guiones == []  # tope D-3: exactamente 1 reintento, jamás loop


@pytest.mark.asyncio
async def test_publica_con_tokens_sustituidos(monkeypatch, _audit):
    async def fake_tool(nombre, entrada=None):
        return [_res()]

    monkeypatch.setattr("app.cfo.agente.loop.ejecutar_tool", fake_tool)
    guiones = [
        RespuestaLLM(
            "tool_use",
            [BloqueToolUse(id="t1", nombre="caja_disponible_hoy", input={})],
            1,
            1,
        ),
        RespuestaLLM(
            "end_turn", [BloqueTexto(texto="Tu caja hoy es [[caja_hoy]].")], 1, 1
        ),
    ]
    r = await srv.consultar("¿caja?", actor_id="u1", cliente=ClienteFake(guiones))
    assert r.abstuvo is False
    assert "[[caja_hoy]]" not in r.texto
    assert "$704.722.003 (al 2026-08-11)" in r.texto


@pytest.mark.asyncio
async def test_reincidencia_en_cifra_cruda_abstiene_un_solo_reintento(
    monkeypatch, _audit
):
    async def fake_tool(nombre, entrada=None):
        return [_res()]

    monkeypatch.setattr("app.cfo.agente.loop.ejecutar_tool", fake_tool)
    # 1ª: tool + cifra cruda (aunque numéricamente correcta); reintento: vuelve a
    # escribir cruda en vez de citar el token → abstención, jamás loop (D-3).
    guiones = [
        RespuestaLLM(
            "tool_use",
            [BloqueToolUse(id="t1", nombre="caja_disponible_hoy", input={})],
            1,
            1,
        ),
        RespuestaLLM("end_turn", [BloqueTexto(texto="Tu caja es $704.722.003.")], 1, 1),
        RespuestaLLM("end_turn", [BloqueTexto(texto="Perdón: $704.722.003.")], 1, 1),
    ]
    fake = ClienteFake(guiones)
    r = await srv.consultar("¿caja?", actor_id="u1", cliente=fake)
    assert r.abstuvo is True and r.motivo == "verificacion"
    # consumió exactamente 3 respuestas (1ª: tool+texto; reintento: 1 texto), no más
    assert fake._guiones == []


@pytest.mark.asyncio
async def test_error_interno_no_revienta_y_audita(monkeypatch, _audit):
    # crear_cliente revienta (fallo no-LLM) -> abstención graciosa, no excepción
    def boom():
        raise RuntimeError("boom")

    monkeypatch.setattr(srv, "crear_cliente", boom)
    r = await srv.consultar("¿caja?", actor_id="u1")  # NO debe levantar
    assert r.abstuvo is True and r.motivo == "error"
    assert [e[0] for e in _audit] == ["cfo.consulta", "cfo.respuesta"]


@pytest.mark.asyncio
async def test_consultar_usa_historial_y_expone_texto_crudo(monkeypatch, _audit):
    async def fake_tool(nombre, entrada=None):
        return [_res()]  # ResultadoCFO caja_hoy disponible

    monkeypatch.setattr("app.cfo.agente.loop.ejecutar_tool", fake_tool)
    guiones = [
        RespuestaLLM(
            "tool_use",
            [BloqueToolUse(id="t1", nombre="caja_disponible_hoy", input={})],
            1,
            1,
        ),
        RespuestaLLM("end_turn", [BloqueTexto(texto="Tu caja es [[caja_hoy]].")], 1, 1),
    ]
    fake = ClienteFake(guiones)
    historial = [
        {"role": "user", "content": "hola"},
        {"role": "assistant", "content": "¿en qué te ayudo?"},
    ]
    r = await srv.consultar("¿caja?", actor_id="u1", cliente=fake, historial=historial)
    # el historial se antepuso (el primer mensaje que vio el cliente lo incluye)
    assert fake.llamadas[0]["messages"][0]["content"] == "hola"
    # texto publicado = sustituido; texto_crudo = con token (para guardar en el hilo)
    assert "[[caja_hoy]]" not in r.texto and "$704.722.003" in r.texto
    assert r.texto_crudo == "Tu caja es [[caja_hoy]]."


# --- inc4 rebanada 3 sub-3b (Task 5): rumbo_caja end-to-end -------------------
# rumbo_caja es una tool de CERO args cableada DIRECTO en DISPATCH a
# tendencias.rumbo_caja (sin wrapper) — a diferencia de tendencia_real (que
# accede al módulo calc por atributo en cada llamada, así que monkeypatchear
# `app.cfo.calc.tendencias.tendencia_real` sí lo intercepta), DISPATCH ya
# capturó la referencia de función al importar tools.py, así que aquí se usa
# `monkeypatch.setitem(tools.DISPATCH, ...)` — mismo patrón que
# test_camino_feliz usa a nivel loop para las otras tools de cero args.
_RUMBO_CAJA_ULT = ResultadoCFO(
    concepto="caja_real_ult",
    valor=Decimal("704722003"),
    unidad="COP",
    disponible=True,
    evidencia=Evidencia(
        fuente="proyeccion.service.comparar_vigente+proyectar_vigente",
        fecha_corte=None,
        ref="2026-08",
    ),
)
_RUMBO_CAJA_PREVIO = ResultadoCFO(
    concepto="caja_real_previo",
    valor=Decimal("650000000"),
    unidad="COP",
    disponible=True,
    evidencia=Evidencia(
        fuente="proyeccion.service.comparar_vigente+proyectar_vigente",
        fecha_corte=None,
        ref="2026-07",
    ),
)
_RUMBO_DELTA = ResultadoCFO(
    concepto="delta_caja_rumbo",
    valor=Decimal("54722003"),
    unidad="COP",
    disponible=True,
    evidencia=Evidencia(
        fuente="proyeccion.service.comparar_vigente+proyectar_vigente",
        fecha_corte=None,
        ref="direccion:sube",
    ),
)
_RUMBO_PISO = ResultadoCFO(
    concepto="piso_proyectado",
    valor=Decimal("40000000"),
    unidad="COP",
    disponible=True,
    evidencia=Evidencia(
        fuente="proyeccion.service.comparar_vigente+proyectar_vigente",
        fecha_corte=None,
        ref="quiebre:2026-11",
    ),
)


@pytest.mark.asyncio
async def test_rumbo_caja_publica_valores_sustituidos(monkeypatch, _audit):
    """E2E de la garantía anti-alucinación con la tool rumbo_caja (inc4 rebanada
    3, sub-3b): el modelo pide `rumbo_caja` (sin parámetros), el DISPATCH/
    tools.py REAL corre, la calc está fakeada con 4 `ResultadoCFO` conocidos, el
    modelo cita los 4 tokens y RELATA la dirección (que viene en el `ref` del
    delta, no la calcula él), el verificador los deja pasar y el servicio
    sustituye — el texto publicado trae los VALORES formateados, nunca
    `[[token]]` crudo."""

    async def fake_rumbo_caja():
        return [_RUMBO_CAJA_ULT, _RUMBO_CAJA_PREVIO, _RUMBO_DELTA, _RUMBO_PISO]

    monkeypatch.setitem(tools.DISPATCH, "rumbo_caja", fake_rumbo_caja)
    guiones = [
        RespuestaLLM(
            "tool_use",
            [BloqueToolUse(id="t1", nombre="rumbo_caja", input={})],
            10,
            6,
        ),
        RespuestaLLM(
            "end_turn",
            [
                BloqueTexto(
                    texto=(
                        "Tu caja viene subiendo: hoy tienes [[caja_real_ult]], "
                        "el mes pasado tenías [[caja_real_previo]], una "
                        "variación de [[delta_caja_rumbo]]. La proyección "
                        "apunta a un piso de [[piso_proyectado]]."
                    )
                )
            ],
            8,
            20,
        ),
    ]
    r = await srv.consultar(
        "¿voy en rumbo?", actor_id="u1", cliente=ClienteFake(guiones)
    )
    assert r.abstuvo is False
    assert "[[" not in r.texto  # ningún token crudo se filtró
    assert "$704.722.003" in r.texto
    assert "$650.000.000" in r.texto
    assert "$54.722.003" in r.texto
    assert "$40.000.000" in r.texto
    assert {
        "caja_real_ult",
        "caja_real_previo",
        "delta_caja_rumbo",
        "piso_proyectado",
    }.issubset(set(r.conceptos_usados))


@pytest.mark.asyncio
async def test_rumbo_caja_cifra_cruda_reintenta_y_abstiene(monkeypatch, _audit):
    """Si el modelo escribe la caja CRUDA ("$704.722.003") en vez de citar
    [[caja_real_ult]], el verificador lo atrapa, dispara EL reintento
    correctivo (D-3: uno solo) y, si el modelo reincide, el servicio se
    abstiene con `motivo='verificacion'` — jamás publica ni entra en un loop."""

    async def fake_rumbo_caja():
        return [_RUMBO_CAJA_ULT, _RUMBO_CAJA_PREVIO, _RUMBO_DELTA, _RUMBO_PISO]

    monkeypatch.setitem(tools.DISPATCH, "rumbo_caja", fake_rumbo_caja)
    guiones = [
        RespuestaLLM(
            "tool_use",
            [BloqueToolUse(id="t1", nombre="rumbo_caja", input={})],
            5,
            3,
        ),
        RespuestaLLM(
            "end_turn",
            [BloqueTexto(texto="Hoy tu caja es de $704.722.003.")],
            4,
            8,
        ),
        RespuestaLLM(
            "end_turn",
            [BloqueTexto(texto="Perdón, serían $704.722.003 entonces.")],
            4,
            6,
        ),
    ]
    fake = ClienteFake(guiones)
    r = await srv.consultar("¿voy en rumbo?", actor_id="u1", cliente=fake)
    assert r.abstuvo is True and r.motivo == "verificacion"
    assert fake._guiones == []  # tope D-3: exactamente 1 reintento, jamás loop
