"""RF-F10 · Fundacional §2 — Agregación de la serie proyectada por trimestre/año.

Hoy el motor genera series MENSUALES; mostrar 240 puntos (20 años) es ruido. La
agregación por trimestre/año hace usable el horizonte largo sin tocar el motor
(golden-master 176 meses intacto, regla del motor intocable).

**Semántica** (crítica, distinta según sea stock o flujo):
  · `caja_final`: **caja del ÚLTIMO mes del periodo** — es un stock, no se suma.
  · `piso`: **min caja** durante el periodo (el punto más bajo).
  · `flujo`, `ingreso_bruto`, `egresos`: **SUMA** de los meses del periodo.
  · `motos`: **SUMA** de unidades vendidas.

Etiquetas: `"2027"` (anual), `"2027-Q3"` (trimestre 1..4). `desde`/`hasta` son
el primer y último `mes` con datos dentro del periodo — no bordes del calendario:
un año/trimestre incompleto (arranque parcial, cierre parcial) declara sus
límites reales y `meses_en_periodo`.

Función pura. Devuelve `list[dict]` con montos como STRING COP (regla 1); el
caller Serializa directo a JSON sin manejar Decimal.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from typing import Literal

from app.core.money import money_str
from app.proyeccion.motor import MesProyeccion

Granularidad = Literal["trimestre", "anual"]


def _clave_periodo(mes_iso: str, granularidad: Granularidad) -> str:
    """`YYYY-MM` → etiqueta del periodo: `"2027"` (anual) o `"2027-Q3"` (trimestre)."""
    y, m = int(mes_iso[:4]), int(mes_iso[5:7])
    if granularidad == "anual":
        return f"{y:04d}"
    if granularidad == "trimestre":
        q = (m - 1) // 3 + 1
        return f"{y:04d}-Q{q}"
    raise ValueError(f"granularidad no soportada: {granularidad!r}")


def agregar_por_periodo(
    meses: Iterable[MesProyeccion],
    *,
    granularidad: Granularidad,
) -> list[dict]:
    """Agrega la serie mensual al periodo pedido, preservando semántica
    stock/flujo (ver docstring del módulo). Serie vacía → `[]`. Preserva el
    orden cronológico (dict ordered en Python 3.7+ + inserción en orden)."""
    if granularidad not in ("trimestre", "anual"):
        raise ValueError(
            f"granularidad no soportada: {granularidad!r} "
            "(usa 'trimestre' o 'anual')"
        )
    # dict preserva orden de inserción → los meses vienen ordenados por diseño
    # del motor, así que la iteración natural respeta cronología.
    grupos: dict[str, list[MesProyeccion]] = {}
    for m in meses:
        etiqueta = _clave_periodo(m.mes, granularidad)
        grupos.setdefault(etiqueta, []).append(m)

    salida: list[dict] = []
    for etiqueta, ms in grupos.items():
        ultimo = ms[-1]
        piso = min(m.caja for m in ms)
        flujo = sum((m.flujo for m in ms), Decimal("0"))
        ingreso = sum((m.ingreso_bruto for m in ms), Decimal("0"))
        egresos = sum((m.egresos for m in ms), Decimal("0"))
        motos = sum(m.motos for m in ms)
        salida.append(
            {
                "etiqueta": etiqueta,
                "desde": ms[0].mes,
                "hasta": ultimo.mes,
                "meses_en_periodo": len(ms),
                "caja_final": money_str(ultimo.caja),
                "piso": money_str(piso),
                "flujo": money_str(flujo),
                "ingreso_bruto": money_str(ingreso),
                "egresos": money_str(egresos),
                "motos": motos,
            }
        )
    return salida
