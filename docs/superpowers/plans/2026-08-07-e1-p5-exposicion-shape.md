# E1 · P5 — Exposición del shape en `GET /proyeccion` — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Exponer, de forma aditiva, el origen de cada cifra de la proyección: `meses_anclados` (4 marcas), `sin_mapear` (rubros sin concepto) y la completitud del mes en curso (`mes_en_curso`, B13).

**Architecture:** Reusar lo que el backend ya computa: `marcas_origen` (P4) para las marcas; una función pura nueva `rubros_sin_mapear` (sobre el snapshot, reusa `mapear_a_conceptos`) para los rubros sin concepto; un helper Mongo nuevo en el `loader` para la completitud del mes en ejecución. `_resultado_con` empaqueta los tres en un `AnclajeMeta` y `_serializar` los emite como 3 claves top-level. Sin anclaje → formas vacías y el resto del payload byte-idéntico a hoy. Perímetro `anclar`/`lectura`/`reconciliacion`/`motor` intacto (R0).

**Tech Stack:** Python 3.12, FastAPI, Beanie/Motor, pytest + pytest-asyncio, mongomock-motor, ruff.

## Global Constraints

- **Dinero = Decimal, nunca float.** Montos en la API como string (vía `money_str`). (regla 1)
- **Fechas `YYYY-MM-DD` estrictas**, meses normalizados al día 1. `Transaccion.fecha` es string ISO (ordena cronológicamente por lexicografía). (regla 2)
- **Pydantic strict=True**; claves nuevas son aditivas, ningún consumidor obligado a cambiar. (regla 3)
- **R0:** `motor.py` cero diffs. NO tocar `anclar`, `lectura.py`, `reconciliacion.py`. (regla 10)
- **Catálogo de eventos cerrado (31):** P5 no emite eventos. (regla 11)
- **C-1 intacto:** las marcas son lectura pura; NO cambian `AnclaMes.estado`; la exclusión D2 (solo cerrados) queda inalterada.
- **TDD rojo→verde** por paso. Escribir en **español neutro**.
- CI corre `ruff check` **y** `ruff format --check` sobre `backend/` — correr ambos antes de pushear.
- Dos capas Mongo para consultas nuevas: mongomock + real-mongo (`@pytest.mark.requires_real_mongo`).

## Contrato de las 3 claves nuevas (referencia)

```jsonc
"meses_anclados": { "2026-07": "cerrado", "2026-08": "en_ejecucion" }, // {} sin anclaje
"sin_mapear": ["Rubro sin concepto X"],                               // [] si nada
"mes_en_curso": {                                                     // null si no hay mes en_ejecucion
  "mes": "2026-08", "cargado_hasta": "2026-08-06", "dia": 6,
  "formula": "ejecutado + max(0, definido - ejecutado) por concepto"
}
```

---

## Task 1: `rubros_sin_mapear` — función pura (guarda.py)

**Files:**
- Modify: `backend/app/proyeccion/ejecucion/guarda.py`
- Test: `backend/tests/test_e1_guarda.py`

**Interfaces:**
- Consumes: `mapear_a_conceptos(*, rubros, valor_por_rubro_id, neutros_ids) -> ResultadoMapeo` (de `lectura.py`, con `.sin_mapear: list[str]`); `AnclaMes` (con `.ejecutado_por_rubro_id: dict[str, Decimal]`); `RubroInfo`.
- Produces: `rubros_sin_mapear(anclas: dict[str, AnclaMes], *, rubros: list[RubroInfo], neutros_ids: set[str]) -> list[str]` — unión ordenada y deduplicada de nombres de rubro sin concepto, sobre los meses con ejecutado.

- [ ] **Step 1: Escribir el test que falla**

En `backend/tests/test_e1_guarda.py`, añadir al import de `guarda` el símbolo `rubros_sin_mapear` y agregar al final:

