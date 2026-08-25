from datetime import date
from decimal import Decimal

from app.cfo.agente.conceptos import CONCEPTOS_CITABLES, formatear, sustituir_tokens
from app.cfo.calc.evidencia import Evidencia, ResultadoCFO


def _r(concepto, valor, unidad, fecha):
    return ResultadoCFO(
        concepto=concepto,
        valor=valor,
        unidad=unidad,
        disponible=True,
        evidencia=Evidencia(fuente="f", fecha_corte=fecha, ref="x"),
    )


def _r2(concepto, valor, unidad, ref=""):
    # variante de _r para unidades/quiebre: sin fecha_corte, con ref libre.
    # nombre distinto de _r a propósito — _r es posicional (concepto, valor,
    # unidad, fecha) y lo usan los tests existentes arriba; reusar el nombre
    # con otra firma los rompería en silencio (Python resuelve el global al
    # llamar, no al definir, así que la última def gana para TODOS los tests).
    return ResultadoCFO(
        concepto=concepto,
        valor=Decimal(str(valor)),
        unidad=unidad,
        disponible=True,
        evidencia=Evidencia(fuente="x", fecha_corte=None, ref=ref),
    )


def test_citables():
    assert CONCEPTOS_CITABLES == frozenset({"caja_hoy", "runway", "iva_cuatrimestre"})


def test_formatear_caja_money_es_co_con_fecha():
    r = _r("caja_hoy", Decimal("704722003.00"), "COP", "2026-08-11")
    assert formatear(r) == "$704.722.003 (al 2026-08-11)"


def test_formatear_runway_meses_coma():
    r = _r("runway", Decimal("4.20"), "meses", None)
    assert formatear(r) == "4,2 meses"


def test_formatear_iva_vencimiento_y_dias():
    r = _r("iva_cuatrimestre", Decimal("36204698.10"), "COP", "2026-09-10")
    # hoy fijo para que 'en N días' sea determinista
    assert formatear(r, hoy=date(2026, 8, 17)) == (
        "$36.204.698 (vence el 2026-09-10, en 24 días)"
    )


def test_formatear_iva_usa_today_bogota_cuando_hoy_es_none(monkeypatch):
    import app.cfo.agente.conceptos as c

    monkeypatch.setattr(c, "today_bogota", lambda: date(2026, 8, 17))
    r = _r("iva_cuatrimestre", Decimal("36204698.10"), "COP", "2026-09-10")
    assert formatear(r) == "$36.204.698 (vence el 2026-09-10, en 24 días)"


def test_sustituir_multiple():
    caja = _r("caja_hoy", Decimal("704722003.00"), "COP", "2026-08-11")
    iva = _r("iva_cuatrimestre", Decimal("36204698.10"), "COP", "2026-09-10")
    texto = "Tu caja es [[caja_hoy]] y el IVA es [[iva_cuatrimestre]]."
    out = sustituir_tokens(texto, [caja, iva], hoy=date(2026, 8, 17))
    assert out == (
        "Tu caja es $704.722.003 (al 2026-08-11) y el IVA es "
        "$36.204.698 (vence el 2026-09-10, en 24 días)."
    )


def test_sustituir_token_desconocido_se_deja_igual():
    # defensivo: verificar ya garantiza validez; un token sin resultado se deja tal cual
    assert sustituir_tokens("x [[ventas]] y", []) == "x [[ventas]] y"


def test_sustituir_token_con_espacios_se_resuelve():
    # RE_TOKEN (hardening FINAL-REVIEW) es tolerante a espacios internos: un token
    # como "[[ caja_hoy ]]" debe sustituirse igual que "[[caja_hoy]]" — antes del
    # fix ninguna de las dos regex (verificador/conceptos, antes duplicadas) lo
    # reconocía, así que el placeholder crudo se filtraba tal cual al usuario.
    caja = _r("caja_hoy", Decimal("704722003.00"), "COP", "2026-08-11")
    out = sustituir_tokens("Caja: [[ caja_hoy ]].", [caja], hoy=date(2026, 8, 17))
    assert out == "Caja: $704.722.003 (al 2026-08-11)."
    assert "[[" not in out


def test_formatea_unidades_como_motos():
    assert formatear(_r2("unidades_extra", 12, "unidades")) == "12 motos"


def test_piso_con_contexto_de_quiebre():
    # una cifra COP cuyo ref codifica el mes de quiebre
    out = formatear(_r2("piso_con", 40000000, "COP", ref="quiebre:2026-11"))
    assert "$40.000.000" in out and "cruzas el umbral en 2026-11" in out


def test_piso_sin_quiebre():
    out = formatear(_r2("piso_con", 40000000, "COP", ref="quiebre:nunca"))
    assert "$40.000.000" in out and "no cruzas el umbral" in out
