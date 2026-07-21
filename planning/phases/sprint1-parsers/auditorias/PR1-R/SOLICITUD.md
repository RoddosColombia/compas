# SOLICITUD DE AUDITORÍA — sprint1-parsers PR1-R: fixes de I-PR1 (8.0 → re-auditoría)

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-07-20
**Ronda previa:** I-PR1 = **8.0 / 10** (NO-GO): 1 Alta (A-01) + 4 Medias + bajas.
**Rama:** `fix/kimi-pr1r-parsers-carga` · **Fix commit:** `375bdae` (sobre `0a3f1fa`)
**Docs:** Spec §1.5/§1.6/§2.3; CLAUDE.md reglas 1,5,7,8,11

## Resolución de hallazgos

| # | Hallazgo | Corrección aplicada | Evidencia |
|---|---|---|---|
| **A-01** (Alta) | Huella sin discriminador colapsa idénticos legítimos | `derivar_id_banco` añade **ordinal de ocurrencia por archivo** (`…\|1`, `…\|2`); el servicio cuenta ocurrencias por `(fecha,tipo,desc,monto)` en orden de fila | tests real-mongo: `test_identicos_en_un_archivo_no_colapsan` (2 cuotas iguales → nuevas=2) y `test_solape_dedup_conserva_identicos` (A[X,X] + B[X,X,Z] → nuevas=1, dup=2) |
| **M-01** | Año desde el reloj (bug frontera dic/ene) | d/m sin año: si el año actual pone la fecha en el **futuro**, se usa el año anterior | `test_diciembre_leido_en_enero_no_salta_al_futuro` (31/12 leído el 2-ene-2027 → 2026-12-31) |
| **M-02** | Finalización sin transacción (regla 8) | **Transacción multi-doc real**: pre-filtro de duplicados con la sesión + `insert_many(session)` de solo-nuevos + `carga.save(session)`, todo en `with_transaction` (retry ante transitorios) | ver "Sobre M-02" abajo + tests de carga verdes contra Mongo real |
| **M-03** | N+1 en `MesControl.find_one` | Cache `dict[mes, MesControl]` (1 lookup por mes, no por fila) | `service.py` (mes_cache) |
| **M-04** | `archivo_s3_key` opcional → original no re-procesable | **Regla dura**: sin S3 ni `dir_originales` → `OriginalNoPreservableError`. Interim: copia local del original (`local://<hash>.<ext>`) hasta S3 (bloque C) | `test_sin_preservacion_rechaza`, `test_preserva_original_local` |
| Baja | `valor_crudo` no llega al Financiero | Propagado del parser a `CargaBancaria.errores_detalle` (regla 7) | `test_valor_crudo_se_propaga` (celda "N/A" → errores_detalle[0].valor_crudo=="N/A") |
| Baja | Placeholder `test_real_mongo_marker` | Retirado (cubierto por `test_transaccion_dedup.py`) | diff |

## Sobre M-02 (corrección técnica, con evidencia)
La afirmación "dentro de una transacción cabe `insertMany ordered=False` + capturar `BulkWriteError` + commit" **no funciona**: se probó contra Mongo real y un dup-key (código 11000) marca la transacción como `TransientTransactionError` y la aborta (`nInserted=0`, el doc nuevo NO se persiste). Capturar el error no permite commitear.

La forma correcta —implementada— satisface **ambas** reglas: **pre-filtrar** los duplicados dentro de la sesión y luego `insert_many` **solo de los nuevos** (sin dups → no aborta) + el update de la carga, todo en la misma transacción. El ordinal de A-01 hace únicos los ids dentro del archivo, así que el único duplicado posible es cross-archivo, que el pre-filtro detecta; `with_transaction` reintenta ante el TOCTOU con una carga concurrente. Regla 8 cumplida sin CR.

## Semántica preservada
Sin cambios en histórico/audit/dinero. F-02 intacto. La dedup de solape sigue funcionando (mismo orden de fila → mismo ordinal).

## Puntos a auditar con lupa
1. **A-01**: ¿el ordinal por orden de fila es robusto? Riesgo residual: si un banco reordena filas entre dos exports del mismo periodo, el solape podría no alinear ordinales. Para RODDOS los exports son estables en orden; documentado.
2. **M-02**: ¿aceptas el pre-filtro + transacción como cumplimiento de la regla 8? ¿Ves un hueco en el TOCTOU (mitigado por índice único + retry)?
3. **M-04**: la copia local es interim; la regla dura bloquea cargas sin destino. ¿Suficiente hasta S3?

## Pendientes declarados (no bloqueantes de este PR)
- **CR de A2 (análisis de colisión sobre fixtures reales):** pendiente de los fixtures congelados (S1-01). El ordinal ya garantiza **correctitud** independiente de la frecuencia de colisión; el análisis solo la cuantificará.
- **Alcance del plan:** BBVA/Global66 estaban en Sprint 2 (adelanto benigno) — registrado.
- **Reaper de cargas** (procesando stale → fallida): llega con el worker (Sprint 5-6); interim futuro `/cargas/{id}/expirar`.
- Pantalla de cargas + POST manual (MAN-+ULID): fuera de este PR.

## Evidencia local (ver EVIDENCIA.md — diff real + salidas)
- pytest: **212 passed / 23 skipped** (local) · **13 passed** @requires_real_mongo (carga + dedup).
- ruff: All checks passed. · Protocolo: r1/journal-entries/estado-pending = 0.
