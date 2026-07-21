# CR-S3 — Gobernanza del inventario de secretos en el repo (condición del GO 9.2)

**Origen:** Kimi R-PR1 sprint2-cargas (2026-07-20): la excepción a la regla 12
(`docs/INVENTARIO-SECRETOS.xlsx` con valores reales, allowlist de gitleaks) entró al
baseline **sin CR propia** (polizón en el fix commit `f9985fe`). El GO quedó
condicionado a esta CR. **Plazo: esta semana.**

## Decisión que se formaliza
El repo privado `RoddosColombia/compas` contiene `docs/INVENTARIO-SECRETOS.xlsx` con
los valores reales de los secretos de COMPAS (decisión CEO 2026-07-20, motivada por el
principio rector: una sola fuente para un equipo de 1-2 personas, sin fricción).

## (a) Alcance exacto — VERIFICADO
`.gitleaks.toml` → `[allowlist] paths = ['''docs/INVENTARIO-SECRETOS\.xlsx''']` —
**path exacto, no patrón de carpeta**. Todas las demás reglas de gitleaks siguen
activas y bloqueando (probado adversarialmente: PR #20, run `29797947548`).

## (b) Regla dura de rotación
**ANTES de cualquier ampliación de exposición o membresía se rota TODO el contenido
del inventario**: hacer público el repo (prohibido sin revisión), añadir un colaborador,
conectar una integración con acceso al repo (CI de terceros, apps de GitHub con scope
repo), o mover el archivo. Sin rotación previa → la ampliación NO se hace.

## (c) Alternativas evaluadas
| Opción | Evaluación |
|---|---|
| AWS SSM/Secrets Manager | Aplaza a cuando exista la cuenta IAM de COMPAS (bloque S3/DISP-02). Candidata natural en go-live. |
| Doppler (free) | Servicio adicional + dependencia externa para 2 usuarios; fricción > beneficio hoy. |
| SOPS/age (cifrado en repo) | La mejor relación costo/beneficio a corto plazo; exige gestionar la clave age fuera del repo (gestor personal del CEO). |
| **Statu quo (xlsx en repo privado)** | **Aceptado como interim** por decisión CEO: riesgo acotado (credenciales solo-COMPAS, F-19/F-27; repo de 2 personas; bloqueo C3 activo para todo lo demás). |

**Compromiso:** migrar el inventario a **AWS Secrets Manager o SOPS/age en el go-live**
(junto con DISP-01/02, cuando se endurece todo lo demás). Hasta entonces aplica (b).

## (d) Acceso
Las mismas 2 personas de B3 (Andrés + Iván; hoy operativamente solo Andrés). Revisión
obligatoria de esta CR al añadir CUALQUIER colaborador al repo (dispara (b)).

## Nota de proceso (lección registrada)
El cambio entró como polizón porque un `git add CLAUDE.md` arrastró una edición del
árbol de trabajo no relacionada con el fix. Regla operativa para Claude Code: **revisar
el diff staged completo antes de cada commit de un PR crítico y declarar TODO cambio
de CLAUDE.md/gobernanza en la SOLICITUD del gate.**

---
**Firma CEO:** ☐ Aprobada · Fecha: ________ · Se folda al re-baseline v1.1.3 (con E-9 y CR-S2).
