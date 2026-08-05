# backend/app/domain/rubros_neutros.py
"""Rubros NEUTROS para la lectura de la realidad (una verdad, un lugar).

Dinero que entró/salió de la cuenta pero NO es recaudo ni gasto operativo: contarlo
inflaría el ingreso real (metas) o el ejecutado anclado (E1). La exclusión se resuelve
SIEMPRE por `rubro_id` (nunca por grupo ni `es_sistema`): el id es la identidad estable;
el nombre puede cambiar y grupo/es_sistema barren de más.

El set:
  • 'Reversas y devoluciones'    — FIX-B: reversas GMF, devoluciones, reembolsos.
  • 'Tránsito Wava mes anterior' — CR-WAVA: depósito Wava del mes previo que llega.
  • 'Ajuste de conciliación'     — CR-WAVA: contra-asiento de una reapertura de cierre.

Promovido desde `metas_ingreso.service` (donde nació con FIX-B) para que E1 y metas
compartan exactamente el mismo conjunto — no dos copias que puedan divergir."""

RUBROS_NEUTROS_INGRESO_REAL: frozenset[str] = frozenset(
    {
        "Reversas y devoluciones",
        "Tránsito Wava mes anterior",
        "Ajuste de conciliación",
    }
)
