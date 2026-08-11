# FABS · Incremento 1 — Cimiento determinista (sin LLM)

- **Fecha:** 2026-08-10 · **Autor:** Claude + CEO (Andrés)
- **Fase:** primer incremento de la construcción de FABS (agente CFO de RODDOS)
- **Estado:** spec para aprobación del CEO (aún sin código)
- **Corpus que gobierna:** `docs/COMPAS_CFO_*` (INFO/ARQ/PLAN v1.2) + Auditoría v1.0 + acta de decisiones FABS (2026-08-10, memoria `fabs-fundacion-decisiones`). Ante conflicto, mandan las decisiones del CEO de esta sesión.

## 1. Propósito y alcance (SOLO este incremento)

Construir el **cimiento determinista** de FABS: el motor de datos que lee lo que COMPAS ya calcula y devuelve **cada cifra con su evidencia**, más el **arnés de evaluación (golden set)** que lo verifica. Es la implementación de la regla #1 del sistema (regla del CFO-INFO y lección Deloitte de la auditoría): *el modelo nunca calcula ni inventa; toda cifra publicada trae su origen*.

**En alcance:**
1. Módulo `backend/app/cfo/` nuevo, detrás de feature flag `CFO_ENABLED` (apagado por defecto).
2. `cfo/calc/` — puente de **solo lectura** a la capa de servicios de COMPAS, para **3 conceptos**: caja disponible hoy, runway, IVA del cuatrimestre. Cada uno devuelve un resultado tipado con evidencia.
3. `cfo/goldens/` — colección `cfo_goldens`, runner de evaluación, y un **lote semilla** de casos verificados a mano desde PROD.
4. Salvaguarda S1 (regla de import: `cfo/` solo importa servicios de COMPAS; escribe solo en `cfo_*`) + doble barrera del flag.

**Fuera de alcance (incrementos siguientes, YAGNI aquí):** el loop del LLM, Telegram, chat en COMPAS, alertas proactivas, provisión de IVA, el motor de escenarios conversacional, y el set completo de 240+60 goldens (esto es el arnés + semilla).

**Decisiones del CEO ya incorporadas:** Alegra = CERO (ninguna referencia); CXC socios / interés presuntivo / devengado = FUERA; las fórmulas viven en COMPAS y FABS las **consume** (D5); goldens desde PROD real **anonimizado** (D15); presupuesto operativo del modelo $30/mes (no aplica a este incremento — aún no hay LLM).

## 2. Arquitectura

Módulo interno de COMPAS (mismo repo, servicio y base — decisión v1.1/v1.2), **aditivo**:

```
backend/app/cfo/                 # MÓDULO NUEVO — todo FABS vive aquí
├── __init__.py
├── config.py                    # flag CFO_ENABLED (default False)
├── calc/                        # puente read-only → servicios COMPAS
│   ├── __init__.py
│   ├── evidencia.py             # ResultadoCFO + Evidencia (tipos, Decimal)
│   ├── caja.py                  # concepto: caja disponible hoy
│   ├── runway.py                # concepto: meses de runway
│   └── iva.py                   # concepto: IVA del cuatrimestre + fecha DIAN
├── goldens/
│   ├── __init__.py
│   ├── modelo.py                # Document cfo_goldens (Beanie)
│   ├── runner.py                # corre calc vs esperado, tolerancia
│   └── semilla.py               # lote inicial (valores del CEO/PROD, editables)
└── datos/
    └── repositorios.py          # única puerta de escritura: SOLO cfo_*
```

- **Flag `CFO_ENABLED`:** en ESTE incremento se crea solo la **config del flag** (default `False`) y la disciplina aditiva — NO se expone ningún endpoint (el puente y el runner son librería + tests). La **doble barrera** real (registro condicional del router `/api/v1/cfo` + guard 404 por ruta) aterriza con el primer endpoint, en el incremento 2. **Propiedad verificable ya en inc1:** con el módulo `cfo/` presente y sin router montado, la suite de COMPAS pasa idéntica.
- **S1 (aislamiento por código):** `cfo/calc/` importa SOLO funciones públicas de `app.<modulo>.service`; nunca queries directos a colecciones ajenas. `cfo/datos/repositorios.py` es la única subruta que toca el driver, y solo sobre colecciones `cfo_*`. Se verifica con una prueba estática en CI (regla S1) — un test que falla si `cfo/` importa un modelo de dominio ajeno o `get_pymongo_collection` de una colección no-`cfo_*`.

## 3. Contrato de evidencia (`cfo/calc/evidencia.py`)

El tipo que todo concepto devuelve. Sin evidencia, no hay cifra.

```
Evidencia (Pydantic strict):
  fuente: str            # p.ej. "proyeccion.proyectar_vigente", "caja.caja_diaria"
  fecha_corte: str|None  # 'YYYY-MM-DD' del dato más reciente que sustenta la cifra
  ref: str               # identificador reproducible (mes de control, cuatrimestre, etc.)

ResultadoCFO (Pydantic strict):
  concepto: str          # "caja_hoy" | "runway" | "iva_cuatrimestre"
  valor: Money|None      # Decimal; None SOLO si el dato no existe (abstención honesta)
  unidad: str            # "COP" | "meses" | ...
  disponible: bool       # False → el agente declara la ausencia, no inventa
  evidencia: Evidencia
  detalle: dict          # desglose opcional (no cifras nuevas: derivadas del origen)
```

**Frescura declarada (corrige el defecto FP6 del legado):** `fecha_corte` es obligatoria en conceptos con dato temporal (caja). Si el último dato supera el SLA (p.ej. caja > 3 días), el resultado lo refleja para que el consumidor lo diga ("dato al [fecha]"), nunca lo presente como de hoy.

## 4. Los 3 conceptos del incremento (`cfo/calc/`)