```python
def _rubros_con_4040():
    # los 9 del mapeo + un rubro no-sistema sin concepto (4040 = R-2, grupo
    # deudas_obligaciones no está en _GRUPOS_GASTOS_FIJOS → _concepto_de = None)
    return _rubros() + [
        RubroInfo(
            id="4040",
            codigo="4040",
            grupo="deudas_obligaciones",
            nombre="Ajuste raro 4040",
            es_sistema=False,
        )
    ]


def test_rubros_sin_mapear_reporta_rubro_con_movimiento_sin_concepto():
    anclas = {
        "2026-05": AnclaMes(
            estado="cerrado",
            ejecutado_por_rubro_id={"4010": Decimal("100"), "4040": Decimal("500")},
            definido_por_rubro_id={},
            ingreso_real=Decimal("0"),
        ),
    }
    assert rubros_sin_mapear(
        anclas, rubros=_rubros_con_4040(), neutros_ids=set()
    ) == ["Ajuste raro 4040"]


def test_rubros_sin_mapear_vacio_cuando_todo_mapea():
    anclas = {
        "2026-05": AnclaMes(
            estado="cerrado",
            ejecutado_por_rubro_id={"4010": Decimal("100")},
            definido_por_rubro_id={},
            ingreso_real=Decimal("0"),
        ),
    }
    assert rubros_sin_mapear(anclas, rubros=_rubros(), neutros_ids=set()) == []


def test_rubros_sin_mapear_dedup_y_ordena_entre_meses():
    a = AnclaMes(
        estado="cerrado",
        ejecutado_por_rubro_id={"4040": Decimal("500")},
        definido_por_rubro_id={},
        ingreso_real=Decimal("0"),
    )
    anclas = {"2026-05": a, "2026-06": a}  # mismo rubro en dos meses → una entrada
    assert rubros_sin_mapear(
        anclas, rubros=_rubros_con_4040(), neutros_ids=set()
    ) == ["Ajuste raro 4040"]
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `cd backend && python -m pytest tests/test_e1_guarda.py -k sin_mapear -v`
Expected: FAIL con `ImportError: cannot import name 'rubros_sin_mapear'`.

- [ ] **Step 3: Implementación mínima**

En `backend/app/proyeccion/ejecucion/guarda.py`, cambiar el import de `lectura` para incluir `mapear_a_conceptos`:

```python
from app.proyeccion.ejecucion.lectura import RubroInfo, mapear_a_conceptos
```

y añadir la función al final del archivo:

```python
def rubros_sin_mapear(
    anclas: dict[str, AnclaMes],
    *,
    rubros: list[RubroInfo],
    neutros_ids: set[str],
) -> list[str]:
    """Nombres de rubro con movimiento REAL y sin concepto del motor (unión ordenada y
    deduplicada sobre los meses con ejecutado). Reusa `mapear_a_conceptos` sobre el
    snapshot del ejecutado —aquí afloran R-1/R-2 parqueados—; función PURA (sin Mongo).
    `[]` si todo mapea. NO altera el anclaje: es solo lectura para exponer en el shape."""
    nombres: set[str] = set()
    for a in anclas.values():
        if not a.ejecutado_por_rubro_id:
            continue
        res = mapear_a_conceptos(
            rubros=rubros,
            valor_por_rubro_id=a.ejecutado_por_rubro_id,
            neutros_ids=neutros_ids,
        )
        nombres.update(res.sin_mapear)
    return sorted(nombres)
