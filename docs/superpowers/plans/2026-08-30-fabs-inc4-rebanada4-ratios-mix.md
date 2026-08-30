# FABS inc4 · Rebanada 4 — Ratios/% + Mix · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que FABS responda por conversación la composición del gasto real por grupo ("¿qué % es nómina?") y el mix de modelos ("¿cómo está mi mix?"), con porcentajes que computa COMPAS y cita el modelo por token — abriendo el uso de `%` sin debilitar el control anti-alucinación.

**Architecture:** Dos agregaciones nuevas de valores planos (`composicion_gasto_real` en `proyeccion/service.py`, `mix_activos` en `modelos_moto/service.py`) → dos calcs en `cfo/calc/ratios.py` (nuevo) que computan los ratios `%` → tools + prompt. El `%` viaja por el camino del token: el modelo cita `[[pct_nomina]]` (sin `%` literal), el verificador pasa, `sustituir_tokens` lo vuelve "45,3%" DESPUÉS. Un branch nuevo `unidad=="%"` en `conceptos.formatear`; el verificador NO cambia de lógica (solo docstring). De paso se cierra el fast-follow M3 (borrar `CONCEPTOS_CITABLES` muerto).

**Tech Stack:** Python 3.12, FastAPI, Beanie/Motor, MongoDB (tests: mongomock, seed via `.insert()`), Pydantic strict, `decimal.Decimal`, pytest.

**Spec:** `docs/superpowers/specs/2026-08-30-fabs-inc4-rebanada4-ratios-mix-design.md`

## Global Constraints

- **Dinero = `decimal.Decimal`, nunca float.** El `%` también es Decimal (`valor`, unidad `"%"`). Cero `float(` en la ruta nueva.
- **`motor.py` cero diffs.** Aditivo.
- **El verificador NO se debilita.** Solo se actualiza su docstring/comentarios (COMPAS ahora SÍ computa `%`, pero el modelo los cita por TOKEN; un `%` crudo del modelo sigue bloqueado). Hay un test explícito de que un `%` crudo del modelo SIGUE dando `ok=False`.
- **S1:** `cfo/**` importa solo servicios (`proyeccion.service`, `modelos_moto.service`) + `core`/`evidencia`/stdlib — NO `app.domain.*`/`motor`/driver. Las agregaciones viven en `proyeccion`/`modelos_moto` service y devuelven valores planos (`ComposicionGasto`, `list[tuple[str,Decimal]]`). **La subcadena literal `motor` NO puede aparecer en `cfo/calc/ratios.py`** (regex de `test_s1_aislamiento.py`). Los ratios los computa `cfo/calc` (COMPAS, no el modelo — permitido).
- **Mongomock-safe:** las agregaciones usan `Transaccion.find(...)` + `pares_clasificacion`, NUNCA `col.aggregate($group)` (no soportado por mongomock). NO reusar `control.service._egresos_por_rubro` (usa `$group`).
- **Conceptos NAMESPACED** `pct_*`/`cop_*`/`mix_*`/`gasto_total_comp` — inventario verificado libre de colisión (rebanadas 1–3: `piso_*`,`impacto_*`,`*_real_*`,`delta_*`,`caja_real_*`,`gasto_real_mes`,`presupuesto_mes`,`desvio_presupuesto`,`caja_hoy`,`runway`,`iva_cuatrimestre`,`unidades_extra`,`piso_con_unidades`). `gasto_real_mes` (r3) ≠ `gasto_total_comp` (r4).
- **Catálogo de auditoría sin eventos nuevos.** Flag `CFO_ENABLED`. `ruff` limpio. Gate = **gate-waiver + GO CEO** (NADA de Kimi; NUNCA simular).
- **Branch guard:** `git branch --show-current` == `feat/fabs-inc4-rebanada4-ratios-mix` antes de cada commit. Rama desde `main`.

