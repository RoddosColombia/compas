"""Nits cosméticos inc4 (fast-follow):
1. el prompt evita el doble sustantivo tras [[unidades_extra]] ("0 motos motos");
2. _cifras colapsa duplicados EXACTOS (re-llamadas redundantes del modelo) sin
   perder valores distintos (dos escenarios en un turno)."""

from decimal import Decimal

from app.cfo.agente.prompt import SYSTEM_PROMPT
from app.cfo.agente.servicio import _cifras
from app.cfo.calc.evidencia import Evidencia, ResultadoCFO


def _r(concepto, valor, unidad="COP", ref="r", disponible=True):
    return ResultadoCFO(
        concepto=concepto,
        valor=Decimal(str(valor)) if valor is not None else None,
        unidad=unidad,
        disponible=disponible,
        evidencia=Evidencia(fuente="f", fecha_corte=None, ref=ref),
    )


def test_prompt_evita_doble_motos_tras_token():
    assert "unidades_extra" in SYSTEM_PROMPT
    # el prompt aclara que el token ya incluye "motos" y que no se repita
    assert "ya se sustituye por el texto completo" in SYSTEM_PROMPT
    assert "motos motos" in SYSTEM_PROMPT


def test_cifras_colapsa_duplicados_exactos():
    r = _r("piso_con", 71199133, "COP", ref="quiebre:nunca")
    assert len(_cifras([r, r, r])) == 1


def test_cifras_conserva_valores_distintos_misma_unidad():
    a = _r("piso_con", 40000000, "COP", ref="quiebre:2026-11")
    b = _r("piso_con", 71199133, "COP", ref="quiebre:nunca")
    out = _cifras([a, b])
    assert len(out) == 2
    assert [c.valor for c in out] == ["40000000", "71199133"]  # orden preservado


def test_cifras_dedup_respeta_evidencia_distinta():
    # mismo valor+unidad pero evidencia distinta => NO son el mismo dato => ambos
    a = _r("piso_con", 100, "COP", ref="A")
    b = _r("piso_con", 100, "COP", ref="B")
    assert len(_cifras([a, b])) == 2


def test_cifras_ignora_no_disponibles_y_sin_valor():
    ok = _r("piso_con", 100, "COP")
    no = _r("x", None, "COP", disponible=False)
    assert len(_cifras([ok, no])) == 1
