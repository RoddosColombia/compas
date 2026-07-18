# Guía de arranque — Construir COMPAS con Claude Code

**Para:** Andrés (CEO/Tech Lead) e Iván (par revisor) · 18-jul-2026
**Premisa:** los documentos v1.1.2 + CR-001 son el contrato; Claude Code es la mano de obra. Tu trabajo es dirigir sesión por sesión, verificar demos y firmar gates.

---

## Paso 0 — Instalar y autenticar (una vez, ~10 min)

1. Instalar Claude Code (instalador nativo, recomendado):
   - macOS/Linux: `curl -fsSL https://claude.ai/install.sh | bash`
   - Windows: PowerShell nativo o WSL (guía oficial: https://code.claude.com/docs/en/setup)
2. Verificar: `claude --version` y `claude doctor`
3. Autenticar: ejecutar `claude` la primera vez → OAuth con tu cuenta Claude (Pro/Max) o `ANTHROPIC_API_KEY`.
4. Instalar también: `git`, GitHub CLI (`gh auth login`), Node 22+ (para el frontend) y Python 3.12.

## Paso 1 — Crear el repo y sembrar el contrato (~15 min)

```bash
mkdir compas && cd compas && git init
mkdir -p docs backend frontend migrations
# Copiar a docs/: los 5 documentos v1.1.2 + CR-001 + Calendario DIAN
# Copiar a la raíz: CLAUDE.md (entregado) y render.yaml (entregado)
# Copiar a docs/: RUNBOOK-INFRA.md
gh repo create roddos/compas --private --source=. --push
```

**El orden importa:** `CLAUDE.md` en la raíz hace que cada sesión de Claude Code arranque conociendo las reglas innegociables sin que tengas que repetirlas.

**Clave — el código de SISMO:** ten el repo de SISMO clonado en una carpeta hermana (`../sismo`). Cuando le pidas a Claude Code portar auth/RBAC/audit/parsers, dile la ruta: puede leerla directamente.

## Paso 2 — Sprint 0 con Claude Code (días 1–3)

Abre `claude` dentro del repo y usa prompts de este estilo (uno por bloque de trabajo, no todo junto):

**Sesión 1 — esqueleto:**
> Lee docs/COMPAS_Spec_Tecnica_v1_1_2.docx y docs/COMPAS_STACK_v1_1_2.docx. Crea el esqueleto del backend FastAPI según el stack: estructura app/, config con Pydantic Settings, /health, conexión a Mongo con Beanie, y el arranque condicional del scheduler con RUN_SCHEDULER (regla 6 de CLAUDE.md). Luego el esqueleto del frontend con Vite+React+TS+Tailwind+shadcn. Tests mínimos verdes.

**Sesión 2 — portar de SISMO:**
> El repo de SISMO está en ../sismo. Porta a COMPAS los módulos de autenticación JWT (con las mejoras del Spec: token_version, logout con denylist, rotación de refresh con detección de reuso), el RBAC de 4 roles según la matriz del Spec §4.1, y el audit log append-only. Escribe el test de CI que verifica que update/remove sobre audit_log FALLA. Documenta en docs/PORTADO_DE_SISMO.md qué se trajo y qué se cambió (es entregable para Iván).

**Sesión 3 — CI/CD:**
> Crea los workflows de GitHub Actions: por PR → lint (ruff/Biome) + pytest + vitest + build + pip-audit + gitleaks (bloqueantes); merge a main → deploy a staging en Render; tag v* → deploy a production con environment protegido. Configura Dependabot.

**Sesión 4 (Sprint 0b) — dominio base:**
> Implementa según el data dictionary del Spec: Rubro (con semilla de los 5 grupos del Excel — están en el PRD M1), MesControl, Configuracion (carga la tabla CALENDARIO_DIAN de docs/Calendario_DIAN_2026.md), y MFA TOTP para admin. Todo con Pydantic strict y tests.

**Lo que Claude Code NO puede hacer solo (tú, en los dashboards, con RUNBOOK-INFRA.md en mano):** crear la database `compas` en Atlas, aplicar `render.yaml` en Render (Blueprints → New), el proyecto en Vercel, el DNS en Cloudflare, el IAM y buckets en AWS, los proyectos en Sentry/Better Stack, y cargar los secretos. Claude Code te puede ir dictando cada pantalla si le pides "guíame para ejecutar la sección 2 del RUNBOOK", y puede usar `gh` y `aws` CLI si las autenticas.

**Cierre del Sprint 0:** checklist §9 del RUNBOOK completo → Iván revisa el checklist de seguridad → **gate G1** (bloqueante).

## Paso 3 — El ritmo de cada sprint (semanas 2–10)

La receta que se repite:

1. **Arranca la sesión citando el contrato:** "Lee el PLAN v1.1.2, Sprint N, y el Spec. Implementa X con sus criterios de aceptación (US-XX)."
2. **Una sesión por entregable**, no por sprint completo. Sesiones cortas y enfocadas rinden más que una maratón.
3. **Pide los tests con el código, no después.** El DoD los exige; Claude Code los escribe bien si se lo pides desde el inicio.
4. **Revisa con Iván los PRs críticos** (auth, cargas, aprobación, cierre) — es su rol de par revisor.
5. **Demo con datos reales** al cierre del sprint (los extractos y el Excel congelado) → gate del sprint → siguiente.

Mapa rápido de sprints → prompts iniciales:
- **S1:** "Porta el parser de Bancolombia desde ../sismo al esquema canónico del Spec §1.5/1.6, con el fixture real anonimizado, deduplicación e US-03/US-09."
- **S2:** "Parsers BBVA y Global66 (moneda original), reglas de clasificación, y el script de mini-migración de las bases mar–jul del Excel congelado (docs/...xlsx de corte)."
- **S3:** "Motor del sugerido, fórmula exacta del Spec §1.4.1 con el ejemplo numérico como test. Demo en modo histórico contra agosto-2026."
- **S4:** "Vista Control + caja + conciliación + transacciones multi-documento + CR-001 (ExtractoMensual con el PDF de Global66 del proyecto como fixture)."
- **S5:** "Pagos de la semana + deudas + Capacidad de pago + SnapshotCaja en el worker + primera versión del dashboard."
- **S6a/S6b:** "Facturas ambos lados + IVA cuatrimestral" / "M10 ingresos + dashboard completo + job de archivado."
- **S7:** "Migración restante + conciliación formal + reporte de cierre + prueba de restore cronometrada + guion UAT US-01..10." → **tu gate G5 (ventana 48h)**.
- **S8:** tag v1.0.0 → Iván aprueba el deploy → go-live → double-run.

## Paso 4 — Los 3 hábitos que protegen el proyecto

1. **Nunca dejes que Claude Code "mejore" el alcance sin CR** — si en una sesión propone algo fuera de los docs, la respuesta es: "regístralo como propuesta de CR, no lo construyas". Ya vivimos esa lección con la auditoría.
2. **Commit pequeño y frecuente**; si una sesión se enreda, `git checkout .` y reintenta con un prompt más claro — es más barato que arreglar.
3. **`/clear` entre tareas distintas** dentro de Claude Code: contexto limpio = mejores resultados. CLAUDE.md se recarga solo.

## Pendientes externos (no bloquean el código)
- Memo RNBD firmado con el contador (prerrequisito del go-live, no del Sprint 0).
- Extracto reciente de Bancolombia y BBVA para validar que los layouts de SISMO v2 siguen vigentes.
