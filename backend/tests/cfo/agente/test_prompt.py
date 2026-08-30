from app.cfo.agente.prompt import CORRECTIVO, SYSTEM_PROMPT


def test_system_prompt_fija_invariantes():
    p = SYSTEM_PROMPT.lower()
    assert "nunca calcul" in p  # el modelo no calcula
    assert "herramienta" in p or "tool" in p
    assert "abst" in p  # abstenerse
    assert "evidencia" in p or "fecha de corte" in p


def test_correctivo_es_formateable():
    out = CORRECTIVO.format(
        cifras="$999",
        tokens="[[ventas_totales]]",
        disponibles="[[caja_hoy]]; [[runway]]",
    )
    assert "$999" in out
    assert "[[ventas_totales]]" in out
    assert "[[caja_hoy]]; [[runway]]" in out


def test_system_prompt_prohibe_porcentajes_calculados():
    # COMPAS no tiene concepto de "porcentaje": el modelo no debe calcular ni dar
    # porcentajes/ratios propios (regla #1, FIX 1 FINAL-REVIEW inc2).
    assert "%" in SYSTEM_PROMPT or "porcentaje" in SYSTEM_PROMPT.lower()


def test_prompt_exige_tokens_de_concepto():
    p = SYSTEM_PROMPT
    assert "[[caja_hoy]]" in p and "[[runway]]" in p and "[[iva_cuatrimestre]]" in p
    assert "nunca escrib" in p.lower() or "no escrib" in p.lower()  # no escribe numeros


def test_correctivo_formateable_con_tokens():
    out = CORRECTIVO.format(
        cifras="$999", tokens="[[ventas]]", disponibles="[[caja_hoy]]"
    )
    assert "$999" in out and "[[ventas]]" in out and "[[caja_hoy]]" in out


def test_prompt_advierte_no_espacios_en_el_token():
    # Historia: A3 dejaba un hueco (deferred) donde "[[ caja_hoy ]]" con espacios
    # pasaba los regex del verificador sin violar la regla anti-alucinacion, pero
    # el token quedaba sin sustituir y se filtraba crudo al usuario. Ese hueco ya
    # esta CERRADO: RE_TOKEN (hardening FINAL-REVIEW, compartido entre verificador
    # y sustitucion) tolera espacios internos y hoy SI sustituye el token espaciado
    # (ver test_sustituir_token_con_espacios_se_resuelve en test_conceptos.py). Esta
    # instruccion en el prompt es una segunda capa defensiva (pedirle al modelo que
    # no agregue espacios), no la unica barrera contra el token espaciado.
    assert "espacio" in SYSTEM_PROMPT.lower()


def test_prompt_menciona_las_tools_de_escenario():
    # inc4: el modelo debe saber que impacto_escenario y motos_para_evitar_umbral
    # existen y que responden preguntas "¿qué pasaría si...?" / "¿cuántas motos
    # más...?" -- si el prompt no las nombra, el modelo nunca las invoca.
    p = SYSTEM_PROMPT.lower()
    assert "impacto_escenario" in p
    assert "motos_para_evitar_umbral" in p


def test_prompt_exige_citar_los_tokens_de_escenario():
    # Cada tool de escenario devuelve VARIOS conceptos nombrados; el modelo debe
    # citar cada uno con su propio token, nunca resumir el resultado con un
    # numero propio.
    p = SYSTEM_PROMPT
    for token in (
        "[[impacto_mensual]]",
        "[[piso_sin]]",
        "[[piso_con]]",
        "[[unidades_extra]]",
        "[[piso_con_unidades]]",
    ):
        assert token in p


def test_prompt_prohibe_escribir_conteo_de_motos_crudo():
    # Historia: "unidades_extra" son motos/mes -- un conteo entero pequenio
    # ("12 motos") es tan prohibido como un monto o un mes; el prompt debe
    # extender la regla #1 explicitamente a cantidades/conteos, no solo a
    # montos y porcentajes, y nombrar el token que reemplaza el conteo.
    p = SYSTEM_PROMPT.lower()
    assert "cantidad" in p or "conteo" in p or "moto" in p
    assert "[[unidades_extra]]" in SYSTEM_PROMPT


def test_prompt_menciona_simular_palanca():
    # inc4 rebanada 2: el modelo debe saber que simular_palanca existe para
    # "¿qué pasa si cambio el plazo/cuota inicial/cuota semanal?" -- si el
    # prompt no la nombra, el modelo nunca la invoca.
    p = SYSTEM_PROMPT.lower()
    assert "simular_palanca" in p
    assert "plazo" in p and "cuota inicial" in p and "cuota semanal" in p


def test_prompt_exige_citar_los_tokens_de_palanca():
    # simular_palanca devuelve TRES conceptos nombrados; el modelo debe citar
    # cada uno con su propio token, nunca resumir el resultado con una resta
    # propia (esa resta ya la hace la herramienta, cargada en [[impacto]]).
    p = SYSTEM_PROMPT
    for token in ("[[piso_sin]]", "[[piso_con]]", "[[impacto]]"):
        assert token in p
    # reforzamos la regla 1/2: no resumir los tres tokens en una resta propia
    assert "esa resta" in p.lower()