### Firmas reales verificadas (reusar/imitar)
- `RubroGrupo` (`app/domain/rubro.py`): `INGRESOS_OPERATIVOS`, `COSTO_PRODUCTO`, `OPERACION`, `NOMINA`, `DEUDAS_OBLIGACIONES`, `OTROS`. Los 5 grupos de gasto = todos menos `INGRESOS_OPERATIVOS`.
- Mapeo rubro→grupo (patrón de `control/service.py:127`): `{r.id: r.grupo for r in await Rubro.find_all().to_list()}`; `r.grupo.value`.
- `Transaccion` (`app/domain/transaccion.py`): `mes_id`, `rubro_id`, `tipo_flujo: TipoFlujo (EGRESO="egreso")`, `valor: Money`, `partes`. `pares_clasificacion(tx) -> list[tuple[rubro_id, valor]]` (expande `partes`, o `[(rubro_id, valor)]` si no hay split).
- `cierre.service._rubro_ajuste() -> Rubro` (ya importado en proyeccion/service.py) — `.id` es el rubro "Ajuste de conciliación".
- `MesControl`: `mes`("YYYY-MM-01"), `estado: EstadoMes(CERRADO)`. Selección de meses = como rebanada 3 (`actuals_mensuales`).
- `modelos_moto.service.listar_modelos(*, activo=None) -> list[ModeloMoto]`; `ModeloMoto.nombre: str`(único), `participacion_mix: Money`(0..1, sin validación de suma).
- `cfo.calc.evidencia.ResultadoCFO(concepto, valor:Money|None, unidad, disponible, evidencia, detalle={})`; `Evidencia(fuente, fecha_corte, ref)`.
- `cfo.agente.conceptos.formatear(r, hoy=None)`: branches `concepto=="runway"`→meses, `unidad=="unidades"`→motos, else `_money_es`. `_money_es`/`_meses_es` ya cuantizan es-CO. `sustituir_tokens` solo sustituye `disponible and valor is not None`.
- `verificador.py`: `_RE_PORCENTAJE = re.compile(r"\d+(?:[.,]\d+)?\s*%")`; `verificar()` da `ok = not crudas and not tokens_invalidos`. Docstring/comentarios ~líneas 20-31, 58-61, 149-155 dicen "COMPAS no tiene concepto de porcentaje" (a actualizar).
- `CONCEPTOS_CITABLES` (`conceptos.py:15-17`) frozenset muerto; único consumidor: `tests/cfo/agente/test_conceptos.py:4` (import) y `:34` (aserción `== frozenset({"caja_hoy","runway","iva_cuatrimestre"})`).
- Patrón calc + abstención: `cfo/calc/tendencias.py` (rebanada 3). Patrón tool con-enum: `tendencia_real`; no-param: `rumbo_caja` (directa en DISPATCH). `resultado_a_dict` strippea valor/detalle.

---

### Task 1: `composicion_gasto_real` + `ComposicionGasto` — `proyeccion/service.py` (4a)

**Files:** Modify `backend/app/proyeccion/service.py` · Test `backend/tests/proyeccion/test_composicion_gasto_real.py`

**Interfaces — Produces:**
- `@dataclass(frozen=True) ComposicionGasto(ventana: str, meses: list[str], por_grupo: dict[str, Decimal], total: Decimal)` (`meses` = "YYYY-MM"; `por_grupo` clave = valor de `RubroGrupo`).
- `async def composicion_gasto_real(*, ventana: str) -> ComposicionGasto` — `ventana ∈ {cerrado, acumulado, curso}`.

- [ ] **Step 1: failing test** (mongomock; seed via `.insert()`, imitar `tests/proyeccion/test_actuals_mensuales.py` de la rebanada 3). Un mes cerrado 2026-07 con: rubro NOMINA (EGRESO) tx 3.000.000, rubro DEUDAS_OBLIGACIONES tx 1.000.000, un split (`partes`) 1.000.000 repartido 600k OPERACION + 400k NOMINA, y una tx 500.000 al rubro "Ajuste de conciliación" (NO cuenta):