```

- [ ] **Step 4: Correr el test para verificar que pasa**

Run: `cd backend && python -m pytest tests/test_e1_guarda.py -v`
Expected: PASS (los 6 previos + los 3 nuevos).

- [ ] **Step 5: Lint**

Run: `cd backend && ruff check app/proyeccion/ejecucion/guarda.py tests/test_e1_guarda.py && ruff format --check app/proyeccion/ejecucion/guarda.py tests/test_e1_guarda.py`
Expected: `All checks passed!` (si `format --check` marca algo, correr `ruff format` sobre esos archivos).

- [ ] **Step 6: Commit**

```bash
git add backend/app/proyeccion/ejecucion/guarda.py backend/tests/test_e1_guarda.py
git commit -m "feat(e1-p5): rubros_sin_mapear (función pura, aflora R-1/R-2)"
```

---

## Task 2: `cargar_completitud_mes_en_curso` — helper Mongo (loader.py)

**Files:**
- Modify: `backend/app/proyeccion/ejecucion/loader.py`
- Test: `backend/tests/test_e1_loader.py` (mongomock)
- Test: `backend/tests/test_e1_loader_realmongo.py` (real-mongo, la consulta nueva)

**Interfaces:**
- Consumes: `MesControl` (con `.mes`, `.id`, `.estado`, `EstadoMes.EN_EJECUCION`); `Transaccion` (con `.fecha: str`, `.mes_id`); `_meses_del_horizonte(mes_inicio, horizonte) -> list[tuple[int,int]]`.
- Produces: `cargar_completitud_mes_en_curso(mes_inicio: tuple[int,int], horizonte: int) -> dict | None` — `{"mes","cargado_hasta","dia","formula"}` del mes `EN_EJECUCION` del horizonte, o `None` si no hay ninguno. `cargado_hasta`/`dia` son `None` si el mes existe pero aún no tiene transacciones.

- [ ] **Step 1: Escribir el test mongomock que falla**

En `backend/tests/test_e1_loader.py`, añadir `cargar_completitud_mes_en_curso` al import desde `loader` y agregar (usar el mismo estilo de seed del archivo — `MesControl`/`Transaccion` con `Banco`, `TipoFlujo`):

```python
@pytest.mark.asyncio
async def test_completitud_mes_en_curso_toma_la_fecha_maxima(db):
    ago = await MesControl(
        mes="2026-08-01",
        saldo_inicial_caja=Decimal("0"),
        estado=EstadoMes.EN_EJECUCION,
    ).insert()
    rubro = await Rubro(
        grupo=RubroGrupo.OPERACION,
        nombre="Arriendos",
        tipo_flujo=TipoFlujo.EGRESO,
        orden=1,
        codigo="2010",
    ).insert()
    for f in ("2026-08-03", "2026-08-06", "2026-08-01"):
        await Transaccion(
            fecha=f,
            descripcion="x",
            valor=Decimal("1"),
            tipo_flujo=TipoFlujo.EGRESO,
            rubro_id=rubro.id,
            mes_id=ago.id,
            banco=Banco.GLOBAL66,
            id_banco=f"REF-{f}|1",
        ).insert()

    comp = await cargar_completitud_mes_en_curso((2026, 8), 1)
    assert comp == {
        "mes": "2026-08",
        "cargado_hasta": "2026-08-06",
        "dia": 6,
        "formula": "ejecutado + max(0, definido - ejecutado) por concepto",
    }


@pytest.mark.asyncio
async def test_completitud_none_sin_mes_en_ejecucion(db):
    await MesControl(
        mes="2026-08-01",
        saldo_inicial_caja=Decimal("0"),
        estado=EstadoMes.CERRADO,
    ).insert()
    assert await cargar_completitud_mes_en_curso((2026, 8), 1) is None
