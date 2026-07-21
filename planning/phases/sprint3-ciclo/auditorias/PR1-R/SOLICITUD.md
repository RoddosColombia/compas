# SOLICITUD DE AUDITORÍA — sprint3-ciclo PR1-R: fixes de I-PR1 (8.8 → re-auditoría)

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-07-21
**Ronda previa:** I-PR1 = 8.8 (1 Media semántica + 3 Bajas). **Fix commit:** `8f68158` sobre `274f47e` (rama `feat/ciclo-abrir-mes`, SIN mergear).

## Resolución por hallazgo

| # | Hallazgo | Corrección | Evidencia |
|---|---|---|---|
| **M-1** | `saldo_inicial_caja` como input libre (falla silenciosa de caja) | **Derivado del consolidado bancario del predecesor** (Σ `saldos_banco`); input obligatorio SOLO para el primer mes de la historia; digitarlo con predecesor → **422** con mensaje que remite a `ciclo:config`+step-up; predecesor sin consolidado → **422 explícito** (regla 7: no se adivina 0); **ciclo secuencial** (saltar meses → 422 con el mes esperado). `mes.creado` lleva `saldo_derivado: true/false` | `test_arrastra_saldo_del_consolidado_anterior` (N+1 → saldo == consolidado de N, exactamente tu test), `test_saldo_explicito_con_predecesor_422`, `test_primer_mes_sin_saldo_422`, `test_predecesor_sin_saldos_banco_422`, `test_mes_no_contiguo_422` |
| **B-1** | Drift runtime/dev sin detección | Job CI **`runtime-imports`**: `pip install -r requirements.txt` (solo runtime, como Render) + `create_app()` (monta todos los routers → el chequeo multipart de FastAPI dispara ahí) | `.github/workflows/ci.yml` |
| **B-2** | Rechazo de `manual` en saldos sin test | `test_manual_en_saldos_422` | test |
| B-3 | GET /meses sin paginación | Nota futura aceptada (selector; se pagina cuando el histórico crezca) | — |

## Decisión adicional declarada (parte de M-1)
**Contigüidad estricta**: con historia existente, el único mes abrible es `max(mes)+1`. Sin ella, saltar un mes reabriría la puerta al saldo digitado (el hueco no tiene predecesor) y burlaría F-14. Trade-off: no se pueden abrir meses retroactivos por API — la mini-migración histórica (S2-02) los creará por script, como ya preveía tu nota de I-PR1 sprint1 ("el script de migración crea los meses históricos directamente").

## Nota sobre el "consolidado"
Hoy deriva de los `saldos_banco` reportados del predecesor (lo último consolidado conocido). Cuando exista el flujo de **cierre** (Sprint 4), el cierre FIJARÁ ese consolidado formalmente (F-14) y esta derivación leerá el valor congelado — misma semántica, fuente más fuerte. Declarado para que quede en actas.

## Evidencia local (EVIDENCIA.md: diff + salidas)
pytest: **254 passed / 23 skipped** (16 en ciclo, +6 nuevos) · ruff check + format limpios · greps 0.