```python
# backend/tests/proyeccion/test_composicion_gasto_real.py
from decimal import Decimal
import pytest
from app.proyeccion import service as svc

@pytest.mark.asyncio
async def test_composicion_cerrado_por_grupo_excluye_ajuste_expande_partes(db):
    # seed (copiar patrón de tests/proyeccion/test_actuals_mensuales.py):
    #  Rubro 'Ajuste de conciliación' (es_sistema=True, grupo OTROS),
    #  Rubro nomina (grupo NOMINA), rubro deudas (DEUDAS_OBLIGACIONES), rubro oper (OPERACION);
    #  MesControl 2026-07-01 cerrado saldo_inicial 0;
    #  tx EGRESO 3M->nomina, 1M->deudas, split 1M (600k oper + 400k nomina) via partes,
    #  0.5M EGRESO -> rubro ajuste.
    c = await svc.composicion_gasto_real(ventana="cerrado")
    assert c.meses == ["2026-07"]
    assert c.por_grupo["nomina"] == Decimal("3400000")            # 3M + 400k del split
    assert c.por_grupo["deudas_obligaciones"] == Decimal("1000000")
    assert c.por_grupo["operacion"] == Decimal("600000")          # 600k del split
    assert c.total == Decimal("5000000")                          # ajuste (0.5M) excluido
    assert "ingresos_operativos" not in c.por_grupo               # solo grupos de gasto
```
(El implementer completa el seeding copiando el patrón EXACTO de un test existente que crea `Rubro`/`MesControl`/`Transaccion` — `tests/proyeccion/test_actuals_mensuales.py`. `Rubro` requiere `grupo`, `nombre`, `tipo_flujo`, `orden`. Montos recalculados a mano arriba.)

- [ ] **Step 2: Run → FAIL** — `cd backend && python -m pytest tests/proyeccion/test_composicion_gasto_real.py -v`.

- [ ] **Step 3: Implement** en `service.py` (agregar imports que falten: `from app.domain.rubro import Rubro, RubroGrupo`; `pares_clasificacion` de `app.domain.transaccion`; `_rubro_ajuste`/`Transaccion`/`TipoFlujo`/`MesControl`/`EstadoMes` ya en scope — confirmar):

```python
_GRUPOS_GASTO = [g for g in RubroGrupo if g != RubroGrupo.INGRESOS_OPERATIVOS]


@dataclass(frozen=True)
class ComposicionGasto:
    ventana: str
    meses: list[str]                 # 'YYYY-MM'
    por_grupo: dict[str, Decimal]    # RubroGrupo.value -> COP
    total: Decimal


async def _meses_de_ventana(ventana: str) -> list[MesControl]:
    todos = await MesControl.find_all().sort(+MesControl.mes).to_list()
    if ventana == "cerrado":
        cerrados = [mc for mc in todos if mc.estado == EstadoMes.CERRADO]
        return cerrados[-1:]
    con_mov: list[MesControl] = []
    for mc in reversed(todos):  # más recientes primero
        if await Transaccion.find(Transaccion.mes_id == mc.id).count() > 0:
            con_mov.append(mc)
    if ventana == "curso":
        return con_mov[:1]
    if ventana == "acumulado":
        return list(reversed(con_mov[:3]))
    raise ProyeccionError(f"ventana no soportada: {ventana}", 422)


async def composicion_gasto_real(*, ventana: str) -> ComposicionGasto:
    meses = await _meses_de_ventana(ventana)
    if not meses:
        raise ProyeccionError("sin meses con datos para la ventana", 409)
    rubro_aj = await _rubro_ajuste()
    grupo_de = {r.id: r.grupo for r in await Rubro.find_all().to_list()}
    por_grupo: dict[str, Decimal] = {g.value: Decimal("0") for g in _GRUPOS_GASTO}
    mes_ids = [mc.id for mc in meses]
    async for t in Transaccion.find(
        {"mes_id": {"$in": mes_ids}, "tipo_flujo": TipoFlujo.EGRESO.value}
    ):
        for rid, val in pares_clasificacion(t):
            if rid == rubro_aj.id:
                continue
            g = grupo_de.get(rid)
            if g is None or g == RubroGrupo.INGRESOS_OPERATIVOS:
                continue
            por_grupo[g.value] += val
    total = sum(por_grupo.values(), Decimal("0"))
    return ComposicionGasto(
        ventana=ventana, meses=[mc.mes[:7] for mc in meses],
        por_grupo=por_grupo, total=total,
    )
```

