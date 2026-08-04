# CR-WAVA-2 — Hook estado-dependiente de clasificación de depósitos Wava

**Fecha:** 2026-08-03 · **Decisión:** Andrés (CEO) + Kimi (arquitecto) · **Rama:** `feat/cr-wava-2`
**Relacionado:** `docs/COMPAS_IPLAN_CR-WAVA.md` (§5/§8.8, regla C3 que quedó omitida por falta del patrón),
`docs/NOTA_Transito_Wava_Julio_2026.md`, `backend/app/cierre/transito.py`.

## Problema (una oración)

Cuando los settlements de Wava aterrizan en agosto, deben reconocerse como **llegada del tránsito
declarado en el cierre de julio** (rubro `Tránsito Wava mes anterior`, fuera de `ingreso_real`) hasta
agotar los $37.280.415 declarados — no como recaudo de agosto — y el sobrante como recaudo normal.

## Contexto

- El cierre de julio declara `transito_wava = 37.280.415` (CR-WAVA §3, ya en producción).
- `transito_remanente(mes)` (`transito.py:68`) ya deriva el remanente vivo = `max(0, declarado − Σ llegadas)`.
- La clasificación en la carga elige rubro en `cargas/service.py:241` vía `elegir_regla`; si existe una regla
  activa `"Recibido de" → Recaudo`, un depósito Wava caería a **Recaudo** sin este hook.
- El rubro tránsito es `es_sistema=True` → ninguna `ReglaClasificacion` puede apuntarle (guard P0-1). Por eso
  el **hook es la única vía automática** hacia tránsito; no compite con el motor de reglas.

## Diseño

### Unidad nueva en `backend/app/cierre/transito.py`

- `PATRONES_TRANSITO: tuple[str, ...] = ("recibido de wava",)` — patrones ya normalizados; match por
  *contains* sobre `normalizar_texto(descripcion)` (cubre "…wava technologie…").
- `es_transito_wava(descripcion: str) -> bool` — puro, reutiliza `normalizar_texto` (la MISMA de reglas, sin
  divergencia). `any(p in normalizar_texto(desc) for p in PATRONES_TRANSITO)`.
- `class AsignadorTransito` — helper con estado por corrida (una instancia por carga / por `aplicar_pendientes`):
  - `async def asigna(self, *, descripcion, mes, tipo_flujo, valor) -> bool`
  - Devuelve `True` **solo si**: `tipo_flujo is INGRESO` **y** `es_transito_wava(descripcion)` **y**
    `remanente[mes] > 0`.
  - **Cache + descuento en batch** (decisión CEO 2026-08-03): calcula `transito_remanente(mes)` una vez por
    mes (primer depósito Wava de ese mes) y le resta `valor` por cada depósito que manda a tránsito. Así el
    comportamiento dentro de un archivo == cargas secuenciales (el 2º depósito ve el remanente reducido por el
    1º) y nunca sobre-asigna a tránsito más que lo declarado.

### Los dos hooks (antes de `elegir_regla`)

1. **`cargas/service.py`** (loop de movimientos, antes de la línea 241): si `await asignador.asigna(...)` →
   `rubro_id = rubro_transito.id`, `regla_id = None` (sello de sistema); si no → flujo normal (`elegir_regla`
   → regla o `Por clasificar`). Se resuelve el rubro tránsito **una vez** por carga (lookup cacheado); si no
   existe, el asignador nunca dispara (fail-safe: sin rubro, sin hook).
2. **`reglas/service.py::aplicar_pendientes`** (antes de la línea 439): igual, sobre las tx en `Por clasificar`
   de meses abiertos. Necesita el `mes` string por tx → se extiende el lookup de `meses_abiertos` a un mapa
   `mes_id → mes`. Las tx enviadas a tránsito se sellan con `clasificada_por/at` (quién disparó el lote) y
   `regla_id = None`.

### Invariante de caja (idéntico a la trampa de CR-WAVA)

El depósito sube el saldo del banco (dato de conciliación), el remanente baja (la tx cuenta como llegada en
`_suma_llegadas_despues`), el total no cambia. `ingreso_real` excluye el rubro tránsito por `rubro_id` → el
recaudo NO se infla. Es reconocimiento del tránsito, no recaudo de agosto ni doble conteo.

## Comportamiento por estado (lo "estado-dependiente")

| Estado | Comportamiento del depósito Wava |
|--------|----------------------------------|
| Hay declaración y `remanente(mes) > 0` | → rubro **Tránsito Wava mes anterior** (descuenta remanente) |
| `remanente(mes) == 0` (ya agotado) | → flujo normal (`elegir_regla` → Recaudo) y **sí** cuenta en `ingreso_real` |
| Sin declaración previa (`_mc_prev_con_transito` = None) | → flujo normal siempre (Recaudo) |
| Descripción no-Wava ("Recibido de Éxito") | → intacto (flujo normal), el hook no dispara |

## Qué NO cambia

`motor.py` cero diffs · golden sin regenerar · catálogo de eventos congelado en 59 (no hay evento nuevo:
la clasificación a tránsito es un rubro, no un evento) · compuerta IVA intacta · reglas existentes intactas.

## Testing

**Unit (mongomock):**
- `es_transito_wava`: matchea "Recibido de WAVA Technologie", no matchea "Recibido de Éxito"/"Pago a Wava egreso".
- `AsignadorTransito`: INGRESO+patrón+remanente>0 → True y descuenta; segundo depósito que agota → False;
  EGRESO con patrón → False; remanente=0 → False; sin declaración → False.

**Real-mongo (CI, la red final — la carga usa `with_transaction`):**
1. `remanente>0` → carga con depósito Wava → tx en rubro tránsito; remanente baja, recaudo inmóvil, total
   invariante.
2. `remanente=0` (llegada previa agotó) → siguiente depósito Wava → Recaudo y **sí** en `ingreso_real`.
3. Sin declaración → depósito Wava → Recaudo siempre.
4. No-Wava ("Recibido de Éxito") → intacto.
5. Batch: dos depósitos Wava en un archivo que suman > remanente → el/los primeros a tránsito hasta agotar,
   el último a Recaudo (descuento en batch).
6. `aplicar_pendientes`: depósito Wava en `Por clasificar` con remanente>0 → reclasifica a tránsito.

## Fecha dura

Antes de la primera carga semanal de extractos de agosto (~7–9 ago, cuando aterrizan los settlements). Si no
llega a tiempo, los depósitos de julio se clasifican a mano contra el rubro tránsito (ya soportado por la
whitelist `es_rubro_clasificable`).
