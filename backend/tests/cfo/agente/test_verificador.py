# backend/tests/cfo/agente/test_verificador.py
"""FABS · batería del verificador cifra→concepto (control crítico, inc3 Pieza A).

Contrato NUEVO — reemplaza el de inc2 (historial en git para la versión previa): el
modelo nunca escribe una cifra cruda, cita conceptos con `[[concepto]]`. Por eso esta
batería ya NO tiene casos "cifra con evidencia real → pasa": bajo el contrato nuevo
TODA cifra cruda es violación, tenga o no evidencia real detrás — eso es precisamente
lo que cierra el hueco de inc2 (una cifra de IVA mal-etiquetada como caja pasaba si el
valor caía en tolerancia de algún ResultadoCFO en COP; ahora no hay pool de tolerancia
que la respalde, período).

Los casos de inc2 que probaban "cifra inventada/sumada/en formato wire se atrapa" se
preservan reexpresados más abajo: bajo el contrato nuevo se atrapan por la MISMA regla
que una cifra correcta (cualquier cifra cruda = rechazo), así que quedan como
demostraciones del mecanismo — ya no como casos con lógica de comparación propia. Se
preserva también la cobertura de porcentajes (COMPAS no tiene ese concepto) y se
añade la validación de tokens (concepto inexistente / no disponible este turno), que
es la pieza nueva de este contrato."""

from decimal import Decimal

from app.cfo.agente.verificador import extraer_cifras, verificar
from app.cfo.calc.evidencia import Evidencia, ResultadoCFO


def _r(concepto, valor, unidad, disp=True):
    return ResultadoCFO(
        concepto=concepto,
        valor=valor,
        unidad=unidad,
        disponible=disp,
        evidencia=Evidencia(fuente="f", fecha_corte="2026-08-11", ref="x"),
    )


def _caja():
    return _r("caja_hoy", Decimal("704722003.00"), "COP")


def _iva():
    return _r("iva_cuatrimestre", Decimal("36204698.10"), "COP")


# --- Contrato nuevo: tokens válidos pasan; cifras crudas y tokens inválidos no ----


def test_tokens_validos_pasan():
    v = verificar(
        "Tu caja es [[caja_hoy]] y el IVA es [[iva_cuatrimestre]].", [_caja(), _iva()]
    )
    assert v.ok is True
    assert v.cifras_sin_evidencia == [] and v.tokens_invalidos == []


def test_cifra_cruda_se_rechaza():
    # el modelo escribió un número en vez de un token
    v = verificar("Tu caja es $704.722.003.", [_caja()])
    assert v.ok is False
    assert any("704.722.003" in c for c in v.cifras_sin_evidencia)


def test_el_caso_vinculante_caja_con_valor_de_iva_se_rechaza():
    # el modelo escribe crudo el valor del IVA bajo la etiqueta 'caja'. Este es EL
    # hueco de inc2: con el contrato viejo (evidencia agrupada por `unidad`, nunca por
    # `concepto`) esto PASABA porque $36.204.698 cae en tolerancia de ALGÚN
    # ResultadoCFO en COP del turno (el de IVA), sin importar que el texto lo
    # etiquete como caja. El contrato nuevo lo cierra por construcción: ya no existe
    # el camino "está en el pool COP" porque no hay pool — toda cifra cruda se
    # rechaza sin mirar su valor.
    v = verificar("Tu caja es $36.204.698.", [_caja(), _iva()])
    assert v.ok is False  # ya no puede pasar por 'está en el pool COP'


def test_token_de_concepto_inexistente_se_rechaza():
    v = verificar("Las ventas fueron [[ventas]].", [_caja()])
    assert v.ok is False
    assert "[[ventas]]" in v.tokens_invalidos


def test_token_de_concepto_no_disponible_se_rechaza():
    v = verificar(
        "El runway es [[runway]].", [_caja(), _r("runway", None, "meses", disp=False)]
    )
    assert v.ok is False
    assert "[[runway]]" in v.tokens_invalidos


def test_token_valido_con_espacios_se_reconoce():
    # RE_TOKEN (compartido con conceptos.sustituir_tokens, hardening FINAL-REVIEW)
    # es tolerante a espacios internos: "[[ caja_hoy ]]" debe reconocerse como
    # token válido igual que "[[caja_hoy]]". Antes del fix, la regex sin '\s*' no
    # lo reconocía como token EN ABSOLUTO (ni válido ni inválido) — pasaba el
    # veredicto por accidente (no había nada que marcar como inválido) pero luego
    # conceptos.sustituir_tokens tampoco lo sustituía: el placeholder crudo se
    # filtraba al usuario pese a ok=True.
    v = verificar("Tu caja es [[ caja_hoy ]].", [_caja()])
    assert v.ok is True
    assert v.cifras_sin_evidencia == [] and v.tokens_invalidos == []


