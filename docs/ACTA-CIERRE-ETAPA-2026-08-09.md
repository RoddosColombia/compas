# ACTA DE CIERRE DE ETAPA — COMPAS

**Fecha:** 2026-08-09
**Proyecto:** COMPAS — sistema predictivo de presupuesto y flujo de caja (RODDOS S.A.S.)
**Etapa cubierta:** post-épico E1 → Copys UX + Lote Dependabot + Endurecimiento G1 (parcial)
**Participantes:** Andrés (CEO/desarrollador) · Claude Code (ejecución) · Kimi (auditor adversarial)
**Rama:** `main` · commit al cierre: `38201e2`

---

## 1. Alcance y veredicto

Se declara **cerrada esta etapa de construcción**. COMPAS queda **funcionalmente completo** en lo
construido; los únicos pendientes son **prerrequisitos de go-live** (endurecimiento), documentados y
diferidos por decisión del CEO. Cada pieza crítica pasó gate Kimi ≥ 9.0 + GO del CEO.

## 2. Trabajo cerrado en esta etapa

| Ítem | Resultado | Evidencia |
|------|-----------|-----------|
| **Épico E1** (anclaje proyección↔ejecución) | ✅ 6/6 en prod | P1–P6, gates 9.3–9.6 |
| **FIX-I-2** (flake dedup cargas) | ✅ | squash `5d1c9e8`, gate 9.5 (I 7.5→II 9.5) |
| **Copys UX** (español de negocio) | ✅ | squash `ed574eb` (PR #76), **gate Kimi 9.5** |
| **Lote Dependabot #10–19** | ✅ 8 aplicados / 4 cerrados | **gate Kimi 9.5** (LOTE-I) |
| **GitHub Actions v7 + Node 22** | ✅ | squash `71d983e` (PR #79), CI-only |
| **Privatización del repo** | ✅ | `visibility=PRIVATE` confirmado |
| **Rotación de secretos** | ✅ | verificada en vivo (§4) |

### Detalle del lote Dependabot
- **Aplicados (8):** fastapi 0.141.1 · uvicorn 0.52.1 · sentry-sdk ≥2.66.1 · APScheduler 3.11.3 ·
  lucide-react 1.29 · @types/node 26 · jsdom 29.1.1 (PR manual #77) · typescript 7.0.2 (PR manual #78).
- **Cerrados con causa (4):** cryptography (obsoleto: main ya en 50.0.0 por CVE) · biome 2.x
  (major disruptivo, dev-only; se mantiene 1.9.4) · #18/#19 (reemplazados por PR manual).
- **Manuales por incompatibilidad real:** jsdom (30 exige Node ≥22; CI corre Node 20 → se fijó 29.1.1) ·
  typescript (TS7 elimina `baseUrl`; se quitó, `paths` relativo resuelve el alias `@/`).

## 3. Estado del catálogo de calidad (DoD, Spec §5)

- **Cumplidos:** #6 audit-log inmutable · #8 CI (pip-audit/gitleaks/Dependabot) · #11 auth endurecida ·
  #12 cabeceras de seguridad.
- **Módulo IVA (#5):** facturas reales **cargadas y en ejecución** (CEO 2026-08-09); pendiente el
  cierre formal "reproduce el cuatrimestre May–Ago 2026" para marcar Cumplido.
- **Pendientes (go-live):** #1 RBAC negativo por rol · #3 ciclo presupuestal vs Excel · #4 migración
  histórica conciliada · #7 dashboard con cifras reales (M10) · #9 rendimiento · #10 restauración RTO.

## 4. Verificaciones al cierre

- **CI en `main`:** 7 jobs (backend, backend-real-mongo, frontend, runtime-imports, pip-audit,
  gitleaks, Vercel) en verde por PR. Suite frontend: vitest 248/248 · build · biome limpio.
  Suite backend: regresión completa verde.
- **Servicio en vivo** (`https://compas-api-von1.onrender.com`):
  - `/health` → `200 {"status":"ok"}`
  - `/api/v1/health/ready` → `200 {"status":"ready","mongo":"up","beanie":"ready"}`
    → **confirma conexión a Mongo con las credenciales ROTADAS**.

## 5. Endurecimiento G1 — estado y decisiones

| Paso G1 | Estado | Nota |
|---------|--------|------|
| Mini-lote Actions (v7 + Node 22) | ✅ Hecho | PR #79 |
| Privatizar repo | ✅ Hecho | corta la exposición del inventario de secretos |
| **Rotar secretos** | ✅ Hecho | verificado en vivo (§4). Necesario porque el repo estuvo público con `INVENTARIO-SECRETOS.xlsx` (valores reales) |
| **`backend` required check** | ⏳ **Diferido** | Regla clásica creada y guardada, pero **"Not enforced"**: org en plan **Free** no aplica branch protection **ni** rulesets en repo privado. **Decisión CEO: no cambiar de plan ahora.** Se activará al subir a GitHub Team en go-live. **Mitigación vigente:** gate blando — se verifica `backend` en verde antes de cada merge. |

## 6. Riesgos y deuda declarada (no bloqueante)

- **Enforcement de CI:** hoy **no hay bloqueo duro** de merge a `main` (=deploy). Mitigado con
  disciplina manual; cerrar con GitHub Team antes de operación con datos reales de alto volumen.
- **CI en Node 20 → 22:** ya subido a Node 22 LTS (Node 20 deprecado por GitHub).
- **Bajas de UX:** aria-labels con "umbral" (invisibles) · B-1 (scroll de tabla a resolución real) ·
  B-2 ("resta del presupuesto" plana vs Regla A por concepto).

## 7. Pendiente para go-live (fuera de esta etapa)

Sprints de datos reales / conciliación histórica / IVA cierre de cuatrimestre / UAT / deploy a
producción (tag `v1.0.0` + reviewer Iván) + subir a GitHub Team para el required-check. El **acta de
cierre de construcción definitiva** (paso a operación) la emite Kimi cuando G1 cierre por completo.

---

**Declaración:** a la fecha, la construcción de COMPAS está **funcionalmente completa y verificada**;
lo pendiente es endurecimiento de go-live, explícitamente diferido. Esta acta registra el estado a
este punto.

**Aprobación:** ______________________  (CEO — Andrés)  ·  Fecha: __________
