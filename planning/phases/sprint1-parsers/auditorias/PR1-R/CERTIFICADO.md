# CERTIFICADO KIMI — sprint1-parsers · R-PR1

**Veredicto:** ✅ **GO — 9.3 / 10** (umbral ≥ 9.0). Fecha: 2026-07-20.
**Merge del fix `375bdae` autorizado.** 5/5 hallazgos cerrados con implementación correcta y tests contra Mongo real.

| Ítem | Cierre |
|---|---|
| **A-01** (Alta) huella sin discriminador | Ordinal de ocurrencia por archivo (`…\|1`, `…\|2`). Tests: 2 cuotas idénticas → nuevas=2; solape A[X,X]+B[X,X,Z] → nuevas=1, dup=2. Robusto al reordenamiento; el residual falla hacia **duplicación visible, nunca hacia pérdida** — dirección correcta. |
| **M-01** año del reloj | Fecha futura → año anterior. Test de frontera dic/ene ✓. (Si algún día cargan extractos de años anteriores, volver al encabezado del extracto.) |
| **M-02** transacción | **Refutación aceptada:** probaron contra Mongo real que la sugerencia (catch-and-commit tras dup-key) no funciona (aborta, TransientTransactionError) e implementaron algo más robusto: pre-filtro + insert solo-nuevos + carga.save en `with_transaction` con retry. TOCTOU cubierto por índice único + re-carga. Regla 8 sin CR. |
| **M-03** N+1 | Cache `dict[mes, MesControl]` ✓ |
| **M-04** original no preservado | Regla dura (sin S3/dir → `OriginalNoPreservableError`); interim copia local. **Ojo:** en Render el disco es efímero → el interim es solo puente; vigilar que el bloque C (S3) no se retrase. |

Bajas: `valor_crudo` propagado con test ✓; placeholder retirado ✓. Salidas: 212 local, 13 real-mongo, ruff limpio.

**Nota de proceso (Kimi):** la refutación de M-02 es el intercambio que debe dar una auditoría seria — el equipo probó empíricamente que la corrección sugerida no funcionaba y propuso una mejor. Aceptada y registrada.

## Pendientes para la completitud del Sprint 1 (no bloquean el GO del backend)
- Pantalla de cargas + POST manual (`MAN-`+ULID).
- Fixtures reales anonimizados (S1-01) + export Global66 **.xlsx** para el FX real.
- En paralelo: bloque C del CEO para cerrar el Gate G1.