Todos son funciones `async` puras respecto a efectos (solo LEEN), en Decimal, que llaman a un servicio de COMPAS y envuelven el resultado en `ResultadoCFO`.

| Concepto | Lee de (servicio COMPAS) | Devuelve | Evidencia |
|---|---|---|---|
| `caja_hoy()` | `caja.service.caja_diaria` (último día con dato) | saldo disponible total (Money) | fuente + `fecha_corte` = último movimiento cargado |
| `runway()` | `proyeccion.service.proyectar_vigente` (KPI `runway_meses`) | meses de runway (Money\|None) | fuente + `ref` = parámetros vigentes + mes inicio |
| `iva_cuatrimestre()` | `facturas.service` (liquidación IVA) | IVA a pagar del cuatrimestre vigente + fecha DIAN | fuente + `ref` = cuatrimestre + fecha DIAN |

Regla transversal: si el servicio de COMPAS no tiene el dato (p.ej. no hay ciclo abierto, o IVA sin facturas), el concepto devuelve `disponible=False`, `valor=None` — **abstención honesta**, nunca un `$0` falso.

## 5. Arnés de evaluación (`cfo/goldens/`)

Eval-first: el arnés existe **antes** que cualquier LLM; nada avanza sin él (gate G1 del plan).

- **`cfo_goldens` (Beanie Document):** `{ concepto, filtros: dict, valor_esperado: Money|None, tolerancia: Decimal, unidad: str, origen: 'semilla'|'fabian', nota, creado_at }`. `tolerancia` es Decimal (no Money-COP) para cubrir la unidad del concepto — $1 COP para montos, 0,1 para "meses". Colección `cfo_*` → escritura permitida por S1.
- **`runner.py`:** para cada golden, corre el concepto de `cfo/calc/` con sus `filtros` y compara `valor` contra `valor_esperado` dentro de `tolerancia`. Casos de abstención (`valor_esperado=None`) exigen `disponible=False`. Reporta: total, OK, fallos (con el delta). Devuelve estructura, no imprime — para poder correrlo en CI.
- **Tolerancia:** **$1 COP absoluta** por defecto (PROP declarada, no "heredada de COMPAS" — la auditoría marcó que ese literal no existía; COMPAS concilia el golden-master a 0,042 COP, así que $1 es holgado y honesto). Conceptos en "meses" (runway): tolerancia 0,1.
- **Semilla (`semilla.py`):** un lote pequeño de goldens que yo calculo al peso desde PROD (solo lectura) para los 3 conceptos, con `origen='semilla'`. El set completo (240+60, con casos de abstención) se construye con Fabián en un incremento posterior; esto es el andamiaje + la prueba de que corre.

## 6. Flujo de datos

```
cfo/goldens/runner  ──►  cfo/calc/<concepto>  ──►  app.<modulo>.service (COMPAS)  ──►  Mongo (lectura)
        │                        │
        │                        └─►  envuelve el resultado en ResultadoCFO + Evidencia
        └─►  compara valor vs esperado (tolerancia)  ──►  reporte {ok, fallos, deltas}
```
Ninguna flecha escribe en datos de COMPAS. La única escritura del incremento es sembrar `cfo_goldens` (colección propia), vía `cfo/datos/repositorios.py`.

## 7. Manejo de errores

- **Solo lectura:** el módulo no expone ninguna escritura sobre datos financieros de COMPAS (por diseño, no por permiso). Elimina por construcción los riesgos FP2/FP3/FP12 del legado.
- **Abstención, no invención:** dato ausente → `disponible=False` + `valor=None`. El runner trata esto como un resultado válido (para los goldens de abstención), no como error.
- **Fallo del servicio COMPAS:** se propaga como excepción tipada del módulo `cfo`; el runner lo marca como fallo del caso, no como cifra.

## 8. Pruebas (TDD)

- **Por concepto:** test unitario de cada función de `cfo/calc/` contra un COMPAS de prueba (mongomock, mismo patrón que la suite existente): (a) camino feliz devuelve `ResultadoCFO` con evidencia y `fecha_corte`; (b) sin dato → `disponible=False`, `valor=None`.
- **Runner:** corre un mini-set de goldens (OK, fallo por delta, abstención correcta) y verifica el reporte.
- **S1 estático:** test que falla si `cfo/` importa un modelo de dominio ajeno o toca una colección no-`cfo_*`.
- **Flag apagado = COMPAS idéntico:** la suite completa de COMPAS pasa con el módulo `cfo/` presente y el flag apagado (no se registra router, no cambia comportamiento).
- **Decimal/Money en todo el pipeline** (regla 1); cero float.

## 9. Reglas innegociables honradas

Decimal/Money (regla 1) · TZ Bogotá y fechas `YYYY-MM-DD` (regla 2) · Pydantic strict (regla 3) · **motor de COMPAS cero diffs** (aditivo puro) · sin secretos en repo (regla 12) · **sin eventos nuevos de auditoría** en este incremento (el catálogo cerrado no crece; los eventos `cfo.*` llegan con su CR cuando aterrice el loop/escrituras del incremento 2) · trabajos pesados irían al Worker (regla 6) — no aplica aún.

## 10. Criterio de terminado (DoD del incremento 1)

- Los 3 conceptos devuelven `ResultadoCFO` con evidencia y frescura; abstención honesta cuando no hay dato.
- El runner corre la semilla de goldens en verde y produce un reporte reproducible.
- Test S1 en verde; flag apagado ⇒ suite de COMPAS idéntica (verde antes y después).
- `motor.py` y demás servicios de COMPAS con cero diffs.
- Gate: por tocar la lectura de cifras de plata, el PR va con evidencia para auditoría Kimi (aunque no escribe, alimenta decisiones).
