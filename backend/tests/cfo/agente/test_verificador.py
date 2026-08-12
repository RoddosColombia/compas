# backend/tests/cfo/agente/test_verificador.py
"""FABS · batería adversarial del verificador cifra→evidencia (control crítico).

Cada caso ataca un modo de falla real de LLMs con cifras (monto inventado, suma
inventada, $0 falso, meses fuera de tolerancia, evidencia abstenida) o un falso
positivo que NO debe disparar el veredicto (años, fechas, tolerancia de redondeo)."""

from decimal import Decimal

from app.cfo.agente.verificador import extraer_cifras, verificar
from app.cfo.calc.evidencia import Evidencia, ResultadoCFO


def _cop(valor):
    return ResultadoCFO(
        concepto="caja_hoy",
        valor=valor,
        unidad="COP",
        disponible=True,
        evidencia=Evidencia(fuente="f", fecha_corte="2026-08-11", ref="2026-08"),
    )


def _meses(valor):
    return ResultadoCFO(
        concepto="runway",
        valor=valor,
        unidad="meses",
        disponible=True,
        evidencia=Evidencia(fuente="f", fecha_corte=None, ref="2026-08"),
    )


def test_extrae_montos_y_meses_ignora_anios_y_fechas():
    texto = (
        "En 2026, al 10 de septiembre, la caja es $704.722.003 y el runway "
        "es de 4,2 meses. Período C2."
    )
    cifras = {(v, u) for v, u, _ in extraer_cifras(texto)}
    assert (Decimal("704722003"), "COP") in cifras
    assert (Decimal("4.2"), "meses") in cifras
    # 2026 (año), 10 (día), C2 (etiqueta) NO son cifras monetarias/unitarias
    assert all(not (v == Decimal("2026")) for v, _, _ in extraer_cifras(texto))


def test_ok_cuando_toda_cifra_tiene_evidencia():
    texto = "La caja hoy es $704.722.003 (al 2026-08-11)."
    v = verificar(texto, [_cop(Decimal("704722003"))])
    assert v.ok is True
    assert v.cifras_sin_evidencia == []


def test_atrapa_monto_inventado():
    texto = "La caja hoy es $704.722.003, pero podrías tener hasta $50.000.000 extra."
    v = verificar(texto, [_cop(Decimal("704722003"))])
    assert v.ok is False
    assert any("50.000.000" in t for t in v.cifras_sin_evidencia)


def test_atrapa_suma_inventada():
    # el modelo sumó dos evidencias — resultado sin respaldo directo
    texto = "En total son $740.926.701."
    v = verificar(texto, [_cop(Decimal("704722003")), _cop(Decimal("36204698"))])
    assert v.ok is False


def test_tolerancia_cop_1_peso():
    texto = "Caja $704.722.004."  # +1 por redondeo
    v = verificar(texto, [_cop(Decimal("704722003"))])
    assert v.ok is True


def test_meses_fuera_de_tolerancia_falla():
    texto = "El runway es de 6 meses."
    v = verificar(texto, [_meses(Decimal("4.2"))])
    assert v.ok is False


def test_evidencia_no_disponible_no_respalda_cifra():
    # un ResultadoCFO abstenido NO respalda ninguna cifra
    r = ResultadoCFO(
        concepto="iva_cuatrimestre",
        valor=None,
        unidad="COP",
        disponible=False,
        evidencia=Evidencia(fuente="f", fecha_corte=None, ref="x"),
    )
    v = verificar("El IVA es $36.204.698.", [r])
    assert v.ok is False


def test_dolares_cero_falso_es_atrapado():
    v = verificar("No debes nada: $0.", [_cop(Decimal("704722003"))])
    assert v.ok is False


# --- Regresión / hardening (Task 7 hardening pass) ---------------------------
# Fijan la intención de la heurística: no castigar lo inocuo (cero legítimo,
# números pelados sin formato de dinero) y seguir atrapando lo inventado
# (monto grande junto a uno real, múltiples cifras con múltiple evidencia).


def test_cero_legitimo_con_evidencia_pasa():
    # un $0 que SÍ tiene evidencia (caja realmente en 0) no debe marcarse
    v = verificar("La caja hoy es $0.", [_cop(Decimal("0"))])
    assert v.ok is True
    assert v.cifras_sin_evidencia == []


def test_entero_pelado_sin_formato_no_se_marca():
    # números sin formato de dinero (nº de cuenta) no son candidatos → no molestan
    texto = "Según la cuenta 5493, la caja es $704.722.003."
    v = verificar(texto, [_cop(Decimal("704722003"))])
    assert v.ok is True


def test_monto_grande_inventado_junto_a_uno_real_se_atrapa():
    texto = "La caja es $704.722.003; proyecto ingresos de $1.200.000.000."
    v = verificar(texto, [_cop(Decimal("704722003"))])
    assert v.ok is False
    assert any("1.200.000.000" in t for t in v.cifras_sin_evidencia)


def test_multiples_cifras_todas_respaldadas_pasa():
    texto = "Caja $704.722.003 y el IVA del cuatrimestre es $36.204.698."
    v = verificar(texto, [_cop(Decimal("704722003")), _cop(Decimal("36204698"))])
    assert v.ok is True
    assert v.cifras_sin_evidencia == []


# --- Robustez formato "wire" (hallazgo de revisión sobre commit 80b70cd) -----
# tools.resultado_a_dict serializa valor como str(Decimal(...)): dígitos pelados
# sin separador de miles para COP ("704722003") y con PUNTO decimal para meses
# ("4.2") — no el formato es-CO con "$"/miles/coma que asumía la heurística
# original. El prompt (regla #1) exige reproducir las cifras LITERALMENTE, así
# que la respuesta real del modelo llega mayoritariamente en formato wire.


def test_bare_digit_wire_inventado_se_atrapa():
    # monto fabricado en formato wire (sin $, sin separadores) DEBE atraparse
    v = verificar("el flujo proyectado es 950000000", [_cop(Decimal("704722003"))])
    assert v.ok is False
    assert any("950000000" in t for t in v.cifras_sin_evidencia)


def test_bare_digit_wire_que_coincide_pasa():
    v = verificar("la caja es 704722003", [_cop(Decimal("704722003"))])
    assert v.ok is True


def test_anio_no_marcado_pese_a_nuevo_regex():
    # el umbral de 5+ dígitos pelados no debe empezar a atrapar años de 4 dígitos
    cifras = extraer_cifras("En 2026 la caja subió")
    assert all(v != Decimal("2026") for v, _, _ in cifras)


def test_runway_wire_punto_decimal_pasa():
    # str(Decimal("4.2")) usa PUNTO — el runway real del modelo llega así
    v = verificar("El runway es de 4.2 meses.", [_meses(Decimal("4.2"))])
    assert v.ok is True


def test_runway_coma_decimal_sigue_pasando():
    v = verificar("El runway es de 4,2 meses.", [_meses(Decimal("4.2"))])
    assert v.ok is True
