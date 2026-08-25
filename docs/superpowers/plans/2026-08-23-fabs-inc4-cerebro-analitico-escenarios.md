# FABS inc4 · Rebanada 1 — What-if de escenarios (el caso de la bodega) · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que FABS responda un what-if de escenario (ej. "arriendo una bodega de $20M/mes") con impacto en caja, mes de quiebre y cuántas motos de más vender — corriendo el motor real de COMPAS, sin que el modelo haga aritmética.

**Architecture:** Aditivo sobre el motor (cero diffs). Un **solver de unidades** nuevo en `proyeccion/` (bisección entera que re-corre el motor variando motos). Un módulo `cfo/calc/escenario.py` que envuelve `proyeccion.service.proyectar_impactos` (impacto/mes de quiebre) y el solver (motos), devolviendo **varios** `ResultadoCFO` nombrados. El loop/tools de FABS se extienden a **tools con parámetros** y **múltiples resultados**; el verificador y el formateador aprenden la unidad `unidades`. La garantía anti-alucinación (el modelo cita `[[token]]`, nunca escribe cifras) se preserva.

**Tech Stack:** Python 3.12, FastAPI, Beanie/Motor, Pydantic strict, `decimal.Decimal`, pytest. FABS con `ClienteFake`/mocks (CI verde sin API key).

**Spec:** `docs/superpowers/specs/2026-08-23-fabs-inc4-cerebro-analitico-escenarios-design.md`

## Global Constraints

- **Dinero = Decimal, nunca float** (regla 1); montos como string en el borde/API; cero `float(` en la ruta nueva.
- **`motor.py` cero diffs.** Todo aditivo: nuevo solver + nuevas tools/calc, reusando `proyeccion.service` (`proyectar_impactos`, `proyectar_preview`) y `proyeccion.impactos.aplicar_impactos`.
- **El modelo NUNCA produce una cifra.** Cita `[[concepto]]`; el verificador rechaza cualquier número/unidad cruda + tokens no disponibles; el servicio sustituye tras verificar (orden verify→sustituir, jamás re-verifica).
- **S1:** `app/cfo/**` escribe solo `cfo_*`; las tools nuevas LEEN vía `proyeccion.service`/`parametros_proyeccion.service` (capa de servicios permitida) — nunca `app.domain.*` ni el driver directo.
- **Catálogo de auditoría:** SIN eventos nuevos (regla 11) — el Q&A de escenario reusa `cfo.consulta`/`cfo.respuesta`. No hay CR de catálogo.
- **Flag `CFO_ENABLED`:** ya encendido en piloto; con el flag apagado COMPAS es byte-idéntico. `ruff` limpio.
- **Gate:** gate-waiver con GO del CEO 2026-08-23 (Kimi de diseño y de código **retroactivos** pendientes — NUNCA simular que Kimi aprobó). Rama `feat/fabs-inc4-escenarios` (desde `main` `2511398`).
- **Branch guard:** verificar `git branch --show-current` == `feat/fabs-inc4-escenarios` antes de cada commit.
- Firmas del motor reusadas: `impactos.Ajuste(nombre, naturaleza∈{gasto,ingreso}, modo∈{absoluto,porcentaje}, valor:Decimal, mes_inicio:'YYYY-MM', mes_fin=None, rubro_id=None)`; `impactos.aplicar_impactos(r:ResultadoProyeccion, ajustes:list[Ajuste], caja_minima:Decimal) -> ResultadoAjustado(meses, kpis, delta_por_mes)`; `kpis.piso_caja`, `kpis.mes_mas_ajustado`; `ResultadoProyeccion.meses[i].{mes,caja,estado∈{ok,critico,negativo}}`; `service.proyectar_impactos(*, ajustes, escenario, mes_inicio, horizonte_meses) -> {base, ajustada, valles_base, valles_ajustada, delta_por_mes}` (dicts serializados, montos string, `piso_caja` incluido); `service.proyectar_preview(*, campos:dict, escenario, mes_inicio, horizonte_meses)`; `parametros_proyeccion.service.obtener_vigente() -> ParametrosProyeccion|None` con `.motos_base:int`, `.caja_minima:Decimal`; `ProyeccionError` (sin config).

---

### Task 1: Solver de unidades (puro, inyectable) — `proyeccion/solver_unidades.py`

**Files:**
- Create: `backend/app/proyeccion/solver_unidades.py`
- Test: `backend/tests/proyeccion/test_solver_unidades.py`

