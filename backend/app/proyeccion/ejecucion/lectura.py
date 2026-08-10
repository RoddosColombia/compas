# backend/app/proyeccion/ejecucion/lectura.py
"""E1 · P1 — lectura de la ejecución real mapeada a los conceptos del motor.

Traduce el ejecutado por rubro (la verdad del libro) a los conceptos que el motor
proyecta, usando el mapeo del Plan de Cuentas (I-PLAN §10, decisiones del CEO):

    neto (ingreso)   ← 0110 Recaudo de cartera   [único rubro de ingreso real de RODDOS]
    pago_inventario  ← 1010 Producto                        [R-1: 1010 entero]
    fondeo           ← 4030 Garantía cupo (Auteco)          [REEMPLAZA el paramétrico]
    costo_nueva      ← 1020 SOAT/Matrículas                 [R-1: 1010 no entra aquí]
    gps              ← 1030 Seguros (Hunter)
    gastos_fijos     ← TODO OPERACIÓN + NÓMINA + OTROS (menos 5060 y menos sistema)
    int_deuda        ← 4010 Préstamos · 4020 Tarjetas · 4040 Deudas impuestos ·
                       4050 Proveedores · 4070 Rodante–Financiación (PTS6-D)
    iva              ← 5060 Impuestos

NOTA (E1-P2, decisión CEO 2026-08-06): se quitaron del mapeo 0120 (Cuotas iniciales),
0130 (RODANTE), 0140 (Otros ingresos) y 4060 (Inventario Auteco) — están en la semilla
pero NO en la taxonomía de PROD (rubros "dormidos": los ingresos van todos a 0110 y
Auteco va por D2). Con ellos en el mapeo, B12 disparaba ValueError en producción. Los 9
códigos restantes existen todos en PROD. Si algún día se siembran, se re-agregan aquí.

FUNCIÓN PURA (sin Mongo): recibe el snapshot de rubros + el valor ejecutado por
rubro_id + los ids de los rubros neutros, y devuelve {concepto: Decimal} + sin_mapear.
Nada se adivina:
  • los 3 NEUTROS se excluyen por rubro_id (A1) — antes que cualquier regla de grupo;
  • R-1 (1010→pago_inventario entero) queda documentado; R-2 (4040 en sin_mapear)
    fue SUPERSEDED por PTS6-D (CEO 2026-08-10): 4040 y 4070 → int_deuda. El canal
    `sin_mapear` sigue vivo para códigos genuinamente sin concepto;
  • si un código del mapeo NO existe en la taxonomía → error ruidoso (B12).

E1 NO decide temporalidad aquí: esta capa solo MAPEA. Qué meses se anclan y con qué
regla (cerrado/en-ejecución/futuro) es P2. Auteco: para meses cerrados el pago real ES
parte del ejecutado (1010+4060, 4030) y E1 lo refleja; el Auteco FUTURO lo posee D2 —
la precedencia (P3) evita el doble conteo.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

_CERO = Decimal("0.00")

# Conceptos del motor que E1 puede anclar (Auteco incluido para meses cerrados).
CONCEPTOS = (
    "neto",
    "pago_inventario",
    "fondeo",
    "costo_nueva",
    "gps",
    "gastos_fijos",
    "int_deuda",
    "iva",
)

# Mapeo explícito por código (los específicos del §10). Solo códigos presentes en la
# taxonomía de PROD — 0120/0130/0140/4060 quitados (ver NOTA del docstring).
# PTS6-D (decisión CEO 2026-08-10, supersede R-2): 4040 (Deudas impuestos) y 4070
# (Rodante – Financiación a clientes, creado en PTS6-C) entran a `int_deuda` para que
# el Gasto del mes en curso refleje TODO el presupuesto no-costo. R-2 (4040 en
# sin_mapear) queda superseded; el mecanismo sin_mapear sigue vivo para códigos
# genuinamente sin concepto.
_CONCEPTO_POR_CODIGO: dict[str, str] = {
    "0110": "neto",  # único rubro de ingreso real; E1 ancla el neto vía ingreso_real
    "1010": "pago_inventario",  # R-1: entero a pago_inventario
    "4030": "fondeo",
    "1020": "costo_nueva",
    "1030": "gps",
    "4010": "int_deuda",
    "4020": "int_deuda",
    "4040": "int_deuda",  # PTS6-D: supersede R-2 (CEO 2026-08-10)
    "4050": "int_deuda",
    "4070": "int_deuda",  # PTS6-D: Rodante – Financiación a clientes (PTS6-C)
    "5060": "iva",
}

# `gastos_fijos` = todo lo de estos grupos que no esté ya mapeado por código, no sea de
# sistema y no sea neutro. Robusto a que la taxonomía sume rubros nuevos (2130, 2140…).
_GRUPOS_GASTOS_FIJOS = frozenset({"operacion", "nomina", "otros"})


@dataclass(frozen=True)
class RubroInfo:
    """Lo mínimo del rubro para mapear (snapshot, sin Mongo)."""

    id: str
    codigo: str | None
    grupo: str
    nombre: str
    es_sistema: bool


@dataclass(frozen=True)
class ResultadoMapeo:
    conceptos: dict[str, Decimal]  # {concepto: Σ valor}
    sin_mapear: list[str]  # nombres de rubros con valor y sin concepto (se reportan)


def _concepto_de(rubro: RubroInfo) -> str | None:
    """El concepto de un rubro, o None si no mapea. NO aplica la exclusión de neutros
    (eso lo hace el llamador ANTES, por id)."""
    if rubro.codigo is not None and rubro.codigo in _CONCEPTO_POR_CODIGO:
        return _CONCEPTO_POR_CODIGO[rubro.codigo]
    if rubro.grupo in _GRUPOS_GASTOS_FIJOS and not rubro.es_sistema:
        return "gastos_fijos"
    return None


def mapear_a_conceptos(
    *,
    rubros: list[RubroInfo],
    valor_por_rubro_id: dict[str, Decimal],
    neutros_ids: set[str],
) -> ResultadoMapeo:
    """Suma el ejecutado por concepto del motor. `valor_por_rubro_id` es la magnitud
    ejecutada por rubro (Σ egresos para egresos; Σ ingresos para los rubros de ingreso;
    lo arma el llamador P2). Excluye los neutros por id ANTES de mapear (A1). Verifica
    que todo código del mapeo exista en la taxonomía (B12) → error ruidoso si falta."""
    # B12: la taxonomía debe contener todos los códigos que el mapeo referencia.
    codigos_presentes = {r.codigo for r in rubros if r.codigo is not None}
    faltantes = sorted(set(_CONCEPTO_POR_CODIGO) - codigos_presentes)
    if faltantes:
        raise ValueError(
            "E1: el mapeo referencia códigos ausentes de la taxonomía vigente "
            f"(B12): {faltantes}. Créalos por C1 antes de anclar."
        )

    conceptos: dict[str, Decimal] = {c: _CERO for c in CONCEPTOS}
    sin_mapear: list[str] = []
    for r in rubros:
        if r.id in neutros_ids:  # A1: exclusión por id, primero
            continue
        valor = valor_por_rubro_id.get(r.id)
        concepto = _concepto_de(r)
        if concepto is None:
            # R-2 (4040) y cualquier rubro no-sistema sin concepto: se reporta si movió
            # dinero (para no ensuciar con rubros vacíos).
            if valor is not None and valor != _CERO and not r.es_sistema:
                sin_mapear.append(r.nombre)
            continue
        if valor is not None:
            conceptos[concepto] = conceptos[concepto] + valor
    return ResultadoMapeo(conceptos=conceptos, sin_mapear=sorted(sin_mapear))
