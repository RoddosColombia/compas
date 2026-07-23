# SOLICITUD DE AUDITORÍA — sprint6-ajuste-caja · I-PR1: C4 ajuste diario de caja (código)

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-07-23
**Objeto:** PR `feat/c4-ajuste-caja` (gate de CÓDIGO). Construido con TDD tras tu GO
PLAN-I 9.3, incorporando tu Baja **B-1** (update atómico posicional).
**Docs contrato:** CLAUDE.md reglas 1, 2, 3, 4, 7, 9, 11; Spec §1.3; tu certificado
I-PLAN sprint6-ajuste-caja (9.3). **Base:** `main` con C1+C3 y deuda S4 saldada.
**Alcance:** SOLO C4 backend; cero cambios en motor/conciliación/cierre (0 líneas en
`_conciliar`/`_caja_libro`/motor §1.4.1) — C4 solo ALIMENTA la estructura que ya
consumen. Diff completo y salidas de tests en EVIDENCIA.md.

## Qué hace el PR (+~912 líneas; diff en EVIDENCIA.md)

**`PATCH /api/v1/meses/{mes}/saldos`** (`caja:reportar`, CR-S6): reporte/ajuste
diario de saldos por banco.
- **B-1 incorporada (tu preferida):** el upsert es un update ATÓMICO POSICIONAL por
  banco — `{"saldos_banco.$": ...}` para el banco existente; `$push` con filtro
  `{"saldos_banco.banco": {$ne: b}}` para el nuevo, y si el push matchea 0 (el banco
  apareció concurrente) reintenta como posicional (máx 3). NO hay read-modify-write
  de la lista → dos PATCH concurrentes sobre bancos distintos NO se pisan.
- **D2:** `fecha_reporte` `YYYY-MM-DD` en `[mc.mes, hoy(Bogotá)]` + no-retroceso por
  banco (fecha ≥ la vigente de ese banco; igualdad = corrección permitida).
- **D3:** solo mes `en_ejecucion` → 409 en los demás estados.
- **D4:** la respuesta incluye `conciliacion` reusando `conciliacion(mes)` sin
  cambios (misma función que el GET operativo → misma verdad).
- **D5/O1:** un evento `saldo_banco.reportado` por banco tocado con metadata
  `{banco, saldo_anterior→nuevo, fecha_reporte_anterior→nueva}`. Fail-closed:
  write→emit por banco; si el emit cae, se restaura ESE banco (posicional si existía,
  `$pull` si era nuevo) y propaga.
- **CR-S6:** catálogo 36→**37** (`saldo_banco.reportado`) + capacidad
  `caja:reportar` = {financiero, admin}. Tests de completitud y guardián al día.

## Puntos a auditar con lupa

1. B-1 — la atomicidad posicional (`_upsert_saldo`): ¿elimina el lost-update sin
   transacción, y el fallback push↔posicional cubre la carrera del banco nuevo?
2. O1 — compensación POR BANCO (`_restaurar`): banco existente → restaura previo;
   banco nuevo → `$pull`. El estado previo se captura ANTES de mutar (de `vigentes`).
3. D2 — no-retroceso y ventana `[mc.mes, hoy]`: comparación de strings YYYY-MM-DD
   (== orden cronológico); la corrección del mismo día pasa (igualdad).
4. Cero polizontes: el diff NO toca `_conciliar`/`_caja_libro`/motor/cierre;
   `conciliacion()` se reusa tal cual.
5. Regla 1: saldo como string en API (strict rechaza el number); Decimal128 al
   escribir raw, Money al releer.

## Evidencia local (EVIDENCIA.md)

Diff real de `app/caja/service.py`, `app/caja/router.py`, deltas de
`events.py`/`permissions.py`/`api/v1/__init__.py`, y los 2 archivos de test. `pytest
-q` verde (guardas mongomock + catálogo/permisos; los 12 real-mongo corren en el CI
del PR: upsert, D4, auditoría por banco, O1, B-1 concurrencia, D6). `ruff
check`/`format`: limpios. Greps del protocolo: 0.

## Pregunta al auditor

¿La implementación de C4 (upsert atómico posicional B-1, compensación O1 por banco,
guardas D2/D3, conciliación al instante D4 reusando la función certificada, CR-S6)
implementa fielmente tu PLAN sin tocar semántica financiera, para mergear a `main`?