```

Nota: reusar los imports que ya tiene `test_e1_loader.py` (`MesControl`, `EstadoMes`, `Rubro`, `RubroGrupo`, `TipoFlujo`, `Banco`, `Transaccion`, `Decimal`). Si falta `Banco`, importarlo de `app.domain.bancos`.

- [ ] **Step 2: Correr para verificar que falla**

Run: `cd backend && python -m pytest tests/test_e1_loader.py -k completitud -v`
Expected: FAIL con `ImportError: cannot import name 'cargar_completitud_mes_en_curso'`.

- [ ] **Step 3: Implementación mínima**

En `backend/app/proyeccion/ejecucion/loader.py` añadir la constante junto a `_CERO`/`_log`:

```python
_FORMULA_MES_EN_CURSO = "ejecutado + max(0, definido - ejecutado) por concepto"
```

y la función (usa `sort(-fecha).limit(1)`: `fecha` ISO ordena cronológicamente; funciona en mongomock y real):

```python
async def cargar_completitud_mes_en_curso(
    mes_inicio: tuple[int, int], horizonte: int
) -> dict | None:
    """B13 — completitud del mes EN EJECUCIÓN del horizonte: hasta qué día está cargado
    (fecha máxima de transacción) y con qué fórmula se arma (Regla A/D-08). `None` si
    ningún mes del horizonte está en ejecución. `cargado_hasta`/`dia` son `None` si el
    mes existe pero aún no tiene transacciones. Consulta independiente de `cargar_anclas`
    (no altera su contrato); corre 1× por request (ver B-1)."""
    meses = [f"{a:04d}-{m:02d}" for a, m in _meses_del_horizonte(mes_inicio, horizonte)]
    claves = [f"{m}-01" for m in meses]
    en_curso = await MesControl.find(
        In(MesControl.mes, claves),
        MesControl.estado == EstadoMes.EN_EJECUCION,
    ).to_list()
    if not en_curso:
        return None
    mc = min(en_curso, key=lambda x: x.mes)  # el más temprano, por determinismo
    ultima = (
        await Transaccion.find(Transaccion.mes_id == mc.id)
        .sort(-Transaccion.fecha)
        .limit(1)
        .to_list()
    )
    cargado_hasta = ultima[0].fecha if ultima else None
    return {
        "mes": mc.mes[:7],
        "cargado_hasta": cargado_hasta,
        "dia": int(cargado_hasta[8:10]) if cargado_hasta else None,
        "formula": _FORMULA_MES_EN_CURSO,
    }
```

- [ ] **Step 4: Correr para verificar que pasa (mongomock)**

Run: `cd backend && python -m pytest tests/test_e1_loader.py -v`
Expected: PASS (los previos + los 2 nuevos).

- [ ] **Step 5: Añadir la capa real-mongo**

En `backend/tests/test_e1_loader_realmongo.py`, añadir `cargar_completitud_mes_en_curso` al import y agregar dentro de `class TestLoaderReal`:

```python
    @pytest.mark.asyncio
    async def test_completitud_fecha_maxima_real(self, db):
        rubro = await Rubro(
            grupo=RubroGrupo.OPERACION,
            nombre="Arriendos",
            tipo_flujo=TipoFlujo.EGRESO,
            orden=1,
            codigo="2010",
        ).insert()
        ago = await MesControl(
            mes="2026-08-01",
            saldo_inicial_caja=Decimal("0"),
            estado=EstadoMes.EN_EJECUCION,
        ).insert()
        for f in ("2026-08-02", "2026-08-09", "2026-08-05"):
            await Transaccion(
                fecha=f,
                descripcion="x",
                valor=Decimal("1"),
                tipo_flujo=TipoFlujo.EGRESO,
                rubro_id=rubro.id,
                mes_id=ago.id,
                banco=Banco.GLOBAL66,
                id_banco=f"REF-{f}|1",
            ).insert()

        comp = await cargar_completitud_mes_en_curso((2026, 8), 1)
        assert comp["cargado_hasta"] == "2026-08-09"
        assert comp["dia"] == 9
