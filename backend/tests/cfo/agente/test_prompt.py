from app.cfo.agente.prompt import CORRECTIVO, SYSTEM_PROMPT


def test_system_prompt_fija_invariantes():
    p = SYSTEM_PROMPT.lower()
    assert "nunca calcul" in p          # el modelo no calcula
    assert "herramienta" in p or "tool" in p
    assert "abst" in p                   # abstenerse
    assert "evidencia" in p or "fecha de corte" in p


def test_correctivo_es_formateable():
    out = CORRECTIVO.format(cifras="$999", valores="caja=$704.722.003")
    assert "$999" in out and "704.722.003" in out
