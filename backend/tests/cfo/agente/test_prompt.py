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
    # simular_palanca devuelve TRES conceptos nombrados (namespaced con sufijo
    # `_palanca` para no colisionar con los de escenario); el modelo debe citar
    # cada uno con su propio token, nunca resumir el resultado con una resta
    # propia (esa resta ya la hace la herramienta, cargada en [[impacto_palanca]]).
    p = SYSTEM_PROMPT
    tokens = ("[[piso_sin_palanca]]", "[[piso_con_palanca]]", "[[impacto_palanca]]")
    for token in tokens:
        assert token in p
    # reforzamos la regla 1/2: no resumir los tres tokens en una resta propia
    assert "esa resta" in p.lower()


def test_prompt_salvedad_de_plazo_largo_plazo():
    # fast-follow 2026-08-29: para la palanca de PLAZO, cuando el impacto es 0 dentro
    # del horizonte corto, FABS no debe reportar "$0" a secas -- debe explicar que el
    # efecto del plazo es de largo plazo. El prompt le enseña a leer la marca del ref.
    p = SYSTEM_PROMPT
    assert "plazo-sin-efecto-horizonte" in p
    assert "largo plazo" in p.lower()


def test_prompt_menciona_tendencia_real():
    # inc4 rebanada 3 (sub-3a): el modelo debe saber que tendencia_real existe
    # para "¿cómo viene el ingreso/gasto/caja vs el mes pasado?" -- si el prompt
    # no la nombra, el modelo nunca la invoca.
    p = SYSTEM_PROMPT.lower()
    assert "tendencia_real" in p


def test_prompt_tendencia_relata_direccion_desde_ref_no_la_calcula():
    # La dirección (sube/baja/estable) viene calculada por COMPAS en el `ref`
    # del concepto delta_..._real -- el prompt debe decirle al modelo que la
    # RELATE, nunca que la infiera comparando los meses a ojo.
    p = SYSTEM_PROMPT.lower()
    assert "direcci" in p  # "dirección"/"direccion"
    assert "ref" in p


def test_prompt_tendencia_reitera_no_porcentajes():
    # Reitera cerca del bloque de tendencia_real la prohibición de la regla 7
    # (ningún % calculado por el modelo), no solo en el bloque original.
    p = SYSTEM_PROMPT.lower()
    idx = p.find("tendencia_real")
    assert idx != -1
    bloque = p[idx:]
    assert "%" in bloque or "porcentaje" in bloque


def test_prompt_menciona_rumbo_caja():
    # inc4 rebanada 3 (sub-3b): el modelo debe saber que rumbo_caja existe para
    # "¿voy en rumbo?/¿hacia dónde va la caja?" -- si el prompt no la nombra, el
    # modelo nunca la invoca (tool sin parámetros, igual que caja_disponible_hoy).
    p = SYSTEM_PROMPT.lower()
    assert "rumbo_caja" in p
    assert "rumbo" in p or "umbral" in p


def test_prompt_exige_citar_los_tokens_de_rumbo_caja():
    # rumbo_caja devuelve CUATRO conceptos nombrados en la misma llamada; el
    # modelo debe citar cada uno con su propio token, nunca resumir en una cifra
    # propia.
    p = SYSTEM_PROMPT
    for token in (
        "[[caja_real_ult]]",
        "[[caja_real_previo]]",
        "[[piso_proyectado]]",
        "[[delta_caja_rumbo]]",
    ):
        assert token in p


def test_prompt_rumbo_relata_direccion_desde_ref_no_la_calcula():
    # La dirección (sube/baja/estable) del delta_caja_rumbo ya viene calculada
    # por COMPAS en su evidencia `ref` -- el prompt debe decirle al modelo que la
    # RELATE, nunca que la infiera comparando las cifras a ojo (mismo contrato
    # que tendencia_real).
    p = SYSTEM_PROMPT.lower()
    idx = p.find("rumbo_caja")
    assert idx != -1
    bloque = p[idx:]
    assert "direcci" in bloque  # "dirección"/"direccion"
    assert "ref" in bloque


def test_prompt_rumbo_reitera_no_porcentajes():
    # Reitera cerca del bloque de rumbo_caja la prohibición de la regla 7 (ningún
    # % calculado por el modelo), no solo en el bloque original.
    p = SYSTEM_PROMPT.lower()
    idx = p.find("rumbo_caja")
    assert idx != -1
    bloque = p[idx:]
    assert "%" in bloque or "porcentaje" in bloque


def test_prompt_menciona_real_vs_presupuesto():
    # inc4 rebanada 3 (sub-3c): el modelo debe saber que real_vs_presupuesto
    # existe para "¿gasté más/menos de lo presupuestado?" -- si el prompt no la
    # nombra, el modelo nunca la invoca (tool con parámetro `mes` OPCIONAL).
    p = SYSTEM_PROMPT.lower()
    assert "real_vs_presupuesto" in p
    assert "presupuesto" in p


def test_prompt_exige_citar_los_tokens_de_presupuesto():
    # real_vs_presupuesto devuelve TRES conceptos nombrados en la misma
    # llamada; el modelo debe citar cada uno con su propio token, nunca
    # resumir en una cifra propia.
    p = SYSTEM_PROMPT
    for token in (
        "[[gasto_real_mes]]",
        "[[presupuesto_mes]]",
        "[[desvio_presupuesto]]",
    ):
        assert token in p


def test_prompt_presupuesto_relata_direccion_desde_ref_no_la_calcula():
    # La dirección (sobre/bajo/en-línea) del desvío ya viene calculada por
    # COMPAS en la evidencia `ref` del concepto desvio_presupuesto -- el
    # prompt debe decirle al modelo que la RELATE, nunca que la calcule ni la
    # infiera comparando las cifras a ojo (mismo contrato que tendencia_real/
    # rumbo_caja).
    p = SYSTEM_PROMPT.lower()
    idx = p.find("real_vs_presupuesto")
    assert idx != -1
    bloque = p[idx:]
    assert "direcci" in bloque  # "dirección"/"direccion"
    assert "ref" in bloque
    assert "sobre" in bloque and "bajo" in bloque


def test_prompt_presupuesto_reitera_no_porcentajes():
    # Reitera cerca del bloque de real_vs_presupuesto la prohibición de la
    # regla 7 (ningún % calculado por el modelo), no solo en el bloque
    # original.
    p = SYSTEM_PROMPT.lower()
    idx = p.find("real_vs_presupuesto")
    assert idx != -1
    bloque = p[idx:]
    assert "%" in bloque or "porcentaje" in bloque