```

- [ ] **Step 6: Correr la capa real-mongo (si hay URI) + lint**

Run: `cd backend && python -m pytest tests/test_e1_loader_realmongo.py -v` (se salta sin `COMPAS_TEST_MONGO_URI`; CI la corre).
Run: `cd backend && ruff check app/proyeccion/ejecucion/loader.py tests/test_e1_loader.py tests/test_e1_loader_realmongo.py && ruff format --check app/proyeccion/ejecucion/loader.py tests/test_e1_loader.py tests/test_e1_loader_realmongo.py`
Expected: PASS / `All checks passed!`.

- [ ] **Step 7: Commit**

```bash
git add backend/app/proyeccion/ejecucion/loader.py backend/tests/test_e1_loader.py backend/tests/test_e1_loader_realmongo.py
git commit -m "feat(e1-p5): cargar_completitud_mes_en_curso (B13, fecha máx. del mes en curso)"
```

---

## Task 3: `AnclajeMeta` + cableado `_resultado_con` → `_serializar`

**Files:**
- Modify: `backend/app/proyeccion/service.py`
- Test: `backend/tests/test_e1_pipeline.py`

**Interfaces:**
- Consumes: `marcas_origen`, `rubros_sin_mapear` (guarda), `cargar_completitud_mes_en_curso` (loader).
- Produces: dataclass `AnclajeMeta(meses_anclados: dict[str, str], sin_mapear: list[str], mes_en_curso: dict | None)`; `_resultado_con(...)` ahora devuelve **5 elementos** `(r, caja_minima, fondo, rec, meta)`; `_serializar(r, escenario, caja_minima, fondo, rec=None, *, meta: AnclajeMeta | None = None)` emite `meses_anclados`/`sin_mapear`/`mes_en_curso` (vacíos si `meta is None`).

- [ ] **Step 1: Escribir el test de integración que falla**

En `backend/tests/test_e1_pipeline.py`:

(a) Actualizar el helper `_correr` para desempacar el 5º elemento y exponer `meta` opcionalmente. Reemplazar la función `_correr` por:

```python
async def _correr(anclas_override, facturas_override, *, con_meta=False):
    r, _cm, _fondo, _rec, meta = await _resultado_con(
        _params(),
        _modelos(),
        escenario="base",
        mes_inicio=_MES_INICIO,
        horizonte_meses=_HORIZONTE,
        anclas_override=anclas_override,
        facturas_override=facturas_override,
    )
    filas = {m.mes: m for m in r.meses}
    return (filas, meta) if con_meta else filas
```

(b) Añadir el import `AnclajeMeta`:

```python
from app.proyeccion.service import AnclajeMeta, _resultado_con
```

(c) Añadir dos tests nuevos al final:

```python
@pytest.mark.asyncio
async def test_meta_marcas_y_sin_mapear(db):
    """P5: _resultado_con expone AnclajeMeta — meses_anclados (marcas) y sin_mapear
    (rubro con movimiento sin concepto). mes_en_curso es None (db vacía, sin ciclo)."""
    rubros_4040 = _rubros() + [
        RubroInfo(
            id="4040",
            codigo="4040",
            grupo="deudas_obligaciones",
            nombre="Ajuste raro 4040",
            es_sistema=False,
        )
    ]
    anclas = {
        "2026-10": AnclaMes(
            estado="cerrado",
            ejecutado_por_rubro_id={"4010": Decimal("40"), "4040": Decimal("9")},
            definido_por_rubro_id={"4010": Decimal("100")},  # 40<50 → sospechoso
            ingreso_real=Decimal("0"),
        )
    }
    _filas, meta = await _correr((anclas, rubros_4040, set()), [], con_meta=True)
    assert isinstance(meta, AnclajeMeta)
    assert meta.meses_anclados == {"2026-10": "cerrado_sospechoso"}
    assert meta.sin_mapear == ["Ajuste raro 4040"]
    assert meta.mes_en_curso is None


@pytest.mark.asyncio
async def test_meta_vacia_sin_anclaje(db):
    """Candado 'foto sin ciclo': sin anclas la meta queda totalmente vacía."""
    _filas, meta = await _correr(({}, [], set()), [], con_meta=True)
    assert meta.meses_anclados == {}
    assert meta.sin_mapear == []
    assert meta.mes_en_curso is None
```

- [ ] **Step 2: Correr para verificar que falla**

Run: `cd backend && python -m pytest tests/test_e1_pipeline.py -k "meta" -v`
Expected: FAIL con `ImportError: cannot import name 'AnclajeMeta'` (o `ValueError: not enough values to unpack` al desempacar 5).

- [ ] **Step 3: Definir `AnclajeMeta` e importar dependencias**

En `backend/app/proyeccion/service.py`, junto a los imports de E1 existentes, añadir:

```python
from app.proyeccion.ejecucion.guarda import marcas_origen, rubros_sin_mapear
from app.proyeccion.ejecucion.loader import (
    cargar_anclas,
    cargar_completitud_mes_en_curso,
)
```

(Si ya existen imports de `marcas_origen`/`cargar_anclas`, fusionarlos; no duplicar.) Añadir la dataclass cerca de las estructuras del módulo (usa `from dataclasses import dataclass, field` — si `field` no está importado, añadirlo):

```python
@dataclass(frozen=True)
class AnclajeMeta:
    """Metadato de origen de la proyección para el shape de P5 (aditivo). Vacío cuando
    no hay anclaje → la respuesta queda byte-idéntica a la de antes de P5."""

    meses_anclados: dict[str, str] = field(default_factory=dict)
    sin_mapear: list[str] = field(default_factory=list)
    mes_en_curso: dict | None = None
