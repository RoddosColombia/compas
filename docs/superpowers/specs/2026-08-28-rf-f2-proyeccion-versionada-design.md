# RF-F2 — Serie de proyección versionada (diseño)

| | |
|---|---|
| **Historia** | RF-F2 (COMPAS 2.0, must) · Fundacional §2/§3 |
| **Fecha** | 2026-08-28 |
| **Estado** | diseño aprobado por el CEO (chat 2026-08-28); pendiente construcción TDD |
| **Anti-principio** | el motor `proyeccion/motor.py` NO se toca; golden-master de 176 meses verde |

## 1 · Contexto y hallazgo

La Fundacional describe RF-F2 como dos mitades:
1. **La costura** — `Ajuste.rubro_id` entra en el cálculo; el presupuesto aprobado manda
   ≤ mes en ejecución, el motor paramétrico manda hacia adelante (autoridad por tramo D-2).
2. **La serie versionada** — cada aprobación de mes produce una versión inmutable; las
   vistas muestran serie nueva, anterior y diferencia; las alertas comparan contra la
   última aprobada.

**El mapeo del código (2026-08-28) encontró que la mitad 1 YA existe** como la capa **E1
de anclaje**:
- `presupuesto/service.py::aprobar_presupuesto` fija `PresupuestoLinea.monto_definido` por
  rubro.
- `proyeccion/ejecucion/loader.py::cargar_anclas` lo lee **por `rubro_id`**; `ejecucion/
  service.py::anclar` aplica la autoridad por tramo (CERRADO→real, EN_EJECUCIÓN/
  PRESUPUESTO→presupuesto, futuro sin presupuesto→motor), todo vía `reacumular` (aditivo,
  motor intacto). Wiring en `proyeccion/service.py::_resultado_con`.

**Lo que falta, y es el alcance de RF-F2, es la mitad 2: versionar la serie.** Hoy la
proyección es 100% en vivo/sin estado — no existe ninguna entidad de versión.

## 2 · Alcance

**Dentro (RF-F2):**
- Entidad inmutable `ProyeccionVersion`.
- Snapshot de la serie base al aprobar el presupuesto (post-commit, serie completa).
- Endpoint de la última versión + endpoint de diff (piso y valles) contra la proyección actual.
- UI en Proyecciones: overlay de la serie anterior + callout de diferencia (piso, valles).

**Fuera (respeta el contrato):**
- **Alertas de valle** nuevo/más profundo vs. aprobada → **RF-F3** (no RF-F2).
- **Versionado de líneas de presupuesto** → NO se toca. §3: «Ningún otro objeto cambia su
  ciclo de vida». (Ver §7, deriva doc-vs-código.)
- El motor y el modelo de datos existentes no se rediseñan.

## 3 · Decisiones (CEO 2026-08-28)

- **Cuándo/cómo se congela:** post-commit de la aprobación, calculando la proyección base a
  horizonte completo (no dentro de la transacción; el cálculo es pesado y lee muchas
  colecciones). Best-effort con backfill idempotente.
- **Qué se guarda:** la serie serializada COMPLETA (lo que produce `_serializar`: ~23
  campos + los meses del horizonte).

## 4 · Entidad `ProyeccionVersion` (`backend/app/domain/proyeccion_version.py`)

Modelada en el patrón probado de `PresupuestoLinea` (vigente + historia append-only):

| Campo | Tipo | Nota |
|---|---|---|
| `version` | int | secuencia global monótona (1, 2, 3…) |
| `vigente` | bool | exactamente una `True` = la última aprobada |
| `mes_aprobado` | str `YYYY-MM-01` | qué aprobación la creó (trazabilidad) |
| `escenario` | str | `"base"` |
| `horizonte_meses` | int | horizonte completo del snapshot |
| `serie` | dict | JSON completo de `_serializar` (Decimales como string, regla 1) |
| `piso_caja` | str | atajo para el diff (Decimal→string) |
| `mes_mas_ajustado` | str | mes del piso |
| `valles` | list[dict] | snapshot de `detectar_valles` |
| `caja_minima` | str | umbral con el que se calculó |
| `creado_por` | str | usuario que aprobó |
| `creado_at` | datetime | `now_utc` |

Índices: único `(version)`; **parcial único `vigente=True`** (una sola vigente). Inmutable:
al aprobar, la versión anterior solo cambia el puntero `vigente→False` — su `serie` nunca se
sobrescribe. Registrada en `DOMAIN_DOCUMENTS`.

## 5 · Servicio y hook

`backend/app/proyeccion/versionado.py` (nuevo):
- `snapshot_version(*, mes_aprobado, usuario_id) -> ProyeccionVersion`: corre
  `proyectar_vigente(escenario base, horizonte completo)`, serializa, calcula piso/valles,
  marca la anterior `vigente=False` e inserta la nueva `vigente=True` con `version=max+1`.
  Idempotente para backfill (si la última vigente ya corresponde a este `mes_aprobado` y
  serie, no duplica — o se fuerza con `--backfill`).
- `version_vigente() -> ProyeccionVersion | None`.
- `diff_contra_vigente(actual) -> dict`: `{piso: {anterior, actual, delta}, mes_mas_ajustado:
  {anterior, actual}, valles: {…}}` — todo Decimal en backend.

Hook en `aprobar_presupuesto` (o su router, junto a la auditoría post-commit): tras el
commit + emit_audit, llama `snapshot_version(...)`. **Best-effort:** si falla, se registra y
se reporta, pero NO revierte la aprobación (la versión es derivada/recreable). Backfill:
`migrations/…_backfill_proyeccion_version.py` recrea la vigente si faltara.

## 6 · API y UI

- `GET /api/v1/proyeccion/version` → la última vigente (o `{disponible:false}` si no hay).
  RBAC `dashboard:leer`.
- `GET /api/v1/proyeccion/version/diff` → `diff_contra_vigente(proyeccion actual)`. RBAC
  `dashboard:leer`.
- **UI** (`ProyeccionPage`): 2ª query a la versión; se pasa `serieAnterior` + `diff` al chart
  (`ComposicionCaja`, overlay punteado «aprobado anterior») y un callout «vs. última
  aprobación: piso Δ, valles». Reusa `formatDelta` y el plumbing de `meses_anclados`.

## 7 · Testing y seguridad

- TDD backend (mongomock + real-mongo para el índice parcial): entidad; `snapshot_version`
  (flip vigente, secuencia, idempotencia); `diff_contra_vigente` (puro); endpoints (RBAC,
  vacío); **test de que `aprobar_presupuesto` deja una versión vigente**.
- Frontend: test del overlay/callout (serie anterior + diff).
- **Golden-master del motor sigue verde** — RF-F2 solo lee `_serializar`; el motor no cambia.
- Gate-waiver (Kimi fuera) + GO CEO; auditoría Kimi retroactiva pendiente.

## 8 · Deriva doc-vs-código anotada (no se arregla)

`backend/app/domain/presupuesto.py` (docstring) dice que las aprobaciones «generan versión
nueva», pero `aprobar_presupuesto` muta la línea vigente en sitio sin subir
`PresupuestoLinea.version`. **Se deja como está** (arreglarlo cambiaría el ciclo de vida del
presupuesto, contra §3). Se añade una nota en el código para que nadie lo «corrija» al ver
RF-F2. La entidad versionada nueva es solo para la PROYECCIÓN.
