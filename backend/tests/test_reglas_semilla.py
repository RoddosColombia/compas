# backend/tests/test_reglas_semilla.py
"""RF-F1 (COMPAS 2.0) — generador de reglas SEMILLA, aprendidas de la curaduría real.

Enfoque A (Fundacional §2 RF-F1 + REGLA DE ORO «no adivinar, usar la curaduría del
CEO»): las reglas NO se inventan; se **aprenden** de los movimientos que el CEO ya
clasificó a mano. `generar_reglas_semilla` es una función PURA (sin Mongo): dado el
histórico clasificado, propone patrones `contains` que reproducen esas decisiones solo
cuando la evidencia es limpia (pureza) y suficiente; nunca un patrón ambiguo.

Contrato con C3: reusa `normalizar_texto` (única normalización, Kimi §3); el patrón
resultante respeta `PATRON_MIN` y la unicidad (patrón_normalizado, tipo_flujo).
"""

from decimal import Decimal

import pytest
from app.domain.rubro import TipoFlujo
from app.reglas.semilla import MovimientoClasificado as Mov
from app.reglas.semilla import generar_reglas_semilla
from beanie import PydanticObjectId

EGR, ING = TipoFlujo.EGRESO, TipoFlujo.INGRESO
ARR = PydanticObjectId()  # Arriendos
NOM = PydanticObjectId()  # Nómina
PRO = PydanticObjectId()  # Proveedores
REC = PydanticObjectId()  # Recaudo (ingreso)
OTR = PydanticObjectId()  # Otros


def _por_patron(reglas):
    return {r.patron_normalizado: r for r in reglas}


def test_patron_puro_con_evidencia_suficiente_genera_regla():
    movs = [Mov("Pago arriendo local norte", ARR, EGR) for _ in range(3)]
    reglas = generar_reglas_semilla(movs, min_evidencia=3)
    p = _por_patron(reglas)
    assert "arriendo" in p
    r = p["arriendo"]
    assert r.rubro_id == ARR
    assert r.tipo_flujo == EGR
    assert r.evidencia == 3
    assert r.pureza == Decimal("1")


def test_token_ambiguo_no_genera_regla():
    """Un token que en la historia cayó en 2 rubros (pureza < umbral) NO se propone —
    el sistema no adivina. Pero los tokens limpios que lo acompañan sí."""
    movs = [
        Mov("Transferencia proveedor uno", PRO, EGR),
        Mov("Transferencia proveedor dos", PRO, EGR),
        Mov("Transferencia sueldo ana", NOM, EGR),
        Mov("Transferencia sueldo beto", NOM, EGR),
    ]
    reglas = generar_reglas_semilla(movs, min_evidencia=2, min_pureza=Decimal("1"))
    p = _por_patron(reglas)
    assert "transferencia" not in p  # ambiguo → descartado
    assert "proveedor" in p and p["proveedor"].rubro_id == PRO
    assert "sueldo" in p and p["sueldo"].rubro_id == NOM


def test_evidencia_insuficiente_no_genera_regla():
    movs = [Mov("Pago renting equipo", ARR, EGR) for _ in range(2)]
    reglas = generar_reglas_semilla(movs, min_evidencia=3)
    assert all(r.patron_normalizado != "renting" for r in reglas)


def test_normalizacion_compartida_tildes_y_mayusculas():
    movs = [
        Mov("Pago Nómina agosto", NOM, EGR),
        Mov("pago nomina julio", NOM, EGR),
        Mov("NOMINA junio", NOM, EGR),
    ]
    reglas = generar_reglas_semilla(movs, min_evidencia=3)
    p = _por_patron(reglas)
    assert "nomina" in p and p["nomina"].evidencia == 3


def test_stopwords_y_numeros_no_son_patron():
    movs = [Mov("Pago 12345 de arriendo", ARR, EGR) for _ in range(3)]
    reglas = generar_reglas_semilla(movs, min_evidencia=3)
    p = _por_patron(reglas)
    assert "pago" not in p  # stopword bancaria genérica
    assert "de" not in p  # < PATRON_MIN y stopword
    assert "12345" not in p  # número puro
    assert "arriendo" in p


def test_unicidad_patron_tipo():
    movs = [Mov("Arriendo bodega", ARR, EGR) for _ in range(4)]
    reglas = generar_reglas_semilla(movs, min_evidencia=3)
    cuantas = [r for r in reglas if r.patron_normalizado == "arriendo"]
    assert len(cuantas) == 1


def test_tipo_flujo_separa_la_pureza():
    """El mismo token puede ser limpio en ingreso hacia un rubro y en egreso hacia otro:
    la pureza se evalúa DENTRO de cada tipo_flujo → dos reglas distintas."""
    movs = [Mov("Giro Wava recaudo", REC, ING) for _ in range(3)] + [
        Mov("Comision Wava servicio", OTR, EGR) for _ in range(3)
    ]
    reglas = generar_reglas_semilla(movs, min_evidencia=3)
    wava = [r for r in reglas if r.patron_normalizado == "wava"]
    assert {r.tipo_flujo for r in wava} == {ING, EGR}
    assert {r.rubro_id for r in wava} == {REC, OTR}


def test_prioridad_determinista_por_evidencia():
    movs = [Mov("Arriendo bodega", ARR, EGR) for _ in range(5)] + [
        Mov("Renting camioneta", PRO, EGR) for _ in range(3)
    ]
    reglas = generar_reglas_semilla(movs, min_evidencia=3)
    p = _por_patron(reglas)
    # más evidencia = más prioridad (número menor)
    assert p["arriendo"].prioridad < p["renting"].prioridad


def test_sin_movimientos_devuelve_vacio():
    assert generar_reglas_semilla([], min_evidencia=3) == []


def test_pureza_configurable_afloja_el_umbral():
    """Con pureza 1.0 un token 3-a-1 se descarta; bajando el umbral a 0.75 se propone
    hacia el rubro dominante (decisión que el CEO puede tomar al sembrar)."""
    movs = [
        Mov("Servicio mantenimiento uno", OTR, EGR),
        Mov("Servicio mantenimiento dos", OTR, EGR),
        Mov("Servicio mantenimiento tres", OTR, EGR),
        Mov("Servicio mantenimiento cuatro", PRO, EGR),
    ]
    estricto = generar_reglas_semilla(movs, min_evidencia=3, min_pureza=Decimal("1"))
    assert all(r.patron_normalizado != "mantenimiento" for r in estricto)
    flojo = generar_reglas_semilla(movs, min_evidencia=3, min_pureza=Decimal("0.75"))
    p = _por_patron(flojo)
    assert "mantenimiento" in p
    assert p["mantenimiento"].rubro_id == OTR
    assert p["mantenimiento"].pureza == Decimal("0.75")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