```

- [ ] **Step 4: Poblar la meta en `_resultado_con` y devolverla**

En `_resultado_con`, dentro del bloque `if anclas:` (donde ya se computa `marcas_origen` para el log de sospechosos), capturar el dict completo de marcas y la lista sin_mapear en lugar de recomputar; y computar la completitud siempre. Reemplazar el bloque del log B10 y el `return` final así:

```python
    marcas: dict[str, str] = {}
    sin_mapear: list[str] = []
    if anclas:
        aj = anclar(
            resultado=r,
            caja_minima=params.caja_minima,
            anclas=anclas,
            rubros=rubros_e1,
            neutros_ids=neutros_e1,
        )
        r = _kpis_a_resultado(aj)
        meses_anclados = frozenset(m for m, a in anclas.items() if a.estado == CERRADO)
        marcas = marcas_origen(anclas, rubros=rubros_e1, neutros_ids=neutros_e1)
        sin_mapear = rubros_sin_mapear(
            anclas, rubros=rubros_e1, neutros_ids=neutros_e1
        )
        # B10: log de los cerrados sospechosos (observabilidad; la marca NUNCA cambia el
        # régimen — un sospechoso sigue anclado y excluido de D2).
        sospechosos = sorted(m for m, mk in marcas.items() if mk == "cerrado_sospechoso")
        if sospechosos:
            _log.warning(
                "E1 B10: mes(es) cerrado(s) sospechoso(s) (ejecutado << definido): %s",
                sospechosos,
            )
```

Nota: `meses_anclados` ya se declara antes del `if anclas:` (línea ~360); conservarlo. Justo antes del bloque `facturas = (...)`, computar la completitud (independiente del anclaje):

```python
    completitud = (
        None
        if anclas_override is not None
        else await cargar_completitud_mes_en_curso(mes_inicio, horizonte)
    )
```

y cambiar el `return` final de `_resultado_con` de:

```python
    return r, params.caja_minima, fondo, rec
```

a:

```python
    meta = AnclajeMeta(
        meses_anclados=marcas, sin_mapear=sin_mapear, mes_en_curso=completitud
    )
    return r, params.caja_minima, fondo, rec, meta
```

Actualizar el tipo de retorno en la firma de `_resultado_con` de
`tuple[ResultadoProyeccion, object, list, ResultadoReconciliado | None]`
a
`tuple[ResultadoProyeccion, object, list, ResultadoReconciliado | None, AnclajeMeta]`.

- [ ] **Step 5: Emitir las 3 claves en `_serializar`**

Cambiar la firma de `_serializar` (línea ~148) para aceptar `meta`:

```python
def _serializar(
    r: ResultadoProyeccion,
    escenario: str,
    caja_minima,
    fondo: list,
    rec: ResultadoReconciliado | None = None,
    *,
    meta: "AnclajeMeta | None" = None,
) -> dict:
```

Al inicio del cuerpo, antes del `return`:

```python
    meta = meta or AnclajeMeta()
```

y añadir las 3 claves al dict que retorna (junto a las demás top-level, p. ej. tras `"escenario": escenario,`):

```python
        "meses_anclados": dict(meta.meses_anclados),
        "sin_mapear": list(meta.sin_mapear),
        "mes_en_curso": meta.mes_en_curso,
