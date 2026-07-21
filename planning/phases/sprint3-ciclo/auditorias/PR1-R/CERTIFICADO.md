# CERTIFICADO KIMI — sprint3-ciclo · R-PR1

**Veredicto:** ✅ **GO — 9.4 / 10.** Fecha: 2026-07-21. **Merge de `8f68158` autorizado.**

3/3 hallazgos cerrados con implementación correcta y tests exactos:

| Ítem | Cierre |
|---|---|
| **M-1** | Contrato F-14/US-01 completo: sin historia → input obligatorio; con predecesor → deriva del consolidado (Σ saldos_banco); digitado con predecesor → 422 (remite a ciclo:config+step-up); sin consolidado → 422 explícito. **Contigüidad secuencial** cierra el hueco (saltar meses burlaba F-14). Test exacto N+1 → Σ bancos de N. `mes.creado` con `saldo_derivado` para el forense. |
| **B-1** | Job CI `runtime-imports` (solo requirements.txt + create_app) — la clase exacta de drift del incidente python-multipart. |
| **B-2** | `test_manual_en_saldos_422` ✓ |

Salidas: 254 passed, ruff check+format limpios.

**En actas (semántica del consolidado):** hoy deriva de los `saldos_banco` reportados del predecesor; cuando exista el cierre (Sprint 4), este fijará formalmente el consolidado (F-14) y la derivación leerá el valor congelado — misma semántica, fuente más fuerte.

**Siguiente (aviso del auditor):** motor del sugerido (Spec §1.4.1) — auditará la fórmula celda a celda contra el Excel (prom_3m + tendencia + prom_3m × crec_pct, solo meses cerrados, historia_incompleta marcada) y el versionado de PresupuestoLinea.
