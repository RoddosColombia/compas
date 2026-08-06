# EXCEPCIÓN DE GATE — E1 PR2-I: merge SIN auditoría Kimi

**Fecha:** 2026-08-06 · **PR:** #69 · **Rama:** `feat/e1-p2-anclaje-service`
**Autoriza:** Andrés (CEO), decisión explícita en sesión.

## Qué se excepciona
El `CLAUDE.md` (regla de oro) exige `AUDITORIA-KIMI ≥ 9.0` registrada antes de todo merge
crítico. Para **este PR (P2)** el CEO autorizó **explícitamente mergear SIN pasar por Kimi**.

## Constancia honesta
- **NO hubo auditoría adversarial de Kimi** sobre P2. El paquete quedó preparado
  (`SOLICITUD.md`, `EVIDENCIA.md`, `PAQUETE.pdf`) por si se quiere correr el gate
  **post-merge**, pero el merge NO esperó su veredicto.
- El PR incluye un cambio delicado que normalmente ameritaría lupa de Kimi: el **ajuste al
  mapeo de P1** (`lectura.py`, quitar 0120/0130/0140/4060), que re-toca un módulo ya
  auditado (gate P1 9.5).
- Sí se conservó el mínimo técnico: **CI 7/7 verde** antes del merge, `motor.py` cero diffs
  (R0), golden 48/48, suite E1 15/15, regresión 137 passed, ruff (check + format) limpio.

## Alcance de la excepción
Puntual para P2. **No** deroga la regla de oro para las demás piezas (P3–P6) ni cambia el
protocolo general de auditoría con Kimi. Si el CEO quiere el gate retroactivo de P2, se corre
como ronda `PR2-R` con el `PAQUETE.pdf` ya listo.
