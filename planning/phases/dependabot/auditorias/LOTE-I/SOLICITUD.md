# SOLICITUD DE AUDITORÍA — LOTE DEPENDABOT (#10–19)

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-08-09 · **Área:** dependencias (backend runtime + frontend dev)
**Tipo:** gate ÚNICO del lote (retrospectivo), como pediste. Cada PR se mergeó uno por uno con CI verde; los 3 majors con GO del CEO + evidencia.

## Resumen

Lote Dependabot procesado con tu criterio: **uno por uno, CI verde por PR, nunca batch**; orden seguridad→runtime→dev-only; los majors con GO del CEO. **8 mergeados, 4 cerrados sin merge** (2 reemplazados por PR manual por incompatibilidad real).

## Tabla consolidada

| # | Paquete | de → a | Riesgo | Verificación | Estado |
|---|---------|--------|--------|--------------|--------|
| #14 | fastapi (backend) | 0.135.2 → **0.141.1** | Major-ish (0.137 breaking) | Changelog 0.136–0.140 revisado: 0.137 `router.routes`→árbol; **no iteramos `.routes`** (solo `include_router`). Suite backend completa verde. | ✅ merged 36bbbac (GO CEO) |
| #10 | uvicorn[standard] | 0.44 → **0.52.1** | Runtime servidor | CI backend + runtime-imports + deploy. | ✅ merged b806073 |
| #16 | sentry-sdk | <3.0,≥2.0 → **≥2.66.1,<3.0** | Piso menor | `init`/`capture_exception` estables 2.x. CI backend. | ✅ merged e664070 |
| #13 | apscheduler | 3.11.2 → **3.11.3** | Patch | CI backend. | ✅ merged 12493c6 |
| #12 | lucide-react (front) | 0.468 → **1.29** | **MAJOR** | build/tsc valida 21 iconos exportados (incl. BarChart3); vitest 248; **captura antes/después idéntica** (ver §capturas). El 1.0 solo quitó brand icons (no usamos). | ✅ merged 7ea7f29 (GO CEO) |
| #17 | @types/node (front) | 22 → **26** | Dev tipos | build/tsc verde. | ✅ merged 4ab8845 |
| #77 | jsdom (front) | 25 → **29.1.1** | Dev (test env) | **PR MANUAL**: dependabot #19 re-resolvió a jsdom 30, que exige Node≥22 y **rompe en el CI (Node 20)** con `markAsUncloneable is not a function`. jsdom 29.1.1 soporta Node 20. vitest 248 en Node 20. | ✅ merged f1a119c (reemplaza #19) |
| #78 | typescript (front) | 5.9 → **7.0.2** | **MAJOR** | **PR MANUAL**: TS 7 elimina `baseUrl` (TS5102). Quitado; `paths` relativo resuelve el alias `@/` (459 imports). build (tsc7+vite) + vitest 248 + biome. | ✅ merged 4b26437 (GO CEO, reemplaza #18) |
| #11 | cryptography (backend) | 48 → 49 | Seguridad | **OBSOLETO**: main ya en **50.0.0** (pin de emergencia CVE 2026-08-03). Bumpear a 49 sería downgrade. | ⛔ cerrado |
| #15 | biome (front) | 1.9.4 → 2.x | **MAJOR** dev | **SALTADO** (GO CEO): major disruptivo (config schema roto, reformatea 29 archivos, 5-6 lint nuevos) y el `biome migrate` automático convierte `recommended:true`→`preset:none` (**apaga el linter en silencio**). Dev-only, 1.9.4 funciona. Major ignorado en dependabot. | ⛔ cerrado |
| #19 | jsdom | → 30 | — | Reemplazado por #77 (incompat Node 20). | ⛔ cerrado |
| #18 | typescript | solo versión | — | Reemplazado por #78 (faltaba quitar baseUrl). | ⛔ cerrado |

## Puntos a auditar

1. ¿La decisión de **cryptography** (no downgradear a 49; main ya en 50) es correcta?
2. ¿El manejo de **jsdom** (manual a 29 por el pin Node 20 del CI, en vez de forzar 30) es sólido? ¿Deberíamos además subir el Node del CI (hoy 20, deprecado por GitHub)?
3. ¿El fix de **TS 7** (quitar `baseUrl`, `paths` relativo) es correcto y suficiente?
4. ¿**biome** bien saltado, o querrías la migración completa en algún momento?
5. **Fuera de alcance:** #7/#8/#9 (GitHub Actions: setup-python/checkout/setup-node) quedaron sin tocar — ¿los incluimos en un segundo lote?

## Evidencia

Ver `EVIDENCIA.md` (CI por PR, greps, capturas lucide) y la tabla del tracker (fila DEPB-LOTE).
