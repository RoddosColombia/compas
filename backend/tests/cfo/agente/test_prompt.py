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
