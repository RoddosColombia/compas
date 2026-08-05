# backend/app/proyeccion/ejecucion/__init__.py
"""Capa E1 — anclaje de la proyección a la ejecución real (tercera capa post-motor).

Orden de aplicación: motor → EJECUCIÓN (E1) → OBLIGACIONES (D2) → IMPACTOS (D1).
E1 reemplaza las líneas de gasto/costo/ingreso de los meses cerrado / en-ejecución /
futuro-con-presupuesto con la mejor fuente disponible, y re-acumula la caja desde ahí.
`motor.py` cero diffs (R0)."""