def test_token_invalido_con_espacios_tambien_se_rechaza():
    # a diferencia del caso anterior, este SÍ distingue pre/post-fix: un concepto
    # inexistente con espacios debe rechazarse igual que sin espacios. Antes del
    # fix no se reconocía como token en absoluto, así que no caía en
    # tokens_invalidos y el veredicto pasaba ok=True indebidamente.
    v = verificar("Las ventas fueron [[ ventas ]].", [_caja()])
    assert v.ok is False
    assert "[[ ventas ]]" in v.tokens_invalidos


def test_porcentaje_crudo_se_rechaza():
    # COMPAS no tiene concepto de "porcentaje": ninguna tool lo calcula ni lo
    # devuelve, así que un % en la respuesta es siempre auto-cálculo del modelo.
    v = verificar("El IVA es el 25% de tus ingresos.", [_caja()])
    assert v.ok is False


def test_porcentaje_con_decimal_y_espacio_tambien_se_rechaza():
    v = verificar("Tu carga tributaria es 12,5 % del flujo.", [_caja()])
    assert v.ok is False


def test_respuesta_sin_cifras_ni_tokens_pasa():
    v = verificar("Con los datos disponibles no puedo confirmar eso.", [])
    assert v.ok is True


# --- Reexpresados de inc2 --------------------------------------------------------
# extraer_cifras/_es_monto/_a_decimal_* (detección) no cambiaron, así que estos casos
# siguen demostrando que una cifra fabricada/sumada/en formato wire se atrapa — ahora
# por la MISMA regla que cualquier cifra cruda, no por comparación de valor contra un
# pool. Donde el caso viejo afirmaba "... y por eso PASA", aquí se invierte a propósito
# (queda documentado el porqué): es la diferencia central del contrato nuevo.


def test_monto_inventado_se_atrapa_aunque_haya_uno_real_al_lado():
    texto = "La caja hoy es $704.722.003, pero podrías tener hasta $50.000.000 extra."
    v = verificar(texto, [_caja()])
    assert v.ok is False
    assert any("50.000.000" in c for c in v.cifras_sin_evidencia)


def test_suma_inventada_se_atrapa():
    # el modelo sumó caja + IVA en un tercer número que ninguna tool devolvió
    v = verificar("En total tienes $740.926.701 entre caja e IVA.", [_caja(), _iva()])
    assert v.ok is False


def test_dolares_cero_crudo_se_rechaza():
    # un $0 crudo es cifra prohibida aunque "suene" inocuo (regla #3 del prompt:
    # jamás un $0 falso).
    v = verificar("No debes nada: $0.", [_caja()])
    assert v.ok is False


def test_cero_real_tambien_debe_citarse_por_token_no_escribirse_crudo():
    # a diferencia de inc2 (donde un $0 que coincidía con la evidencia real pasaba),
    # aquí el valor verdadero SÍ es 0 y el veredicto sigue siendo ok=False: el
    # contrato exige [[caja_hoy]], nunca "$0" escrito a mano — sea correcto o no.
    v = verificar("La caja hoy es $0.", [_r("caja_hoy", Decimal("0"), "COP")])
    assert v.ok is False


def test_multiples_cifras_correctas_se_rechazan_todas_por_ser_crudas():
    # las DOS cifras son exactamente correctas y aun así el veredicto es ok=False:
    # el contrato no perdona una cifra cruda por tener respaldo real detrás, siempre
    # exige el token.
    texto = "Caja $704.722.003 y el IVA del cuatrimestre es $36.204.698."
    v = verificar(texto, [_caja(), _iva()])
    assert v.ok is False
    assert len(v.cifras_sin_evidencia) == 2


def test_meses_crudo_se_rechaza_aunque_coincida_con_la_evidencia():
    v = verificar("El runway es de 4,2 meses.", [_r("runway", Decimal("4.2"), "meses")])
    assert v.ok is False
    assert any("meses" in c for c in v.cifras_sin_evidencia)


