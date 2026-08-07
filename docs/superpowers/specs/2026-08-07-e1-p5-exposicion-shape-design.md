# E1 · P5 — Exposición del shape en `GET /proyeccion`

**Fecha:** 2026-08-07 · **Épico:** E1 (Anclaje de la proyección a la ejecución) ·
**Plan padre:** `docs/COMPAS_PLAN_E1_Anclaje_a_la_Ejecucion.md` (pieza **P5**, §6) ·
**Spec de criterios:** `docs/COMPAS_SPEC_EJECUCION_E2_E1.md` (Parte V, **B13**) ·
**Precede:** P1–P4 (todos en prod; E1 activo) · **Sigue:** P6 (frontend).

## 1. Problema

Exponer en la respuesta de `GET /proyeccion` **el origen de cada cifra** para que la UI (P6)
pueda marcar qué es real, qué está en ejecución y qué es proyección, sin que el usuario tenga
que adivinar. En concreto, tres piezas de metadato que hoy el backend **ya conoce pero no
devuelve**:

1. **`meses_anclados`** — el régimen de cada mes anclado (`cerrado` / `cerrado_sospechoso` /
   `en_ejecucion` / `presupuesto`).
2. **`sin_mapear`** — rubros con movimiento real que no tienen concepto del motor (R-1/R-2
   parqueados); se reportan mientras el CEO no los reubique.
3. **Completitud del mes en curso (B13)** — hasta qué día está cargado el mes en ejecución y
   con qué fórmula se armó ("cargado hasta el día N").

Todo **aditivo**: sin romper el shape actual ni a los consumidores existentes.

## 2. Contrato (shape de respuesta)

Tres claves nuevas top-level en el dict que produce `_serializar` (compartido por
`GET /proyeccion`, `GET`+`POST /preview`, y demás endpoints que serializan la proyección):

```jsonc
{
  // ... todas las claves de hoy, byte-idénticas ...
  "meses_anclados": { "2026-07": "cerrado", "2026-08": "en_ejecucion" }, // {} si no hay anclaje
  "sin_mapear": ["Rubro sin concepto X"],                               // [] si nada
  "mes_en_curso": {                                                     // null si no hay mes en_ejecucion
    "mes": "2026-08",
    "cargado_hasta": "2026-08-06",
    "dia": 6,
    "formula": "ejecutado + max(0, definido - ejecutado) por concepto"
  }
}
```

- **`meses_anclados`**: `dict[str, str]`, clave `YYYY-MM`, valor ∈ el vocabulario ya pineado por
  `marcas_origen` (P4). Vacío `{}` cuando no hay anclaje.
- **`sin_mapear`**: `list[str]` de **nombres** de rubro, ordenada y deduplicada (unión sobre los
  meses con ejecutado). Vacía `[]` cuando todo mapea.
- **`mes_en_curso`**: objeto `{ mes, cargado_hasta, dia, formula }` o `null`. `cargado_hasta` es
  `YYYY-MM-DD` (regla 2: fecha estricta), `dia` es el entero del día, `formula` es texto constante
  que describe la Regla A (D-08). `null` cuando ningún mes del horizonte está `en_ejecucion`.

**Decisión de shape (CEO, 2026-08-07):** objeto rico para `mes_en_curso` (día + fecha completa +
fórmula legible) para que P6 muestre el aviso sin recalcular.

## 3. Diseño — de dónde sale cada dato

Principio: **no tocar el perímetro** que Kimi mantiene estable
(`anclar`/`lectura.py`/`reconciliacion.py`/`motor.py` = R0). Todo lo nuevo es aditivo y, donde
sea puro, testeable sin Mongo (patrón P4).

| Dato | Origen | Cómo |
|---|---|---|
| `meses_anclados` | `marcas_origen(anclas,…)` — **ya existe** (`guarda.py`, P4) | Hoy `_resultado_con` lo computa solo para loguear los sospechosos y **descarta** el dict. P5 deja de descartarlo y lo propaga. **Cero lógica nueva.** |
| `sin_mapear` | Función **pura nueva** en `guarda.py` | Hoy `_conceptos_egreso` (dentro de `anclar`) llama `mapear_a_conceptos` pero se queda solo con `.conceptos` y **bota `.sin_mapear`**. `rubros_sin_mapear(anclas, *, rubros, neutros_ids) -> list[str]` recorre los meses con ejecutado (cerrado + en_ejecucion), re-llama `mapear_a_conceptos` sobre el snapshot del ejecutado y **une** los `.sin_mapear` (sorted, dedup). Pura, sin Mongo. |
| `mes_en_curso` | Helper **nuevo** en `loader.py` (única capa Mongo) | Para el mes `en_ejecucion` del horizonte: `cargado_hasta` = fecha máxima de transacción de ese mes; `dia` = su día; `formula` = constante. Se implementa como **función separada** de `cargar_anclas` para NO alterar el contrato 3-tuple de `anclas_override` que usan los tests. `None` si no hay mes en ejecución. |