```

- [ ] **Step 6: Actualizar los 5 call-sites de `_resultado_con`**

`_resultado_con` ahora devuelve 5 valores. Actualizar cada llamada:

- `_proyectar_con` (~línea 417): `r, caja_min, fondo, rec, meta = await _resultado_con(...)` y el return `return _serializar(r, escenario, caja_min, fondo, rec, meta=meta)`.
- `valles_vigente` (~514): `r, caja_min, _, _, _ = await _resultado_con(...)`.
- `proyectar_impactos` (~540): `r, caja_min, fondo, _, meta = await _resultado_con(...)`; y pasar la meta a AMBAS series: `"base": _serializar(r, escenario, caja_min, fondo, meta=meta),` y `"ajustada": _serializar(r_aj, escenario, caja_min, fondo, meta=meta),`.
- `resolver` (~577): `r, caja_min, _, _, _ = await _resultado_con(...)`.
- `simular_plazo` (~647): `r, _caja, _fondo, rec, _ = await _resultado_con(...)`.

- [ ] **Step 7: Correr los tests de integración**

Run: `cd backend && python -m pytest tests/test_e1_pipeline.py -v`
Expected: PASS (B8/B11/candado + C-1 parametrizado + B10 log + los 2 nuevos de meta).

- [ ] **Step 8: Lint**

Run: `cd backend && ruff check app/proyeccion/service.py tests/test_e1_pipeline.py && ruff format --check app/proyeccion/service.py tests/test_e1_pipeline.py`
Expected: `All checks passed!` (correr `ruff format` si hace falta).

- [ ] **Step 9: Commit**

```bash
git add backend/app/proyeccion/service.py backend/tests/test_e1_pipeline.py
git commit -m "feat(e1-p5): AnclajeMeta + cableado _resultado_con→_serializar (3 claves aditivas)"
```

---

## Task 4: Shape a nivel endpoint + B13 + foto sin ciclo + regresión

**Files:**
- Test: `backend/tests/test_proyeccion_endpoints.py`

**Interfaces:**
- Consumes: el endpoint `GET /api/v1/proyeccion` (ya existente) y su serialización con las 3 claves nuevas.
- Produces: verificación de contrato aditivo end-to-end.

- [ ] **Step 1: Escribir los tests de endpoint que fallan**

En `backend/tests/test_proyeccion_endpoints.py`, siguiendo el patrón de sus tests existentes (mismo `client`/fixtures/seed que ya usa el archivo), añadir:

```python
@pytest.mark.asyncio
async def test_proyeccion_expone_claves_aditivas_sin_ciclo(client):
    """Foto sin ciclo: las 3 claves nuevas salen en su forma vacía; el resto del payload
    conserva sus claves y valores (aditivo, no rompe consumidores)."""
    resp = await client.get("/api/v1/proyeccion")
    assert resp.status_code == 200
    data = resp.json()
    assert data["meses_anclados"] == {}
    assert data["sin_mapear"] == []
    assert data["mes_en_curso"] is None
    # claves de hoy siguen presentes
    for k in ("escenario", "meses", "caja_final", "caja_minima", "piso_caja"):
        assert k in data


@pytest.mark.asyncio
async def test_proyeccion_mes_en_curso_b13(client, <fixture_seed_en_ejecucion>):
    """B13: con un mes EN_EJECUCION cargado, mes_en_curso trae completitud + fórmula."""
    resp = await client.get("/api/v1/proyeccion")
    data = resp.json()
    mec = data["mes_en_curso"]
    assert mec is not None
    assert mec["dia"] == <dia_max_sembrado>
    assert mec["formula"] == "ejecutado + max(0, definido - ejecutado) por concepto"