def test_cifra_en_formato_wire_tambien_se_rechaza():
    # formato real que devuelven las tools (str(Decimal(money_str(x))): sin '$' ni
    # separador de miles, punto decimal de 2 cifras). El modelo ya no lo ve (A2:
    # tools.py deja de exponer `valor`), pero si de algún modo una cifra cruda llega
    # al texto en esta forma, debe rechazarse igual que cualquier otra.
    v = verificar("La caja hoy es 704722003.00.", [_caja()])
    assert v.ok is False


def test_bare_digit_inventado_se_atrapa():
    # cifra fabricada en dígitos pelados (sin $, sin separadores, >=5 dígitos) →
    # cruda → rechazo. Ningún otro caso de la batería ejercita esta rama de
    # `_es_monto` (todos usan '$' o un separador, que la cortocircuitan antes):
    # sin este caso, un monto fabricado en esta forma exacta no tendría cobertura
    # de que SÍ se atrapa.
    v = verificar("Tu caja es 950000000.", [_caja()])
    assert v.ok is False
    assert any("950000000" in c for c in v.cifras_sin_evidencia)


def test_numero_sin_formato_de_dinero_no_se_marca():
    # un nº de cuenta pelado y corto no es un monto (sin '$'/separador y menos de 5
    # dígitos): no debe generar un falso positivo. Sesgo conservador del módulo: no
    # abstenerse de lo inocuo.
    v = verificar("Según la cuenta 5493, no tengo esa cifra a mano.", [_caja()])
    assert v.ok is True


def test_extrae_montos_y_meses_ignora_anios_y_fechas():
    # extraer_cifras no cambió (sigue siendo el detector de cifras crudas); esta
    # regresión de inc2 sigue vigente tal cual.
    texto = (
        "En 2026, al 10 de septiembre, la caja es $704.722.003 y el runway "
        "es de 4,2 meses. Período C2."
    )
    cifras = {(v, u) for v, u, _ in extraer_cifras(texto)}
    assert (Decimal("704722003"), "COP") in cifras
    assert (Decimal("4.2"), "meses") in cifras
    # 2026 (año), 10 (día), C2 (etiqueta) NO son cifras monetarias/unitarias
    assert all(not (v == Decimal("2026")) for v, _, _ in extraer_cifras(texto))


# --- Unidades crudas (inc4 Task 3): "12 motos" cierra el hueco del entero pequeño ---
# Antes de este contrato, un conteo de motos ("12 motos") no se detectaba: 12 tiene
# menos de 5 dígitos y no lleva separador, así que `_es_monto` lo dejaba pasar como
# inocuo (nº de cuenta/día). El modelo debe citar `[[unidades_extra]]`, nunca escribir
# el conteo — igual que ya no puede escribir COP/meses/% crudos.


def _disp(concepto, unidad="unidades", valor=12):
    return ResultadoCFO(
        concepto=concepto,
        valor=Decimal(valor),
        unidad=unidad,
        disponible=True,
        evidencia=Evidencia(fuente="x", fecha_corte=None, ref="r"),
    )


def test_rechaza_unidades_crudas():
    v = verificar("Vende 12 motos más.", [_disp("unidades_extra")])
    assert v.ok is False and any("12 motos" in c for c in v.cifras_sin_evidencia)


def test_acepta_token_de_unidades():
    v = verificar("Vende [[unidades_extra]] más.", [_disp("unidades_extra")])
    assert v.ok is True


# --- Fix round 1: singular "unidad" (bug del regex original, hallazgo de review) ---
# `unidades?` compila a "unidade" + 's' opcional — NUNCA matchea el singular real
# "unidad" (que no lleva la 'e' final). Bypass reproducido: "1 unidad" pasaba con
# ok=True. Fix: `unidad(?:es)?`, el mismo patrón que ya usa `_RE_MESES`
# (`mes(?:es)?`) para pluralizar sustantivos terminados en consonante.


def test_rechaza_unidad_singular_cruda():
    v = verificar("Vende 1 unidad más.", [_disp("unidades_extra")])
    assert v.ok is False and any("1 unidad" in c for c in v.cifras_sin_evidencia)


def test_rechaza_moto_singular_cruda():
    # simetría con el plural "motos" (ya cubierto arriba): el singular "1 moto" ya
    # funcionaba hoy (motos? sí cubre el singular), pero no tenía test dedicado.
    v = verificar("Compra 1 moto más.", [_disp("unidades_extra")])
    assert v.ok is False


def test_rechaza_motocicleta_singular_cruda():
    v = verificar("1 motocicleta.", [_disp("unidades_extra")])
    assert v.ok is False
