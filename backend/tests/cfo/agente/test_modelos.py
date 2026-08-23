import pytest
from app.cfo.agente.modelos import CifraPublicada, RespuestaCFO, UsoLLM
from app.cfo.calc.evidencia import Evidencia
from pydantic import ValidationError


def _uso():
    return UsoLLM(
        modelo="claude-haiku-4-5-20251001", tokens_in=10, tokens_out=20, iteraciones=1
    )


def test_respuesta_cfo_valida():
    ev = Evidencia(
        fuente="caja.service.caja_diaria", fecha_corte="2026-08-11", ref="2026-08"
    )
    r = RespuestaCFO(
        texto="La caja hoy es $704.722.003.",
        abstuvo=False,
        texto_crudo="La caja hoy es [[caja_hoy]].",
        conceptos_usados=["caja_hoy"],
        cifras=[CifraPublicada(valor="704722003", unidad="COP", evidencia=ev)],
        uso=_uso(),
    )
    assert r.abstuvo is False
    assert r.cifras[0].valor == "704722003"


def test_respuesta_cfo_rechaza_campo_extra():
    with pytest.raises(ValidationError):
        RespuestaCFO(texto="x", abstuvo=True, texto_crudo="x", uso=_uso(), foo=1)


def test_respuesta_cfo_exige_texto_crudo():
    # N-2 (nit Kimi): texto_crudo es REQUERIDO — sin default a None. Cierra el
    # camino teórico de fuga donde un fallback `texto_crudo or texto` en un
    # caller habría colapsado al texto YA SUSTITUIDO si texto_crudo faltara.
    with pytest.raises(ValidationError):
        RespuestaCFO(texto="x", abstuvo=True, uso=_uso())