- [ ] **Step 4: Run → PASS** + `python -m pytest tests/proyeccion -q` verde. `ruff` limpio. `git diff -- app/proyeccion/motor.py` vacío.
- [ ] **Step 5: Commit** — `feat(proyeccion): composicion_gasto_real (egreso real por grupo, 3 ventanas, excluye ajuste)`.

---

### Task 2: `%` en el formateo + docstring del verificador + cleanup M3 — `cfo/agente/` (4a, infra del %)

**Files:** Modify `backend/app/cfo/agente/conceptos.py`, `backend/app/cfo/agente/verificador.py`, `backend/tests/cfo/agente/test_conceptos.py`

**Interfaces — Produces:** `conceptos.formatear` renderiza `unidad=="%"` como `"45,3%"`.

- [ ] **Step 1: failing test** en `test_conceptos.py`:

```python
def test_formatear_porcentaje():
    from decimal import Decimal
    from app.cfo.calc.evidencia import Evidencia, ResultadoCFO
    r = ResultadoCFO(concepto="pct_nomina", valor=Decimal("45.3"), unidad="%",
        disponible=True, evidencia=Evidencia(fuente="f", fecha_corte=None, ref="cerrado:2026-07"))
    assert formatear(r) == "45,3%"
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement**
  - `conceptos.py`: en `formatear`, ANTES del branch money, agregar:
    ```python
    if r.unidad == "%":
        return _pct_es(r.valor)
    ```
    y el helper `def _pct_es(d: Decimal) -> str: return f"{d:.1f}".replace(".", ",") + "%"`.
  - `conceptos.py`: **borrar** el `CONCEPTOS_CITABLES = frozenset({...})` (líneas ~15-17, código muerto no consumido para gating — cleanup M3).
  - `test_conceptos.py`: quitar el import de `CONCEPTOS_CITABLES` (línea 4) y la aserción/función que lo verifica (línea ~34). Confirmar por grep que ningún otro archivo lo importa.
  - `verificador.py`: **solo docstring/comentarios** (~módulo, ~líneas 58-61 y 149-155): reemplazar "COMPAS no tiene concepto de porcentaje / TODO % queda huérfano" por: COMPAS SÍ computa `%` (rebanada 4: conceptos `pct_*`/`mix_*`), pero el modelo los cita por TOKEN y el texto sustituido no se re-verifica; un `%` CRUDO en el texto del modelo sigue siendo violación (el modelo no extrapola ratios) — por eso `_RE_PORCENTAJE` y la lógica se mantienen SIN cambios.

- [ ] **Step 4: Run → PASS** (`test_formatear_porcentaje`) + `python -m pytest tests/cfo/agente/test_conceptos.py tests/cfo/agente/test_verificador.py -q` verde (el docstring no cambia lógica; los tests del verificador deben seguir pasando). `ruff` limpio.
- [ ] **Step 5: Commit** — `feat(cfo): formatear branch % + docstring verificador (COMPAS ya computa %) + borra CONCEPTOS_CITABLES muerto`.

---

### Task 3: Calc `composicion_gasto` — `cfo/calc/ratios.py` (4a)

**Files:** Create `backend/app/cfo/calc/ratios.py` · Test `backend/tests/cfo/calc/test_ratios.py`

**Interfaces:**
- Consumes: `proyeccion.service.composicion_gasto_real` + `ComposicionGasto` + `ProyeccionError`.
- Produces: `async def composicion_gasto(*, ventana: str) -> list[ResultadoCFO]`. Conceptos: `gasto_total_comp` (COP); por grupo `cop_{suf}` (COP) y `pct_{suf}` (unidad `"%"`, `= cop/total*100` cuantizado a 0.1). Sufijos por `RubroGrupo.value`: `costo_producto`,`operacion`,`nomina`,`deudas` (de `deudas_obligaciones`),`otros`. `ventana` inválida → `ValueError`; sin data/total≤0 → abstención (`concepto="composicion"`).

- [ ] **Step 1: failing test** (monkeypatch `ratios.proy_service.composicion_gasto_real`):

```python
# backend/tests/cfo/calc/test_ratios.py
from decimal import Decimal
import pytest
from app.cfo.calc import ratios

