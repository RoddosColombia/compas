# SOLICITUD DE AUDITORÍA — sprint0-auth-rbac-audit · R-PR1: audit base (re-presentación)

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-07-19
**Ronda:** R-PR1 (verificación de cierre) · **Previa:** R-PR1 8.8/10 NO-GO condicionado (6 Medias + 5 Bajas + 2 nits; H-01 refutada por tier M10)
**Rama:** `sprint0/sesion2-auth-rbac-audit` · **Nivel:** PR (código) — se adjunta **el diff de líneas cambiadas** + salidas
**Evidencia:** `EVIDENCIA-R-PR1.md` (diff `d08a395..288ce54` + pytest/ruff)

## Resolución de los hallazgos
| # | Sev | Hallazgo | Corrección aplicada |
|---|---|---|---|
| H-01 | Media | Script en Atlas Free/Flex | Guarda `_fail_if_unsupported` (sale y remite al RUNBOOK) + nota de tier M10+ en docstring y RUNBOOK §2 |
| H-02 | Media | updateUser sin `pwd` (rotación) | Rama de actualización ahora incluye `pwd`; docstring "roles Y contraseña" |
| H-03 | Media | Password por argv + `CHANGE_ME` | Se lee de `COMPAS_AUDIT_PWD`/`getpass`, sin default, mínimo 16; eliminado `CHANGE_ME` |
| H-04 | Media | strict rechaza str de evento (lecturas futuras) | `field_validator("evento", mode="before")` castea str→`AuditEvento`; strict intacto |
| H-05 | Media | timestamp naive en lecturas | `field_validator("timestamp")` rechaza naive; `create_client` usa `tz_aware=True` |
| H-06 | Media-Baja | test no probaba serialización str | `assert type(doc["evento"]) is str` |
| H-07 | Baja-Media | `metadata: dict` sin parametrizar | `dict[str, Any]` + nota BSON-able |
| Bajas/nits | Baja | app_env, exclude id, cache, CI, erratas | `app_env: Literal[...]`; quitado `exclude={"id"}`; conftest autouse `cache_clear`; nota CI required-check; "mongomock"→"mongomock_motor"; comentario del índice reconciliado; ref. de errata aclarada |

## Puntos a auditar con lupa
1. **H-04/H-05 validators:** ¿`_cast_evento` (before) + `_timestamp_aware` no rompen el path de escritura (que ya castea) y habilitan la lectura desde Mongo? ¿Algún borde con strict?
2. **H-02/H-03 script:** ¿la actualización con `pwd` + lectura por env/getpass sin default cierran la rotación y el secreto en claro?
3. **H-01 guarda:** ¿el `_fail_if_unsupported` cubre los mensajes reales de Atlas Free/Flex?

## Evidencia local
- `pytest`: **19 passed, 4 skipped**; `-m requires_real_mongo` → **4 failed** (no skip); `ruff`: limpio.
- Diff acotado a las líneas cambiadas en `EVIDENCIA-R-PR1.md` (no el paquete completo, como pediste).

## Pregunta al auditor
¿El diff cierra los 6 Medias + 5 Bajas + 2 nits para autorizar el merge de PR-1 (estimación previa ≥ 9.4) y habilitar el gate de PR-2?