**Interfaces:**
- Consumes: `impactos.Ajuste`, `impactos.aplicar_impactos`, `motor.ResultadoProyeccion`.
- Produces: `resolver_unidades_para_umbral(proyectar_fn, ajustes, caja_minima, *, colchon=Decimal("0"), cap_unidades=10_000) -> UnidadesResultado`. `proyectar_fn: Callable[[int], ResultadoProyeccion]` (dado N unidades extra/mes, devuelve la proyección del motor). `UnidadesResultado(unidades_extra:int, alcanzable:bool, piso_resultante:Decimal|None, meta:Decimal)`. Pureza: NO toca la BD ni el servicio; el llamador inyecta `proyectar_fn` (así se testea con un fake y se re-usa el motor real en producción). Bisección ENTERA (unidades son enteros ≥ 0). Motor intocable.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/proyeccion/test_solver_unidades.py
from dataclasses import dataclass
from decimal import Decimal

import pytest

from app.proyeccion.solver_unidades import resolver_unidades_para_umbral


# Fake mínimo de ResultadoProyeccion: el solver solo necesita que aplicar_impactos
# corra sobre él. Para aislar el solver de aplicar_impactos, monkeypatcheamos el piso.
@dataclass
class _R:  # sustituto de ResultadoProyeccion para el fake
    piso: Decimal


def _piso_lineal(n: int) -> _R:
    # piso sube 1.000.000 por unidad extra, arranca en -5.000.000 (bajo el umbral 0)
    return _R(piso=Decimal(-5_000_000) + Decimal(1_000_000) * n)


def test_encuentra_minimo_de_unidades(monkeypatch):
    # aplicar_impactos(r, ajustes, caja_minima).kpis.piso_caja == r.piso (fake)
    monkeypatch.setattr(
        "app.proyeccion.solver_unidades._piso_con_ajustes",
        lambda r, ajustes, caja_minima: r.piso,
    )
    res = resolver_unidades_para_umbral(
        _piso_lineal, ajustes=[], caja_minima=Decimal("0")
    )
    assert res.alcanzable is True
    assert res.unidades_extra == 5  # -5M + 5*1M = 0 >= umbral 0
    assert res.piso_resultante == Decimal("0")


def test_ya_cumple_con_cero(monkeypatch):
    monkeypatch.setattr(
        "app.proyeccion.solver_unidades._piso_con_ajustes",
        lambda r, ajustes, caja_minima: r.piso,
    )
    res = resolver_unidades_para_umbral(
        lambda n: _R(piso=Decimal(10_000_000)), ajustes=[], caja_minima=Decimal("0")
    )
    assert res.unidades_extra == 0 and res.alcanzable is True


def test_no_alcanzable_dentro_del_tope(monkeypatch):
    monkeypatch.setattr(
        "app.proyeccion.solver_unidades._piso_con_ajustes",
        lambda r, ajustes, caja_minima: r.piso,
    )
    # piso jamás sube (aunque haya más unidades) → no alcanzable
    res = resolver_unidades_para_umbral(
        lambda n: _R(piso=Decimal(-1)), ajustes=[], caja_minima=Decimal("0"),
        cap_unidades=100,
    )
    assert res.alcanzable is False and res.unidades_extra == 0