@pytest.mark.asyncio
async def test_composicion_gasto_pcts(monkeypatch):
    from app.proyeccion.service import ComposicionGasto
    async def fake(*, ventana):
        return ComposicionGasto(ventana="cerrado", meses=["2026-07"],
            por_grupo={"costo_producto":Decimal("0"),"operacion":Decimal("600000"),
                       "nomina":Decimal("3400000"),"deudas_obligaciones":Decimal("1000000"),
                       "otros":Decimal("0")}, total=Decimal("5000000"))
    monkeypatch.setattr(ratios.proy_service, "composicion_gasto_real", fake)
    rs = await ratios.composicion_gasto(ventana="cerrado")
    by = {r.concepto: r for r in rs}
    assert by["gasto_total_comp"].valor == Decimal("5000000")
    assert by["cop_nomina"].valor == Decimal("3400000")
    assert by["pct_nomina"].valor == Decimal("68.0")   # 3.4M/5M*100
    assert by["pct_nomina"].unidad == "%"
    assert by["pct_deudas"].valor == Decimal("20.0")   # 1M/5M*100
    assert all(r.disponible for r in rs)

@pytest.mark.asyncio
async def test_composicion_abstiene_sin_gasto(monkeypatch):
    from app.proyeccion.service import ComposicionGasto
    async def fake(*, ventana):
        return ComposicionGasto(ventana="curso", meses=["2026-08"], por_grupo={}, total=Decimal("0"))
    monkeypatch.setattr(ratios.proy_service, "composicion_gasto_real", fake)
    rs = await ratios.composicion_gasto(ventana="curso")
    assert len(rs) == 1 and rs[0].disponible is False
