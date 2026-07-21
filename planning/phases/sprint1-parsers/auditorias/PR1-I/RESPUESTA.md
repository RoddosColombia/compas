# RESPUESTA KIMI — sprint1-parsers · PR1-I

**Veredicto:** NO-GO condicionado — **8.0 / 10** (umbral ≥ 9.0). Fecha: 2026-07-20. Merge `0a3f1fa`.

Salidas verificadas por Kimi: pytest 209/19 local · 8 @requires_real_mongo · ruff limpio.

## A-01 (Alta) — huella `banco|fecha|tipo|desc|valor` sin discriminador de ocurrencia
Dos movimientos legítimos idénticos el mismo día (misma fecha/desc/monto/tipo) → misma huella → el 2º muere como duplicado. Real en el recaudo de RODDOS (cuotas semanales iguales, desc genérica "Abono"). Pérdida de dinero en silencio. Es el riesgo M-1 del PLAN, sin cerrar.
**Corrección:** ordinal de ocurrencia de la huella dentro del archivo (1ª→…|1, 2ª→…|2) + CR de A2 con análisis de colisión sobre fixtures reales + 3 tests (dos idénticos→ambos; re-subida→0; solape→0).

## Medias
- **M-01** — fecha sin año → año actual (bug de frontera dic/ene). Fix: año del encabezado del extracto (periodo).
- **M-02** — regla 8 y §1.6 NO son incompatibles: `session.with_transaction` admite `insertMany ordered=False` + captura de `BulkWriteError` + commit. Envolver la finalización.
- **M-03** — N+1: `MesControl.find_one` por movimiento (5.000 en el RNF <30s). Cachear por mes.
- **M-04** — sin S3 los originales no se conservan (Spec §1.6, "el dato crudo siempre re-procesable"). Regla dura: ninguna carga real hasta S3 (o copia local + backfill).

## Bajas
- Reaper de cargas sin implementar (worker Sprint 5-6): carga muerta a mitad queda atascada. Mínimo: acción admin `/cargas/{id}/expirar` interim.
- `valor_crudo` del parser NO se propaga a `CargaBancaria.errores_detalle` (regla 7: el Financiero lo necesita). Propagarlo.
- Documentar: el mes se abre ANTES de su 1ª carga (migración crea meses históricos).
- Retirar el placeholder `test_real_mongo_marker` (ya cubierto por `test_transaccion_dedup.py`).

## Proceso — merge pre-gate
Aceptado como excepción única registrada (contención: solo staging). Pero A-01 la habría atrapado el gate pre-merge — el costo ya se ve. La regla sigue intacta; cambiarla = CR. Alcance: BBVA/Global66 estaban en Sprint 2 (adelanto benigno — registrar versión del plan); pantalla de cargas + POST manual + reaper siguen abiertos.

## Camino al GO (~1 día): A-01 + M-01..M-04 → diff → re-verificación. Estimación ≥ 9.3.