```

Nota de implementación (resolver al escribir el test, NO dejar placeholders en el código): el segundo test necesita un `MesControl` en estado `EN_EJECUCION` dentro del horizonte con transacciones sembradas y la taxonomía con los 9 códigos del mapeo (para no disparar B12 al anclar). Reusar el/los helper(s) de seed que ya tiene `test_proyeccion_endpoints.py` (el mismo que usa `_seed_mes_cerrado_con_ingreso` para B12 en P3); si no hay uno para `EN_EJECUCION`, clonar ese patrón cambiando `EstadoMes.CERRADO` por `EstadoMes.EN_EJECUCION` y sembrando 2-3 transacciones con fechas conocidas. Sustituir `<fixture_seed_en_ejecucion>` y `<dia_max_sembrado>` por el fixture/valor reales.

- [ ] **Step 2: Correr para verificar que fallan**

Run: `cd backend && python -m pytest tests/test_proyeccion_endpoints.py -k "aditivas or b13" -v`
Expected: FAIL (`KeyError: 'meses_anclados'` en la respuesta actual, o `mes_en_curso is None` en el B13 antes de sembrar).

- [ ] **Step 3: Verde por construcción (ya implementado en Task 3)**

No hay nuevo código de app: Task 3 ya añadió las claves. Si el B13 falla, ajustar el seed del test (no la lógica). Correr:

Run: `cd backend && python -m pytest tests/test_proyeccion_endpoints.py -v`
Expected: PASS.

- [ ] **Step 4: Regresión completa + R0 + lint**

Run: `cd backend && python -m pytest -q`
Expected: todo verde (los ~901 previos + los nuevos de P5). Si algún test existente asertaba el dict de respuesta COMPLETO y ahora falla por las claves nuevas, actualizarlo **aditivamente** (añadir las claves esperadas), nunca quitar la verificación.

Run (R0): `git diff --stat -- backend/app/proyeccion/motor.py`
Expected: sin salida (cero diffs en `motor.py`).

Run: `cd backend && ruff check . && ruff format --check .`
Expected: `All checks passed!`.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_proyeccion_endpoints.py
git commit -m "test(e1-p5): shape aditivo end-to-end + B13 mes_en_curso + foto sin ciclo"
```

---

## Cierre (fuera de tasks — tras verde completo)

1. **Gate Kimi PR5-I:** armar `planning/phases/e1-anclaje-ejecucion/auditorias/PR5-I/` (SOLICITUD.md + EVIDENCIA.md con diff+tests reales) y generar `PAQUETE.pdf` con `python scripts/generate_kimi_audit_pdf.py planning/phases/e1-anclaje-ejecucion/auditorias/PR5-I/SOLICITUD.md planning/phases/e1-anclaje-ejecucion/auditorias/PR5-I/EVIDENCIA.md`. El CEO lo sube a Kimi. Umbral ≥9.0.
2. **PR** desde `feat/e1-p5-exposicion-shape`; vigilar CI a verde completo, confirmar el job `backend` aparte (no es required check).
3. **NO mergear sin GO Kimi + GO CEO.** Con GO: squash-merge + tracker (Tareas E1-P5 Hecha + Gates GATE-KIMI E1-P5) + memoria.
4. Siguiente: **P6** (frontend) cierra el épico E1.

## Self-Review (cobertura del spec)

- **`meses_anclados`** → Task 3 (reusa `marcas_origen`), verificado en `test_meta_marcas_y_sin_mapear` + endpoint Task 4. ✔
- **`sin_mapear`** → Task 1 (pura) + Task 3 (cableado) + endpoint. ✔
- **`mes_en_curso` (B13, objeto rico)** → Task 2 (loader) + Task 3 (cableado) + Task 4 (endpoint B13). ✔
- **Aditivo / foto sin ciclo == hoy** → `test_meta_vacia_sin_anclaje` (Task 3) + `test_proyeccion_expone_claves_aditivas_sin_ciclo` (Task 4) + Step 4 de regresión. ✔
- **R0 / perímetro intacto** → ningún task toca `motor.py`/`anclar`/`lectura.py`/`reconciliacion.py`; verificado en Task 4 Step 4. ✔
- **C-1 intacto** → el filtro `meses_anclados = frozenset(... estado == CERRADO)` no se toca; las marcas son lectura pura. ✔
- **Dos capas Mongo** para la consulta nueva → Task 2 (mongomock + real-mongo). ✔
- **Tipos consistentes:** `rubros_sin_mapear`/`marcas_origen` firman `(anclas, *, rubros, neutros_ids)`; `AnclajeMeta` mismos nombres de campo que las 3 claves JSON; `_serializar` recibe `meta=` en las 3 llamadas (425/551/552). ✔
