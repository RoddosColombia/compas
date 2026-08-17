# EVIDENCIA — FABS Incremento 2 (PR1, ronda I)

- **Rama:** `feat/fabs-inc2` · **Rango:** `229746f..1955cb9` · **Fecha:** 2026-08-17
- **Diff completo del backend:** `inc2-backend.diff` (en esta carpeta, 1857 líneas). Reproducible: `git diff 229746f..1955cb9 -- backend/`

## 1. Inventario de cambios (backend, `git diff --stat`)

```
 backend/app/audit/events.py           |   9 ++   (CR-CFO-1: cfo.consulta + cfo.respuesta, 62→64)
 backend/app/auth/permissions.py       |   4 +    (capacidad cfo:consultar)
 backend/app/cfo/agente/__init__.py    |   0
 backend/app/cfo/agente/cliente.py     |  95 ++    (wrapper Anthropic lazy + RespuestaLLM)
 backend/app/cfo/agente/loop.py        |  67 ++    (loop acotado modelo↔tool)
 backend/app/cfo/agente/modelos.py     |  35 ++    (RespuestaCFO/CifraPublicada/UsoLLM, strict)
 backend/app/cfo/agente/prompt.py      |  34 ++    (system prompt: nunca calcula, ni %)
 backend/app/cfo/agente/servicio.py    | 209 ++    (orquestador: verify/retry/abstención + auditoría + backstop)
 backend/app/cfo/agente/tools.py       |  75 ++    (3 tools solo-lectura + dispatcher cerrado)
 backend/app/cfo/agente/verificador.py | 178 ++    (cifra→evidencia — EL control)
 backend/app/cfo/calc/iva.py           |  14 ++    (fail-closed por periodicidad)
 backend/app/cfo/config.py             |  25 ++    (modelo/api_key/límites del loop)
 backend/app/cfo/router.py             |  37 ++    (POST /api/v1/cfo, doble barrera + RBAC)
 backend/app/main.py                   |  11 ++    (registro condicional del router por flag)
 14 files changed, 793 insertions(+)
```
(Los tests viven en `backend/tests/cfo/agente/` — ver §3.)

## 2. Regla del motor / flag-off (verificado)

```
$ git diff 229746f..1955cb9 -- backend/app/proyeccion/motor.py
(vacío — CERO diffs)

$ python -m ruff check app/cfo/
All checks passed!
```
- `main.py` monta el router SOLO dentro de `create_app()` bajo `if cfo_enabled()`. `anthropic` se importa perezoso dentro de `ClienteAnthropic.__init__`; `crear_cliente()` devuelve `None` sin key ⇒ el SDK ni se importa con el flag apagado.
- Test de flag-off: `test_flag_off_no_monta_router_en_app_routes` (crea la app real con `CFO_ENABLED` ausente y afirma que `/api/v1/cfo` NO está en las rutas).
- Aislamiento S1 extendido a `agente/` + `router.py`: no importan `app.domain.*` ni el driver de Mongo.

## 3. Tests (verde)

- **Suite backend completa:** `1009 passed / 95 skipped (requires_real_mongo) / 0 failed` con el módulo presente y el flag apagado.
- **`tests/cfo/`:** `74 passed`.
- **Batería adversarial del verificador** (`tests/cfo/agente/test_verificador.py`): `24 passed`. Cubre:
  - cifra correcta con evidencia pasa; monto inventado se atrapa; suma inventada se atrapa;
  - tolerancia ±$1; meses fuera de tolerancia falla; evidencia abstenida no respalda; **$0 falso se atrapa** vs **$0 legítimo con evidencia pasa**;
  - **formato wire real** (`704722003.00`, `36204698.10`, `4.20`) con y sin evidencia; **bare-digit** fabricado; años/fechas/cuenta no se marcan;
  - **porcentajes** (`25%`, `12,5 %`) siempre huérfanos.
- Los goldens (arnés de inc1) se corren en release; smoke en CI (presupuesto $30/mes, memoria fabs §D10).
- Todos los tests del agente usan el **cliente Anthropic MOCKEADO** (`ClienteFake`) ⇒ CI verde SIN `ANTHROPIC_API_KEY` ni red.

## 4. Cómo se construyó y auditó (trazabilidad)

Construido por **SDD** (subagente fresco por tarea + review de dos etapas por tarea + review final whole-branch en el modelo más capaz). Hallazgos REALES cazados por el gate y cerrados (todo en `.superpowers/sdd/2026-08-11-fabs-inc2-loop-agente/` — ledger + reports + paquetes de review):

- **T7 verificador — 2 rondas de fix:** el formato *wire* real de las tools es `NNN.dd` (2 decimales vía `money_str`), no el humano es-CO que asumió el plan → una cifra fabricada en dígitos pelados pasaba sin verificar. Cerrado con normalizador por semántica-de-separadores (verificado empíricamente contra 10 formatos). Además el implementer cazó un off-by-one en el skip meses/COP (point-containment → interval-overlap).
- **T10 servicio — 1 fix:** backstop de nivel superior para que `consultar` NUNCA reviente al caller (un read siempre devuelve `RespuestaCFO`).
- **T11 endpoint:** se usó el patrón real de auth de la repo; se cazó y actualizó el drift-guard `test_config_igual_a_la_matriz_canonica`; no-vacuidad probada mutando cada barrera.
- **Review final (opus):** *"Ready to merge — With fixes"*, **cero Critical de código**. 2 Important + 1 Minor cerrados y re-revisados limpios: (1) **porcentajes** ahora huérfanos (era un hueco real de fabricación); (2) huecos residuales documentados en código; (3) test guard cero.

## 5. Deferral vinculante (declarado, no oculto)

El verificador agrupa la evidencia por **unidad** (COP/meses), NO por **concepto**. Como caja e iva son ambos COP, una cifra REAL citada con etiqueta equivocada pasaría la verificación. **Exposición cero con el flag apagado**; documentado en el docstring de `verificar()`/`servicio.py`. La verificación *concept-aware* (citación estructurada) queda como **CR obligatorio ANTES de encender `CFO_ENABLED` (inc3)**.

## 6. Alcance / seguridad

- `ANTHROPIC_API_KEY` **solo** env var en Render (nunca en repo; gitleaks en CI). Se configura al arrancar inc3.
- Auditoría fail-soft (un read no se bloquea por un fallo de la BD de auditoría); catálogo cerrado (+2 vía CR-CFO-1); RBAC por dependencia (`cfo:consultar` → {financiero, directivo, admin}), `actor_id` = id real del usuario autenticado.
- La pregunta del usuario se guarda en `cfo.consulta.metadata.pregunta` (rastro forense; usuario interno tras auth). Minimización de PII se revisa si inc3 abre el canal a más gente.