```

- [ ] **Step 2: Run tests to verify they fail** — `cd backend && python -m pytest tests/proyeccion/test_solver_unidades.py -v` → FAIL (módulo inexistente).

- [ ] **Step 3: Implement**

```python
# backend/app/proyeccion/solver_unidades.py
"""Solver de UNIDADES (inc4 FABS): ¿cuántas motos de más por mes para que el piso de
caja no baje del umbral, dado un escenario de ajustes? A diferencia de los solvers de
`solvers.py` (que bisectan un Ajuste sobre un ResultadoProyeccion FIJO), aquí cada
candidato N RE-CORRE el motor (las unidades fluyen por cartera/mora/GPS), vía la
`proyectar_fn` que inyecta el llamador. Motor intocable; bisección ENTERA."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal

from app.proyeccion.impactos import Ajuste, aplicar_impactos
from app.proyeccion.motor import ResultadoProyeccion


@dataclass(frozen=True)
class UnidadesResultado:
    unidades_extra: int
    alcanzable: bool
    piso_resultante: Decimal | None
    meta: Decimal


def _piso_con_ajustes(
    r: ResultadoProyeccion, ajustes: Sequence[Ajuste], caja_minima: Decimal
) -> Decimal:
    # aislado en su propia función para poder fakearlo en los tests del solver
    return aplicar_impactos(r, list(ajustes), caja_minima).kpis.piso_caja


def resolver_unidades_para_umbral(
    proyectar_fn: Callable[[int], ResultadoProyeccion],
    ajustes: Sequence[Ajuste],
    caja_minima: Decimal,
    *,
    colchon: Decimal = Decimal("0"),
    cap_unidades: int = 10_000,
) -> UnidadesResultado:
    meta = caja_minima + colchon

    def piso(n: int) -> Decimal:
        return _piso_con_ajustes(proyectar_fn(n), ajustes, caja_minima)

    if piso(0) >= meta:
        return UnidadesResultado(0, True, piso(0), meta)
    # duplicar hasta pasar el tope o cumplir
    lo, hi = 0, 1
    while piso(hi) < meta:
        lo, hi = hi, hi * 2
        if hi > cap_unidades:
            return UnidadesResultado(0, False, None, meta)
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if piso(mid) >= meta:
            hi = mid
        else:
            lo = mid
    return UnidadesResultado(hi, True, piso(hi), meta)
```

- [ ] **Step 4: Run tests** → PASS. `python -m ruff check app/proyeccion/solver_unidades.py` limpio.

- [ ] **Step 5: Commit**
```bash
cd backend && git add app/proyeccion/solver_unidades.py tests/proyeccion/test_solver_unidades.py
git commit -m "feat(proyeccion): solver de unidades para umbral (bisección entera, motor intocable)"
```

---

### Task 2: Formateo de la unidad `unidades` + contexto de mes de quiebre — `cfo/agente/conceptos.py`

**Files:**
- Modify: `backend/app/cfo/agente/conceptos.py`
- Test: `backend/tests/cfo/agente/test_conceptos.py` (añadir)

**Interfaces:**
- Produces: `formatear` reconoce `unidad == "unidades"` → `"N motos"` (entero, sin decimales); y para conceptos COP con un mes de quiebre en `evidencia.ref` con prefijo `quiebre:` → añade el contexto `" (cruzas el umbral en YYYY-MM)"` o `" (no cruzas el umbral)"`. Cero float; el entero de unidades vía `int(Decimal)`.

- [ ] **Step 1: Write the failing test**

```python
# en backend/tests/cfo/agente/test_conceptos.py — añadir
from decimal import Decimal
from app.cfo.agente.conceptos import formatear
from app.cfo.calc.evidencia import Evidencia, ResultadoCFO


def _r(concepto, valor, unidad, ref=""):
    return ResultadoCFO(concepto=concepto, valor=Decimal(str(valor)), unidad=unidad,
        disponible=True, evidencia=Evidencia(fuente="x", fecha_corte=None, ref=ref))


def test_formatea_unidades_como_motos():
    assert formatear(_r("unidades_extra", 12, "unidades")) == "12 motos"


def test_piso_con_contexto_de_quiebre():
    # una cifra COP cuyo ref codifica el mes de quiebre
    out = formatear(_r("piso_con", 40000000, "COP", ref="quiebre:2026-11"))
    assert "$40.000.000" in out and "cruzas el umbral en 2026-11" in out


def test_piso_sin_quiebre():
    out = formatear(_r("piso_con", 40000000, "COP", ref="quiebre:nunca"))
    assert "$40.000.000" in out and "no cruzas el umbral" in out
```

- [ ] **Step 2: Run tests** → FAIL.

- [ ] **Step 3: Implement** — en `conceptos.py`, extender `formatear` (añadir ANTES del `return` COP genérico) y una función de unidades. Mantener intacto lo de `runway`/`iva_cuatrimestre`/`caja_hoy`:

```python
def _unidades_es(d: Decimal) -> str:
    return f"{int(d)} motos"

# dentro de formatear(r, hoy=None), tras el caso runway:
    if r.unidad == "unidades":
        return _unidades_es(r.valor)
    base = _money_es(r.valor)
    ref = r.evidencia.ref or ""
    if ref.startswith("quiebre:"):
        mes = ref.split(":", 1)[1]
        ctx = "no cruzas el umbral" if mes == "nunca" else f"cruzas el umbral en {mes}"
        return f"{base} ({ctx})"
    if r.concepto == "iva_cuatrimestre":
        ...  # (sin cambios)
```
(Reordenar `formatear` para: runway → unidades → quiebre-COP → iva → caja/COP genérico. NO tocar la lógica de iva/caja/runway existentes.)

- [ ] **Step 4: Run tests** → PASS + los tests EXISTENTES de conceptos siguen verdes. `ruff` limpio.

- [ ] **Step 5: Commit**
```bash
cd backend && git add app/cfo/agente/conceptos.py tests/cfo/agente/test_conceptos.py
git commit -m "feat(cfo): formatear unidad 'unidades' (motos) + contexto de mes de quiebre"
```

---

### Task 3: Verificador rechaza unidades crudas — `cfo/agente/verificador.py`

**Files:**
- Modify: `backend/app/cfo/agente/verificador.py`
- Test: `backend/tests/cfo/agente/test_verificador.py` (añadir)

**Interfaces:**
- Produces: `extraer_cifras` detecta `N motos/moto/unidad/unidades/motocicletas` como cifra cruda (tipo `"unidades"`) → `verificar` la rechaza (el modelo debe citar `[[unidades_extra]]`, no escribir "12 motos"). Cierra el hueco del entero pequeño para el caso de unidades.

- [ ] **Step 1: Write the failing test**

```python
# en backend/tests/cfo/agente/test_verificador.py — añadir
from app.cfo.agente.verificador import verificar
from app.cfo.calc.evidencia import Evidencia, ResultadoCFO
from decimal import Decimal


def _disp(concepto, unidad="unidades", valor=12):
    return ResultadoCFO(concepto=concepto, valor=Decimal(valor), unidad=unidad,
        disponible=True, evidencia=Evidencia(fuente="x", fecha_corte=None, ref="r"))


def test_rechaza_unidades_crudas():
    v = verificar("Vende 12 motos más.", [_disp("unidades_extra")])
    assert v.ok is False and any("12 motos" in c for c in v.cifras_sin_evidencia)


def test_acepta_token_de_unidades():
    v = verificar("Vende [[unidades_extra]] más.", [_disp("unidades_extra")])
    assert v.ok is True
```

- [ ] **Step 2: Run tests** → FAIL (hoy "12 motos" no se detecta: 12 < 5 dígitos).

- [ ] **Step 3: Implement** — en `verificador.py`, añadir el regex y su barrido (mismo patrón que `_RE_MESES`/`_RE_PORCENTAJE`, marcando tramo para no re-contar):

```python
_RE_UNIDADES = re.compile(r"\d+\s*(?:motos?|motocicletas?|unidades?)\b", re.IGNORECASE)
# ... en extraer_cifras, junto a los barridos de meses/%:
for m in _RE_UNIDADES.finditer(texto):
    cifras.append((Decimal(0), "unidades", m.group(0)))
    tramos.append((m.start(), m.end()))
```
(Colocarlo con los otros barridos `tramos`, ANTES del barrido de `_RE_NUM`, para que "12 motos" no se re-cuente como COP.)

- [ ] **Step 4: Run tests** → PASS + los tests EXISTENTES del verificador verdes. `ruff` limpio.

- [ ] **Step 5: Commit**
```bash
cd backend && git add app/cfo/agente/verificador.py tests/cfo/agente/test_verificador.py
git commit -m "feat(cfo): el verificador rechaza unidades crudas (N motos/unidades)"
```

---

### Task 4: Loop + tools soportan parámetros y múltiples resultados — `cfo/agente/{tools,loop}.py`

**Files:**
- Modify: `backend/app/cfo/agente/tools.py`, `backend/app/cfo/agente/loop.py`
- Test: `backend/tests/cfo/agente/test_tools.py`, `backend/tests/cfo/agente/test_loop.py` (añadir)

**Interfaces:**
- Produces: `ejecutar_tool(nombre: str, entrada: dict | None = None) -> list[ResultadoCFO]` (antes: sin `entrada`, devolvía UN `ResultadoCFO`). Las tools de un solo concepto envuelven su resultado en lista (`[r]`). El loop pasa `u.input` y hace `resultados.extend(...)`, y el `tool_result` lleva un **array** JSON de `resultado_a_dict`. `resultado_a_dict` sin cambios (sigue sin `valor`/`detalle`).

- [ ] **Step 1: Write the failing test**

```python
# en backend/tests/cfo/agente/test_tools.py — añadir
import pytest
from app.cfo.agente import tools
from app.cfo.calc.evidencia import ResultadoCFO


@pytest.mark.asyncio
async def test_ejecutar_tool_devuelve_lista(monkeypatch):
    r = await tools.ejecutar_tool("caja_disponible_hoy")
    assert isinstance(r, list) and all(isinstance(x, ResultadoCFO) for x in r)


@pytest.mark.asyncio
async def test_tool_desconocida_es_error():
    with pytest.raises(Exception):
        await tools.ejecutar_tool("no_existe")
```

- [ ] **Step 2: Run tests** → FAIL (hoy devuelve un `ResultadoCFO`, no lista; y `ejecutar_tool` no acepta `entrada`).

- [ ] **Step 3: Implement**
- `tools.py`: `ejecutar_tool(nombre, entrada=None)` → busca en `DISPATCH`; si la firma de la calc no toma args, la llama sin `entrada`; normaliza el retorno a `list[ResultadoCFO]` (si devuelve uno, `[r]`). Mantener el dispatcher cerrado (KeyError/ValueError si `nombre` no existe). Las 3 tools actuales siguen registradas.
- `loop.py`: en el bucle de `usos`, `rs = await ejecutar_tool(u.nombre, u.input)`; `resultados.extend(rs)`; `contenido_tool.append({"type":"tool_result","tool_use_id":u.id,"content": json.dumps([resultado_a_dict(x) for x in rs], ensure_ascii=False)})`.

- [ ] **Step 4: Run tests** → PASS + `tests/cfo/agente/test_loop.py` y `test_servicio.py` existentes verdes (las 3 tools de cero-arg siguen funcionando). `ruff` limpio.

- [ ] **Step 5: Commit**
```bash
cd backend && git add app/cfo/agente/tools.py app/cfo/agente/loop.py tests/cfo/agente/test_tools.py tests/cfo/agente/test_loop.py
git commit -m "feat(cfo): tools con parámetros + múltiples resultados por tool (loop extiende resultados)"
```

---

### Task 5: `cfo/calc/escenario.py` — impacto + mes de quiebre (envuelve `proyectar_impactos`)

**Files:**
- Create: `backend/app/cfo/calc/escenario.py`
- Test: `backend/tests/cfo/calc/test_escenario.py`

**Interfaces:**
- Consumes: `proyeccion.service.proyectar_impactos`, `ProyeccionError`, `impactos.Ajuste`, `core.time.now_bogota`.
- Produces: `async impacto_escenario(*, naturaleza:str, monto:Decimal, mes_inicio:str, mes_fin:str|None=None) -> list[ResultadoCFO]`. Nombres de concepto: `impacto_mensual` (COP), `piso_sin` (COP), `piso_con` (COP, `evidencia.ref="quiebre:<YYYY-MM|nunca>"` = primer mes `estado!="ok"` de la serie ajustada). Sin config vigente (`ProyeccionError`) → un solo `ResultadoCFO(disponible=False, ...)` con `ref="sin-config"`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/cfo/calc/test_escenario.py
from decimal import Decimal
import pytest
from app.cfo.calc import escenario


@pytest.mark.asyncio
async def test_impacto_arma_conceptos_y_mes_de_quiebre(monkeypatch):
    async def fake_impactos(*, ajustes, escenario, mes_inicio, horizonte_meses):
        return {
            "base": {"piso_caja": "100000000"},
            "ajustada": {
                "piso_caja": "40000000",
                "meses": [
                    {"mes": "2026-09", "estado": "ok", "caja": "90000000"},
                    {"mes": "2026-10", "estado": "ok", "caja": "60000000"},
                    {"mes": "2026-11", "estado": "critico", "caja": "40000000"},
                ],
            },
            "delta_por_mes": ["-20000000", "-20000000", "-20000000"],
        }
    monkeypatch.setattr(escenario.proy_service, "proyectar_impactos", fake_impactos)
    rs = await escenario.impacto_escenario(
        naturaleza="gasto", monto=Decimal("20000000"), mes_inicio="2026-09"
    )
    by = {r.concepto: r for r in rs}
    assert by["piso_sin"].valor == Decimal("100000000")
    assert by["piso_con"].valor == Decimal("40000000")
    assert by["piso_con"].evidencia.ref == "quiebre:2026-11"
    assert by["impacto_mensual"].valor == Decimal("20000000")
    assert all(r.disponible for r in rs)


@pytest.mark.asyncio
async def test_impacto_abstiene_sin_config(monkeypatch):
    async def boom(**kw):
        raise escenario.ProyeccionError("sin config")
    monkeypatch.setattr(escenario.proy_service, "proyectar_impactos", boom)
    rs = await escenario.impacto_escenario(
        naturaleza="gasto", monto=Decimal("20000000"), mes_inicio="2026-09"
    )
    assert len(rs) == 1 and rs[0].disponible is False
```

- [ ] **Step 2: Run tests** → FAIL.

- [ ] **Step 3: Implement** — `escenario.py`: construir el `Ajuste`, llamar `proyectar_impactos`, escanear `ajustada["meses"]` por el primer `estado != "ok"` (→ `quiebre:<mes>`, o `quiebre:nunca`), y armar los `ResultadoCFO` con `Decimal(...)` sobre los strings (regla 1). Patrón de abstención igual a `runway.py` (try/except `ProyeccionError`). `escenario=` fijo `"base"`, `mes_inicio=(año,mes)` de `now_bogota`, `horizonte_meses=None`. Evidencia: `fuente="proyeccion.service.proyectar_impactos"`, `ref` según arriba.

- [ ] **Step 4: Run tests** → PASS. `ruff` limpio.

- [ ] **Step 5: Commit**
```bash
cd backend && git add app/cfo/calc/escenario.py tests/cfo/calc/test_escenario.py
git commit -m "feat(cfo): calc de escenario — impacto en flujo + mes de quiebre (envuelve proyectar_impactos)"
```

---

### Task 6: `escenario.motos_para_evitar_umbral` — envuelve el solver con `proyectar_preview`

**Files:**
- Modify: `backend/app/cfo/calc/escenario.py`
- Test: `backend/tests/cfo/calc/test_escenario.py` (añadir)

**Interfaces:**
- Consumes: `solver_unidades.resolver_unidades_para_umbral`, `parametros_proyeccion.service.obtener_vigente`, y el camino que produce un `ResultadoProyeccion` crudo desde `ParametrosProyeccion` propuesto (ver `proyeccion.service.proyectar_preview` / `_resultado_con`).
- Produces: `async motos_para_evitar_umbral(*, naturaleza, monto, mes_inicio, mes_fin=None) -> list[ResultadoCFO]`. Conceptos: `unidades_extra` (unidad `"unidades"`, `valor=Decimal(N)`), `piso_con_unidades` (COP). Si `alcanzable=False` → `unidades_extra` con `disponible=False` (abstención honesta) y una evidencia que explique el tope. Sin config → abstención.

- [ ] **Step 1: Write the failing test** — con `proyectar_fn` y solver fakeados:

```python
# en test_escenario.py — añadir
@pytest.mark.asyncio
async def test_motos_devuelve_unidades_y_piso(monkeypatch):
    from app.proyeccion.solver_unidades import UnidadesResultado
    monkeypatch.setattr(escenario, "_proyectar_fn_para", lambda vig, esc, mi, hm: (lambda n: n))
    monkeypatch.setattr(escenario, "resolver_unidades_para_umbral",
        lambda proyectar_fn, ajustes, caja_minima, **kw:
            UnidadesResultado(unidades_extra=12, alcanzable=True,
                              piso_resultante=Decimal("5000000"), meta=Decimal("0")))
    monkeypatch.setattr(escenario.params_service, "obtener_vigente",
        _fake_vigente(caja_minima=Decimal("0")))
    rs = await escenario.motos_para_evitar_umbral(
        naturaleza="gasto", monto=Decimal("20000000"), mes_inicio="2026-09")
    by = {r.concepto: r for r in rs}
    assert by["unidades_extra"].valor == Decimal("12") and by["unidades_extra"].unidad == "unidades"
    assert by["piso_con_unidades"].valor == Decimal("5000000")
```
(Definir el helper `_fake_vigente` en el test: un objeto con `.caja_minima` y `.motos_base`.)

- [ ] **Step 2: Run tests** → FAIL.

- [ ] **Step 3: Implement** — `motos_para_evitar_umbral`: obtener params vigentes (abstención si None), construir el `Ajuste` del escenario, construir `proyectar_fn(n)` que llama a `proyectar_preview` con los `campos` de vigente + `motos_base + n` y devuelve el `ResultadoProyeccion` crudo (usar el camino interno tipo `service._resultado_con`; envolver en un helper `_proyectar_fn_para` para poder fakearlo), llamar `resolver_unidades_para_umbral`, y armar los `ResultadoCFO`. `disponible=alcanzable`.

- [ ] **Step 4: Run tests** → PASS. `ruff` limpio. (Nota: la integración real con Mongo/preview se cubre en el golden/regresión de la Task 9; aquí se testea la lógica del wrapper con fakes.)

- [ ] **Step 5: Commit**
```bash
cd backend && git add app/cfo/calc/escenario.py tests/cfo/calc/test_escenario.py
git commit -m "feat(cfo): calc de escenario — solver de motos para no cruzar el umbral"
```

---

### Task 7: Registrar las tools de escenario (parametrizadas) — `cfo/agente/tools.py`

**Files:**
- Modify: `backend/app/cfo/agente/tools.py`
- Test: `backend/tests/cfo/agente/test_tools.py` (añadir)

**Interfaces:**
- Produces: dos entradas nuevas en `DISPATCH` + `TOOLS_SCHEMA`: `impacto_escenario` y `motos_para_evitar_umbral`, con `input_schema` estricto: `{ naturaleza: enum["gasto","ingreso"], monto: string, mes_inicio: string "YYYY-MM", mes_fin?: string }`, `additionalProperties:false`, `required:[naturaleza,monto,mes_inicio]`. El dispatcher parsea `monto` string→`Decimal` (error explícito si inválido, regla 1) y llama la calc. Dispatcher sigue cerrado.

- [ ] **Step 1: Write the failing test**

```python
# en test_tools.py — añadir
import pytest
from app.cfo.agente import tools


def test_schema_incluye_tools_de_escenario():
    nombres = {t["name"] for t in tools.TOOLS_SCHEMA}
    assert {"impacto_escenario", "motos_para_evitar_umbral"} <= nombres
    imp = next(t for t in tools.TOOLS_SCHEMA if t["name"] == "impacto_escenario")
    assert imp["input_schema"]["additionalProperties"] is False
    assert set(imp["input_schema"]["required"]) == {"naturaleza", "monto", "mes_inicio"}


@pytest.mark.asyncio
async def test_impacto_escenario_parsea_monto(monkeypatch):
    llamado = {}
    async def fake_calc(*, naturaleza, monto, mes_inicio, mes_fin=None):
        llamado.update(monto=monto)
        return []
    monkeypatch.setitem(tools.DISPATCH, "impacto_escenario", None)  # placeholder
    monkeypatch.setattr("app.cfo.calc.escenario.impacto_escenario", fake_calc)
    await tools.ejecutar_tool("impacto_escenario",
        {"naturaleza": "gasto", "monto": "20000000", "mes_inicio": "2026-09"})
    from decimal import Decimal
    assert llamado["monto"] == Decimal("20000000")
```
(Ajustar el wiring del dispatcher en la implementación para que `ejecutar_tool` sepa parsear/mapear `entrada` a los kwargs de la calc de escenario; el test valida el contrato de parseo de `monto`.)

- [ ] **Step 2: Run tests** → FAIL.

- [ ] **Step 3: Implement** — añadir al `DISPATCH` un envoltorio por tool de escenario que tome `entrada: dict`, valide/parses `monto` a `Decimal`, y llame a `escenario.impacto_escenario`/`escenario.motos_para_evitar_umbral` con kwargs; añadir sus `TOOLS_SCHEMA`. Las tools de cero-arg quedan igual (su envoltorio ignora `entrada`).

- [ ] **Step 4: Run tests** → PASS. `ruff` limpio.

- [ ] **Step 5: Commit**
```bash
cd backend && git add app/cfo/agente/tools.py tests/cfo/agente/test_tools.py
git commit -m "feat(cfo): registra tools de escenario (impacto + motos) con input_schema estricto"
```

---

### Task 8: Prompt — enseñar los escenarios y reforzar "cita, no calcules" — `cfo/agente/prompt.py`

**Files:**
- Modify: `backend/app/cfo/agente/prompt.py`
- Test: `backend/tests/cfo/agente/test_prompt.py` (añadir aserciones de contenido)

**Interfaces:**
- Produces: el `SYSTEM_PROMPT` menciona las tools de escenario y **exige** citar `[[impacto_mensual]]`/`[[piso_con]]`/`[[piso_sin]]`/`[[unidades_extra]]`/`[[piso_con_unidades]]` (nunca escribir montos, meses ni cantidades). Sin cambiar el contrato existente (regla 1: el modelo no calcula).

- [ ] **Step 1: Write the failing test** — aserción de que el prompt menciona los nuevos conceptos y la regla de no escribir "N motos".

- [ ] **Step 2: Run test** → FAIL.

- [ ] **Step 3: Implement** — añadir un bloque al prompt (los conceptos de escenario + ejemplo de citación multi-valor). NO tocar la regla #1 ni la mecánica.

- [ ] **Step 4: Run tests** → PASS. Los tests existentes de prompt verdes (ojo al nit N-1 ya cerrado). `ruff` limpio.

- [ ] **Step 5: Commit**
```bash
cd backend && git add app/cfo/agente/prompt.py tests/cfo/agente/test_prompt.py
git commit -m "feat(cfo): prompt enseña escenarios y refuerza citación multi-valor"
```

---

### Task 9: Integración end-to-end + golden + cierre (regresión, gate-waiver, roadmap)

**Files:**
- Test: `backend/tests/cfo/agente/test_servicio.py` (añadir un caso de escenario con `ClienteFake`)
- Test/golden: `backend/tests/cfo/test_escenario_golden.py` (o extender `cfo/goldens/`)
- Modify: `docs/COMPAS_FABS_ROADMAP.md`

**Interfaces:**
- Consumes: todo lo anterior. Prueba que una pregunta de escenario → loop llama las tools → verificador OK → sustitución → respuesta con los valores nombrados. Y un golden con un escenario de referencia (bodega 20M) cuyo impacto/piso/mes/motos se conocen "al peso".

- [ ] **Step 1: Write the failing tests**
  - `test_servicio.py`: guionar un `ClienteFake` que (1) pida `impacto_escenario` y `motos_para_evitar_umbral`, (2) responda citando los tokens; monkeypatch de `escenario.*` para valores conocidos; aserción de que `r.texto` trae los valores sustituidos (`$…`, `… motos`) y `r.abstuvo is False`; y un caso donde el modelo intenta escribir "12 motos" crudo → reintento → abstención.
  - Golden: un `ParametrosProyeccion`/escenario fijo → `impacto_escenario`/`motos_para_evitar_umbral` con resultado esperado exacto (Decimal).

- [ ] **Step 2: Run tests** → FAIL.

- [ ] **Step 3: Implement** — ajustes finos que falten para que el end-to-end pase (no lógica nueva mayor). Sembrar el golden.

- [ ] **Step 4: Regresión + guardas**
```bash
cd backend && python -m pytest -q            # toda la suite verde
cd backend && python -m ruff check app/cfo/ app/proyeccion/solver_unidades.py
cd backend && git diff 2511398..HEAD -- app/proyeccion/motor.py app/presupuesto/motor.py   # VACÍO
cd backend && grep -rn "float(" app/cfo/calc/escenario.py app/proyeccion/solver_unidades.py || echo "sin float OK"
```
Reportar la línea exacta passed/skipped/failed. `motor.py` DEBE dar 0 diffs.

- [ ] **Step 5: Cierre** — actualizar `docs/COMPAS_FABS_ROADMAP.md` (inc4 rebanada 1 construida; **gate-waiver GO CEO 2026-08-23, Kimi diseño+código retroactivos pendientes** — NUNCA simular Kimi). El paquete Kimi (diff completo embebido) lo arma el controlador post-SDD. Branch guard antes del commit.
```bash
cd backend && git add ../docs/COMPAS_FABS_ROADMAP.md tests/
git commit -m "feat(cfo): escenarios what-if end-to-end + golden + cierre rebanada 1 (gate-waiver GO CEO)"
```

---

## Self-Review (autor del plan)

**1. Cobertura del spec:** §4 impacto→T5 · §4 mes de quiebre→T5 (scan estado) · §5.1 solver unidades→T1 · §5.2 tools parametrizadas→T4+T7 · §5.3 citación multi-valor→T2(formatear)+T3(verificador)+T4(loop/tools) · §6 formas→T5/T6 · §7 ancla (caja configurada)→T5/T6 (sin override; fast-follow) · §8 trampas (no runway para quiebre; no gastos_recurrentes)→T5 usa estado/valles + Ajuste · §9 abstención→T5/T6 · §10 pruebas→cada task + T9 · §11 innegociables→Global Constraints + T9.

**2. Placeholders:** los tests traen código real. "Camino interno tipo `_resultado_con`" (T6) es una referencia precisa a una función existente del repo (service.py:425), con el test definiendo el comportamiento del wrapper — no lógica pendiente.

**3. Consistencia de tipos:** `resolver_unidades_para_umbral(proyectar_fn, ajustes, caja_minima, *, colchon, cap_unidades) -> UnidadesResultado(unidades_extra:int, alcanzable, piso_resultante, meta)` (T1) usado en T6; `ejecutar_tool(nombre, entrada=None) -> list[ResultadoCFO]` (T4) usado en T7 y loop; `impacto_escenario`/`motos_para_evitar_umbral` (T5/T6) registradas en T7; unidad `"unidades"` (T2/T3/T6) coherente; conceptos `piso_con`/`piso_sin`/`impacto_mensual`/`unidades_extra`/`piso_con_unidades` idénticos en T5/T6/T8/T9.

---
*Rebanada 1 del inc4. Ejecutar por SDD. Gate-waiver GO CEO 2026-08-23; Kimi retroactivo pendiente (NUNCA simular). Merge: OJO flag ENCENDIDO en piloto → decidir con el CEO cómo soltar (verificación extra / sub-gate) antes de mergear a main. `motor.py` intocable.*
