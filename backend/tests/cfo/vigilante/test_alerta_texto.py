from decimal import Decimal

from app.cfo.calc.evidencia import Evidencia, ResultadoCFO
from app.cfo.vigilante.alerta_texto import construir_texto
from app.cfo.vigilante.disparadores import Disparo, ResultadoAlerta


def _piso(mes):
    return ResultadoCFO(
        concepto="alerta_piso",
        valor=Decimal("2500"),
        unidad="COP",
        disponible=True,
        evidencia=Evidencia(fuente="f", fecha_corte=None, ref=f"quiebre:{mes}"),
    )


def _umbral(concepto, val, ref):
    return ResultadoCFO(
        concepto=concepto,
        valor=Decimal(val),
        unidad="COP",
        disponible=True,
        evidencia=Evidencia(fuente="f", fecha_corte=None, ref=ref),
    )


def test_proyectado_ambar_sustituye_y_menciona_mes():
    res = ResultadoAlerta(
        disparos=[Disparo("proyectado", "ambar")],
        resultados=[
            _piso("2026-10"),
            _umbral("alerta_umbral_atencion", "3000", "umbral:atencion"),
        ],
    )
    crudo, texto = construir_texto(res)
    assert "[[alerta_piso]]" in crudo  # el crudo lleva tokens
    assert "[[" not in texto  # el sustituido no
    assert "cruzas el umbral en 2026-10" in texto
    assert "$3.000" in texto


def test_real_rojo_sustituye_disponible_y_critico():
    res = ResultadoAlerta(
        disparos=[Disparo("real", "rojo")],
        resultados=[
            ResultadoCFO(
                concepto="alerta_disponible_hoy",
                valor=Decimal("500"),
                unidad="COP",
                disponible=True,
                evidencia=Evidencia(
                    fuente="f", fecha_corte="2026-08-30", ref="disponible:hoy"
                ),
            ),
            _umbral("alerta_umbral_critico", "1000", "umbral:critico"),
        ],
    )
    crudo, texto = construir_texto(res)
    assert "$500 (al 2026-08-30)" in texto
    assert "$1.000" in texto
    assert "[[" not in texto