```

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** `ratios.py` (imports SOLO: `from decimal import Decimal`; `from app.cfo.calc.evidencia import Evidencia, ResultadoCFO`; `from app.proyeccion import service as proy_service`; `from app.proyeccion.service import ProyeccionError`. NO escribir la subcadena "motor" en el archivo). Mapa `_SUF = {"costo_producto":"costo_producto","operacion":"operacion","nomina":"nomina","deudas_obligaciones":"deudas","otros":"otros"}`; `pct = (cop / total * Decimal("100")).quantize(Decimal("0.1"))`; `ref=f"{c.ventana}:{'|'.join(c.meses)}"`. Helper `_abstencion(concepto, ref)` (patrón tendencias).
- [ ] **Step 4: Run → PASS.** `ruff` limpio; `ratios.py` sin subcadena "motor"; sin `float(`.
- [ ] **Step 5: Commit** — `feat(cfo): calc composicion_gasto (% por grupo sobre gasto real)`.

---

### Task 4: Tool `composicion_gasto` + prompt + e2e (incl. `%` crudo BLOQUEADO) — `cfo/agente/` (4a)

**Files:** Modify `tools.py`, `prompt.py` · Test `test_tools.py`, `test_prompt.py`, `test_servicio.py`, `test_verificador.py`

**Interfaces:** wrapper `_composicion_gasto(entrada)` valida `ventana ∈ {cerrado,acumulado,curso}` → `ratios.composicion_gasto(ventana=...)`. Schema `required:["ventana"]`, `ventana` enum, `additionalProperties:false`.

- [ ] **Step 1: failing tests**
  - `test_tools.py`: `composicion_gasto` en `TOOLS_SCHEMA` (enum ventana, required); `ejecutar_tool("composicion_gasto",{"ventana":"cerrado"})` llega a la calc (monkeypatch `app.cfo.calc.ratios.composicion_gasto`); ventana inválida → raise.
  - `test_prompt.py`: menciona `composicion_gasto` + "porcentaje/%" + "cítalo, no lo calcules".
  - `test_verificador.py` (CRÍTICO): `verificar("la nómina es 45% de tu gasto", [])` → `ok is False` (un `%` CRUDO del modelo SIGUE bloqueado); `verificar("la nómina es [[pct_nomina]]", [<ResultadoCFO pct_nomina disponible>])` → `ok is True`.
  - `test_servicio.py` (e2e ClienteFake): el modelo pide `composicion_gasto`, cita `[[pct_nomina]]`/`[[cop_nomina]]`, texto con "%" sustituido (no `[[...]]`, no `%` propio); cifra/% cruda → reintento → abstención `motivo="verificacion"`. Monkeypatch `app.cfo.calc.ratios.composicion_gasto`.
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** — `import ratios`; `_composicion_gasto` (mismo molde que `_tendencia_real`); `DISPATCH` + `TOOLS_SCHEMA`; bloque de prompt (usar `composicion_gasto` para "¿qué % de mi gasto es…?"; cita `[[pct_*]]`/`[[cop_*]]`/`[[gasto_total_comp]]`; **el % ya viene calculado — cítalo con el token, NUNCA escribas un `%` propio ni lo calcules; si escribes un % a mano el sistema te rebota**).
- [ ] **Step 4: Run → PASS** + `tests/cfo -q` verde.
- [ ] **Step 5: Commit** — `feat(cfo): tool + prompt composicion_gasto (4a end-to-end, % por token)`.

---

### Task 5: `mix_activos` — `modelos_moto/service.py` (4b)

**Files:** Modify `backend/app/modelos_moto/service.py` · Test `backend/tests/modelos_moto/test_mix_activos.py` (o donde vivan los tests de modelos)

**Interfaces:** `async def mix_activos() -> list[tuple[str, Decimal]]`: `[(m.nombre, m.participacion_mix) for m in await listar_modelos(activo=True)]`.

- [ ] **Step 1: failing test** (mongomock; seed 2 modelos activos + 1 inactivo con `.insert()`, imitar un test existente de `tests/modelos_moto/` o `tests/test_*modelos*`): assert `mix_activos()` devuelve `[(nombre, participacion_mix)]` solo de los activos, en orden.
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** — función una-línea sobre `listar_modelos(activo=True)`. (Confirmar el import de `Decimal` si se usa en la firma/anotación.)
- [ ] **Step 4: Run → PASS** + `tests/modelos_moto -q` verde. `ruff` limpio.
- [ ] **Step 5: Commit** — `feat(modelos_moto): mix_activos (nombre + participacion_mix de modelos activos, valores planos)`.

---

### Task 6: Calc `mix_modelos` — `cfo/calc/ratios.py` (4b)

**Files:** Modify `backend/app/cfo/calc/ratios.py` · Test `backend/tests/cfo/calc/test_ratios.py` (añadir)

**Interfaces:**
- Consumes: `modelos_moto.service.mix_activos`.
- Produces: `async def mix_modelos() -> list[ResultadoCFO]`. `total = Σ participacion_mix`; `total<=0` → abstención (`concepto="mix"`, ref `"sin-mix"`); si no, por modelo `mix_{slug(nombre)}` (unidad `"%"`, `= participacion_mix/total*100` cuantizado 0.1; `slug = re.sub(r"\W+","_",nombre.lower()).strip("_")`). Evidencia `ref="share-normalizado"`.

- [ ] **Step 1: failing test** (monkeypatch `ratios.modelos_service.mix_activos`):

```python
@pytest.mark.asyncio
async def test_mix_modelos_normaliza(monkeypatch):
    async def fake():
        return [("Raider", Decimal("0.5")), ("Apache", Decimal("0.3")), ("Sport", Decimal("0.2"))]
    monkeypatch.setattr(ratios.modelos_service, "mix_activos", fake)
    rs = await ratios.mix_modelos()
    by = {r.concepto: r for r in rs}
    assert by["mix_raider"].valor == Decimal("50.0")
    assert by["mix_raider"].unidad == "%"
    assert by["mix_apache"].valor == Decimal("30.0")

@pytest.mark.asyncio
async def test_mix_modelos_normaliza_suma_distinta_de_uno(monkeypatch):
    async def fake():  # suman 0.8, no 1.0 -> normaliza por 0.8
        return [("Raider", Decimal("0.4")), ("Apache", Decimal("0.4"))]
    monkeypatch.setattr(ratios.modelos_service, "mix_activos", fake)
    by = {r.concepto: r for r in await ratios.mix_modelos()}
    assert by["mix_raider"].valor == Decimal("50.0")   # 0.4/0.8*100

@pytest.mark.asyncio
async def test_mix_modelos_abstiene_sin_mix(monkeypatch):
    async def fake(): return []
    monkeypatch.setattr(ratios.modelos_service, "mix_activos", fake)
    rs = await ratios.mix_modelos()
    assert len(rs) == 1 and rs[0].disponible is False
```

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** en `ratios.py`: `import re`; `from app.modelos_moto import service as modelos_service`. (Servicio, S1-ok; devuelve tuplas planas → NO se importa `ModeloMoto`.)
- [ ] **Step 4: Run → PASS.** `ruff` limpio; sin "motor"/`float(`.
- [ ] **Step 5: Commit** — `feat(cfo): calc mix_modelos (participacion normalizada por modelo, %)`.

---

### Task 7: Tool `mix_modelos` (no-param) + prompt + e2e — `cfo/agente/` (4b)

**Files:** Modify `tools.py`, `prompt.py` · Test `test_tools.py`, `test_prompt.py`, `test_servicio.py`

**Interfaces:** `mix_modelos` en `DISPATCH` DIRECTA a `ratios.mix_modelos` (no-param, como `rumbo_caja`); `TOOLS_SCHEMA` `input_schema:{type:"object",properties:{},additionalProperties:false}`.

- [ ] **Step 1: failing tests**: `test_tools.py` (mix_modelos en schema sin params; `ejecutar_tool("mix_modelos")` sin entrada llega a la calc — `monkeypatch.setitem(tools.DISPATCH,"mix_modelos",fake)` o mock de `ratios.modelos_service.mix_activos`, según cuál intercepte —); `test_prompt.py` (menciona `mix_modelos` + "mix"); `test_servicio.py` (e2e: cita `[[mix_raider]]` etc., `%` sustituido; `%` crudo → abstención).
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** — `DISPATCH["mix_modelos"] = ratios.mix_modelos`; `TOOLS_SCHEMA`; bloque de prompt (usar `mix_modelos` para "¿cómo está mi mix?"; cita `[[mix_<modelo>]]`; es share normalizado; NUNCA escribas un `%` propio).
- [ ] **Step 4: Run → PASS** + `tests/cfo -q` verde.
- [ ] **Step 5: Commit** — `feat(cfo): tool + prompt mix_modelos (4b end-to-end)`.

---

### Task 8: Cierre — regresión, guardas, roadmap

**Files:** Modify `docs/COMPAS_FABS_ROADMAP.md` · (verificación) toda la suite

- [ ] **Step 1: Regresión + guardas** (reportar salidas verbatim):
  - `cd backend && python -m pytest tests/cfo tests/proyeccion tests/modelos_moto -q`.
  - `python -m pytest tests/cfo/test_s1_aislamiento.py tests/cfo/agente/test_verificador.py -q` verde.
  - `ruff check app/cfo/ app/proyeccion/service.py app/modelos_moto/service.py` + `ruff format --check` limpios.
  - `git diff <MERGE_BASE=origin/main>..HEAD -- backend/app/proyeccion/motor.py backend/app/presupuesto/motor.py` VACÍO.
  - `grep -rn "float(" app/cfo/calc/ratios.py` sin resultados; `grep -c "motor" app/cfo/calc/ratios.py` = 0.
  - **Guarda del `%`:** confirmar que `verificador.verificar` con un `%` crudo del modelo da `ok=False` (el test crítico de la Task 4 debe estar verde) — el `%` de COMPAS NO debilitó el control.
  - **Guarda de colisión:** grep de los conceptos nuevos (`pct_*`,`cop_*`,`mix_*`,`gasto_total_comp`) en `app/cfo/calc/*.py` — sin colisión con rebanadas 1–3.
  - Confirmar `CONCEPTOS_CITABLES` borrado (grep 0 en `app/` y `tests/`).
- [ ] **Step 2: Cierre** — `docs/COMPAS_FABS_ROADMAP.md`: rebanada 4 construida (registro fechado; 2 tools composicion_gasto/mix_modelos; ABRE el `%` sin debilitar el verificador; gate-waiver + GO CEO; NADA de Kimi). NO tocar el `.xlsx` (lo hace el controlador post-SDD, verificando que no se clobbereen filas previas). Commit: `feat(cfo): cierre rebanada 4 ratios/mix (4a+4b, gate-waiver GO CEO)`.

---

## Self-Review (autor del plan)

**1. Cobertura del spec:** §5.1 composicion_gasto_real→T1 · §5.2 mix_activos→T5 · §5.3 calcs→T3/T6 · §5.4 formatear %+M3→T2 · §5.5 verificador docstring→T2 · §5.6 tools+prompt→T4/T7 · §6 conceptos namespaced→T3/T6 (+guarda T8) · §7 ventanas→T1 · §8 trampas (excluir ajuste en primario+partes→T1; expandir partes→T1; % lo computa la calc→T3/T6; mix normaliza→T6; namespaced→Global+T8; total 0→T3)→cubiertas · §9 abstención→T3/T6 · §10 pruebas (incl. `%` crudo bloqueado→T4/T8; formatear→T2)→cada task · §11 innegociables→Global+T8 · §12 sub-rebanadas→T1-4 / T5-7.

**2. Placeholders:** el seeding de T1/T5 dice "copiar el patrón de un test existente" (nombra el archivo + da los montos esperados) — instrucción concreta, no lógica pendiente; el resto trae código real.

**3. Consistencia de tipos:** `composicion_gasto_real(*, ventana) -> ComposicionGasto(ventana,meses,por_grupo,total)` (T1) ↔ `composicion_gasto` (T3, sufijos `_SUF`). `mix_activos() -> list[tuple[str,Decimal]]` (T5) ↔ `mix_modelos` (T6). Conceptos `pct_/cop_/gasto_total_comp` (T3) y `mix_*` (T6) idénticos en calc/tool/prompt/e2e. Verificador: solo docstring (T2), la guarda del `%` crudo (T4/T8) prueba que la lógica no cambió.

---
*Rebanada 4 del inc4. Ejecutar por SDD. Gate-waiver + GO CEO (NADA de Kimi, NUNCA simular). `motor.py` intocable. What-if de mix y composición proyectada → rebanadas siguientes.*