### Flujo

`_resultado_con` (ya orquesta motor→E1→D2) pasa a devolver, junto al resultado, los tres insumos
nuevos: el dict `marcas` (que ya tenía en mano), la lista `sin_mapear` (llamada pura) y el objeto
`completitud` (del helper del loader). `_proyectar_con` y `proyectar_vigente`/`proyectar_preview`
los pasan a `_serializar`, que añade las tres claves.

**Aditividad garantizada:** cuando no hay anclaje (sin `MesControl`), `marcas = {}`,
`sin_mapear = []`, `completitud = None` → las tres claves salen en su forma vacía y **todo lo
demás del payload queda byte-idéntico a hoy**.

### Alternativas descartadas

- **Sacar `sin_mapear` a través de `anclar`** — cambiaría la firma/retorno de `anclar`, que es
  perímetro estable (R0-adyacente). Rechazado: rompe la frontera.
- **Recomputar el mapeo en el `loader`** — metería `mapear_a_conceptos` en la capa Mongo y
  duplicaría trabajo. Rechazado: la función pura sobre el snapshot es más simple y testeable.
- **Plegar la completitud dentro de `cargar_anclas` (4-tuple)** — cambiaría el contrato de
  `anclas_override` de todos los tests existentes. Rechazado a favor del helper separado (una
  consulta ligera extra por request; B-1 estableció que `_resultado_con` corre 1× por request).

## 4. Tests (TDD rojo→verde)

1. **Shape aditivo** — con anclaje presente, las tres claves aparecen con contenido; un consumidor
   que solo lee las claves viejas no se rompe (las nuevas se ignoran).
2. **B13 (completitud + fórmula)** — `mes_en_curso.dia`/`cargado_hasta` = la fecha máxima real de
   transacción del mes en ejecución; `formula` presente. Capa real-mongo para la consulta nueva de
   fecha máxima (patrón de dos capas de E1).
3. **Foto `GET /proyeccion` sin ciclo == hoy** — sin `MesControl`: las claves existentes y sus
   valores byte-idénticos a la base; `meses_anclados=={}`, `sin_mapear==[]`, `mes_en_curso==null`.
4. **`sin_mapear`** — un rubro con movimiento y sin concepto (p. ej. 4040/R-2) aparece en la lista;
   escenario limpio → `[]`. Función pura, sin Mongo.
5. **`meses_anclados`** — refleja las 4 marcas (incluida `cerrado_sospechoso` reusando la lógica
   B10 de P4), sin redefinir vocabulario.

## 5. Semántica preservada (candados)

- **R0**: `motor.py` cero diffs. `anclar`/`lectura.py`/`reconciliacion.py` sin tocar.
- **C-1 intacto**: `meses_anclados` (marcas) es lectura pura; NO cambia `AnclaMes.estado`; la
  exclusión D2 (solo cerrados) queda inalterada.
- **Catálogo de eventos sin crecer** (P5 no emite eventos). **Golden sin regenerar.**
- **Dinero = Decimal** (los montos ya viajan como string vía `money_str`).
- **Pydantic strict / API `/api/v1`**: claves nuevas aditivas; ningún consumidor obligado a cambiar.

## 6. Alcance y entrega

- **Archivos:** `backend/app/proyeccion/ejecucion/guarda.py` (+ `rubros_sin_mapear` pura),
  `backend/app/proyeccion/ejecucion/loader.py` (+ helper de completitud del mes en curso),
  `backend/app/proyeccion/service.py` (`_resultado_con`/`_serializar`/`_proyectar_con` propagan) +
  tests.
- **Rama:** `feat/e1-p5-exposicion-shape` (desde main post-P4). **Un PR.**
- **Gate Kimi normal ≥9.0**, paquete en `planning/phases/e1-anclaje-ejecucion/auditorias/PR5-I/`
  (SOLICITUD + EVIDENCIA + PAQUETE.pdf). **No mergear sin GO Kimi + GO CEO.**
- **Estimado del plan:** ~0,25 d.
