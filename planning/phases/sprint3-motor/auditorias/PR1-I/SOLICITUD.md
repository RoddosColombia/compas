# SOLICITUD DE AUDITORÍA — sprint3-motor PR1-I: motor del sugerido (§1.4.1, F-07)

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-07-21
**Docs contrato:** Spec §1.4 (PresupuestoLinea) + §1.4.1 (fórmula oficial), §2.4 (autoridad); CLAUDE.md reglas 1, 2, 3, 9, 10, 11
**Rama:** `feat/motor-sugerido` · commit `78a7fe8` · **SIN mergear — gate antes del merge**

> Anunciaste que auditarías la fórmula **celda a celda contra el Excel**. El núcleo es una función PURA de Decimal y su test dorado es el ejemplo resuelto del propio Spec.

## Qué hace
1. **`app/presupuesto/motor.py` (PURA, sin I/O)** — fórmula §1.4.1 exacta:
   `prom_3m = (E(M-1)+E(M-2)+E(M-3))/3` · `tendencia_mes = (E(M-1)−E(M-3))/2` · `sugerido = prom_3m + tendencia_mes + prom_3m × crec_pct`. Decimal + cuantización COP HALF_EVEN.
2. **Test dorado (celda a celda):** E=48M/61M/75M, crec 15% → `prom_3m=61.333.333,33`, `tendencia=13.500.000,00`, `sugerido=84.033.333,33` — el ejemplo del Spec, verificado en el motor Y **end-to-end por la API** (3 meses cerrados con transacciones que suman 48/61/75M → la línea sale 84.033.333,33).
3. **`PresupuestoLinea` (§1.4):** guarda los componentes para verificación; versionado con índice único parcial `{vigente:true}` (una vigente por mes/rubro, F-06); `monto_definido` null hasta aprobar; `compromisos_programados` fila INFORMATIVA (NO entra en la fórmula, regla 10); `ajustes` append-only; `modo_calculo` default `historico` (N-03).
4. **`POST /meses/{mes}/sugerido`** (RBAC `ciclo:abrir`, §2.4) + **`GET /meses/{mes}/presupuesto`** (`dashboard:leer`). E(i)=Σ valor de Transaccion EGRESO del rubro en el mes CERRADO i (solo estado 'cerrado'). Excluye rubros de sistema.

## Decisiones declaradas (auditar)
1. **n<3 meses cerrados (el Spec solo define n=3):** `historia_incompleta=true`; `prom_3m`=promedio de los disponibles; `tendencia=(reciente−antiguo)/(n−1)` —que en n=3 da /2, la fórmula oficial— y 0 si n<2; n=0 → todo 0. NO se adivina. En go-live todo es n=3 (may–jul cerrados+migrados). ¿De acuerdo con esta generalización?
2. **La generación NO emite evento de auditoría.** El catálogo cerrado no tiene 'sugerido.generado'; usar `presupuesto.acotado` sería mal uso (acotar = ajustar). El sugerido es un BORRADOR recomputable (monto_definido=null); los eventos reales son `presupuesto.acotado` (acotamiento) y `presupuesto.definido` (aprobación), que llegan en el siguiente incremento. ¿Aceptas, o exiges CR para `presupuesto.sugerido_generado`?
3. **Alcance:** este PR GENERA el sugerido (borrador). El **acotamiento** (monto_definido + ajustes) y la **aprobación** (→definido, transacción multi-doc de ~30 líneas + MesControl, regla 8) son el incremento siguiente. Rubros de sistema excluidos (no presupuestables); crec_pct global por ahora (per-rubro es refinamiento).
4. **`monto_sugerido` sin clamp a ≥0:** con tendencia muy negativa podría dar <0. No lo forcé (matemática fiel); ¿clamp a 0, o dejar el negativo visible para que el Financiero lo acote?

## Semántica preservada
Nada existente cambia (solo se agrega el router presupuesto). `compromisos_programados=0` (DeudaCuota llega en Sprint 5). Reglas de dinero/tiempo intactas; `crec_pct` usa el tipo `Money` para round-trip Decimal128 seguro.

## Evidencia local (EVIDENCIA.md: diff + salidas)
pytest **270 passed / 23 skipped** (16 nuevos: 8 motor puro + 8 endpoint). ruff check+format limpios. Greps 0. CI main verde previo.
