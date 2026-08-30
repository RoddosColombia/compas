# FABS inc4 · Rebanada 3 — Tendencias · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que FABS responda por conversación cómo viene lo REAL en el tiempo — tendencia mes-a-mes de ingreso/gasto/caja, rumbo de caja hacia el umbral, y real vs. presupuesto — con cifras reales, su delta y su dirección, con evidencia y sin que el modelo calcule.

**Architecture:** Tres capacidades aditivas sobre servicios existentes. Se agregan agregaciones de actuals mensuales en `proyeccion/service.py` y un `real_vs_presupuesto_mes` en `presupuesto/service.py` (devuelven dataclasses PLANOS → S1). En `cfo/calc/tendencias.py` (nuevo) tres calcs envuelven esos servicios en `ResultadoCFO`; `tools.py` registra 3 tools; el prompt las enseña. La DIRECCIÓN (sube/baja/sobre/bajo) la computa COMPAS y viaja en `evidencia.ref` (patrón del caveat de plazo).

**Tech Stack:** Python 3.12, FastAPI, Beanie/Motor, MongoDB, Pydantic strict, `decimal.Decimal`, pytest. FABS con `ClienteFake`/mocks (CI verde sin API key).

**Spec:** `docs/superpowers/specs/2026-08-29-fabs-inc4-rebanada3-tendencias-design.md`

## Global Constraints

- **Dinero = `decimal.Decimal`, nunca float.** `comparar_vigente`/`proyectar_vigente` devuelven **money-STRINGS** → `Decimal(...)` al leerlos; cero `float(` en la ruta nueva.
- **`motor.py` cero diffs.** Verificar `git diff <MERGE_BASE>..HEAD -- backend/app/proyeccion/motor.py backend/app/presupuesto/motor.py` vacío.
- **S1:** `cfo/**` NO importa `app.domain.*`/`proyeccion.motor`/driver — solo servicios (`proyeccion.service`, `presupuesto.service`, `core.time`, `cfo.calc.evidencia`). Las agregaciones viven en `proyeccion`/`presupuesto` service y devuelven valores planos. `tests/cfo/test_s1_aislamiento.py` verde (OJO: su regex prohíbe la subcadena literal `motor` en cualquier archivo de `cfo/`).
- **El modelo NUNCA produce una cifra.** Cita `[[token]]`; el verificador rechaza cifras/mes/conteo crudos; el servicio sustituye tras verificar. **SIN `%`** (rebanada 4). La dirección va en `ref="direccion:<...>"`, es una palabra, no una cifra.
- **Conceptos NAMESPACED desde el día 1** (lección rebanada 2, `sustituir_tokens` = `{r.concepto: r}` last-wins): nada que colisione con conceptos existentes (`caja_hoy`,`runway`,`iva_cuatrimestre`,`piso_sin`,`piso_con`,`impacto_mensual`,`piso_sin_palanca`,`piso_con_palanca`,`impacto_palanca`,`unidades_extra`,`piso_con_unidades`). **`delta_caja_real` (3a, metrica=caja) y `delta_caja_rumbo` (3b) van con nombres DISTINTOS** para eliminar la colisión que el spec §6 marcó.
- **Excluir el rubro sistema "Ajuste de conciliación"** de toda suma de actuals (igual que `_caja_libro`).
- **Catálogo de auditoría: sin eventos nuevos** (reusa `cfo.consulta`/`cfo.respuesta`). Flag `CFO_ENABLED`. `ruff check` + `ruff format --check` limpios. Gate = **gate-waiver + GO CEO** (NADA de Kimi; NUNCA simular).
- **Branch guard:** `git branch --show-current` == `feat/fabs-inc4-rebanada3-tendencias` antes de cada commit. Rama desde `main`.

### Firmas reales verificadas (para reusar/imitar)
- `cierre.service._caja_libro(mes_id: PydanticObjectId, rubro_ajuste_id, saldo_inicial: Decimal) -> Decimal`: `total = saldo_inicial; async for t in Transaccion.find(Transaccion.mes_id == mes_id): if t.rubro_id == rubro_ajuste_id: continue; total += _signo(t)`. `_signo(t) = t.valor if t.tipo_flujo == TipoFlujo.INGRESO else -t.valor`.
- `cierre.service._rubro_ajuste() -> Rubro` (busca `Rubro.nombre == "Ajuste de conciliación", es_sistema == True`; usar `.id`). Importar: `from app.cierre.service import _caja_libro, _rubro_ajuste`.
- `proyeccion.service._actuals_por_mes(rubro_ajuste_id) -> list[tuple[MesControl, Decimal]]` (todos los MesControl asc por `mes`).
- `proyeccion.service.comparar_vigente(*, escenario: str, ancla_modo: str, horizonte_meses: int|None, mes_inicio_defecto: tuple[int,int]) -> dict` → `{"ancla": None|{"mes","caja_real"(str)}, "actuals":[{"mes":"YYYY-MM","caja_real":str}], "forecast":[{"mes","caja":str}]}`. `ANCLA_MODOS = ("cerrado","movimientos")`.
- `proyeccion.service.proyectar_vigente(*, escenario, mes_inicio, horizonte_meses) -> dict` → `data["piso_caja"]`(str), `data["meses"][i]["mes"]`, `data["meses"][i]["estado"]` (`ok|critico|negativo|atencion`), `data["runway_meses"]`.
- `presupuesto.service._ejecutados_por_rubro_mes(mes_ids, rubro_ids) -> dict[(str,str),Decimal]` (EGRESO, cerrado, expande `partes` vía `pares_clasificacion`).
- Presupuesto aprobado: `PresupuestoLinea` (`app/domain/presupuesto.py`) con `mes_id`, `rubro_id`, `vigente: bool`, `monto_definido: Money|None` (null hasta aprobar). Leer: `PresupuestoLinea.find(PresupuestoLinea.mes_id == mes_id, PresupuestoLinea.vigente == True)`.
- `Transaccion` (`app/domain/transaccion.py`): `mes_id`, `rubro_id`, `tipo_flujo: TipoFlujo(EGRESO="egreso"/INGRESO="ingreso")`, `valor: Money`(>0), `partes: list[ParteClasificacion]|None`. `MesControl`: `mes`("YYYY-MM-01"), `estado: EstadoMes(CERRADO="cerrado")`, `saldo_inicial_caja: Money`.
- `cfo.calc.evidencia.ResultadoCFO(concepto:str, valor:Money|None, unidad:str, disponible:bool, evidencia:Evidencia, detalle:dict={})`; `Evidencia(fuente:str, fecha_corte:str|None, ref:str)`.
- Patrón calc (imitar): `cfo/calc/runway.py` (no-arg, abstención `ProyeccionError`), `cfo/calc/palanca.py` (multi-concepto + ref markers). Patrón tool no-param: `caja_disponible_hoy` (`input_schema:{type:object, properties:{}, additionalProperties:false}`, cableada directo en `DISPATCH`; `ejecutar_tool` llama `calc()` si la firma no tiene params). Patrón tool con-param: `_simular_palanca(entrada: dict)` + `_kwargs_*`.

---

### Task 1: `actuals_mensuales` + helpers de ingreso/gasto real — `proyeccion/service.py` (3a)

**Files:** Modify `backend/app/proyeccion/service.py` · Test `backend/tests/proyeccion/test_actuals_mensuales.py`

**Interfaces — Produces:**
- `@dataclass(frozen=True) ActualMes(mes: str, ingreso_real: Decimal, gasto_real: Decimal, caja_real: Decimal)` (`mes` = "YYYY-MM").
- `async def _ingreso_real_mes(mes_id) -> Decimal` (Σ `valor` de Transaccion INGRESO del mes) y `async def _egreso_real_mes(mes_id, rubro_ajuste_id) -> Decimal` (Σ `valor` de Transaccion EGRESO del mes, excluyendo el rubro ajuste por `rubro_id` primario — mismo criterio que `_caja_libro`).
- `async def actuals_mensuales(*, meses: int = 3) -> list[ActualMes]`: últimos `meses` con movimientos, cronológico asc.

- [ ] **Step 1: failing test** (seed real de MesControl+Rubro+Transaccion; imitar el harness Beanie de `backend/tests/cierre/` o `backend/tests/presupuesto/` — marca `requires_real_mongo` si esos tests la usan). Sembrar 2 meses: 2026-06 (ingreso 3.000.000, egreso 1.000.000, + 1 tx al rubro Ajuste que NO debe contar) y 2026-07 (ingreso 5.000.000, egreso 2.000.000):

```python
# backend/tests/proyeccion/test_actuals_mensuales.py
from decimal import Decimal
import pytest
from app.proyeccion import service as svc
# ... imports del harness Beanie + factories de MesControl/Rubro/Transaccion como en tests/cierre/

@pytest.mark.asyncio
async def test_actuals_mensuales_suma_por_tipo_excluye_ajuste(db):  # `db` = fixture Beanie del harness
    # sembrar rubro ajuste (nombre 'Ajuste de conciliación', es_sistema=True), un rubro INGRESO,
    # un rubro EGRESO normal; dos MesControl (2026-06-01, 2026-07-01, estado cerrado, saldo_inicial 0);
    # Transacciones: jun ingreso 3M, jun egreso 1M, jun egreso 0.5M AL RUBRO AJUSTE;
    # jul ingreso 5M, jul egreso 2M.  (usar los factories del harness)
    out = await svc.actuals_mensuales(meses=3)
    by = {a.mes: a for a in out}
    assert by["2026-06"].ingreso_real == Decimal("3000000")
    assert by["2026-06"].gasto_real == Decimal("1000000")   # el 0.5M del ajuste NO cuenta
    assert by["2026-07"].ingreso_real == Decimal("5000000")
    assert by["2026-07"].gasto_real == Decimal("2000000")
    assert [a.mes for a in out] == ["2026-06", "2026-07"]    # cronológico asc, solo meses con movimientos
```
(El implementer completa el seeding copiando el patrón EXACTO de un test existente en `tests/cierre/` o `tests/presupuesto/` que ya cree `Transaccion`/`MesControl`/`Rubro`. Los montos esperados están recalculados a mano arriba.)

- [ ] **Step 2: Run → FAIL** — `cd backend && python -m pytest tests/proyeccion/test_actuals_mensuales.py -v` (o con `-m requires_real_mongo` si aplica).

- [ ] **Step 3: Implement** en `service.py` (junto a `_actuals_por_mes`; `dataclass`/`Decimal` ya importados; `_rubro_ajuste`/`_caja_libro` ya importados de cierre.service en la línea 15; `Transaccion`/`TipoFlujo`/`MesControl`/`EstadoMes` ya en scope del módulo):

```python
@dataclass(frozen=True)
class ActualMes:
    mes: str            # 'YYYY-MM'
    ingreso_real: Decimal
    gasto_real: Decimal
    caja_real: Decimal


async def _ingreso_real_mes(mes_id) -> Decimal:
    total = Decimal("0")
    async for t in Transaccion.find(Transaccion.mes_id == mes_id):
        if t.tipo_flujo == TipoFlujo.INGRESO:
            total += t.valor
    return total


async def _egreso_real_mes(mes_id, rubro_ajuste_id) -> Decimal:
    total = Decimal("0")
    async for t in Transaccion.find(Transaccion.mes_id == mes_id):
        if t.tipo_flujo == TipoFlujo.EGRESO and t.rubro_id != rubro_ajuste_id:
            total += t.valor
    return total


async def actuals_mensuales(*, meses: int = 3) -> list[ActualMes]:
    rubro_aj = await _rubro_ajuste()
    todos = await MesControl.find_all().sort(+MesControl.mes).to_list()
    # meses con movimientos, los más recientes primero, hasta `meses`
    con_mov: list[MesControl] = []
    for mc in reversed(todos):
        if await Transaccion.find(Transaccion.mes_id == mc.id).count() > 0:
            con_mov.append(mc)
            if len(con_mov) >= meses:
                break
    out: list[ActualMes] = []
    for mc in reversed(con_mov):  # cronológico asc
        out.append(
            ActualMes(
                mes=mc.mes[:7],
                ingreso_real=await _ingreso_real_mes(mc.id),
                gasto_real=await _egreso_real_mes(mc.id, rubro_aj.id),
                caja_real=await _caja_libro(mc.id, rubro_aj.id, mc.saldo_inicial_caja),
            )
        )
    return out
```

- [ ] **Step 4: Run → PASS** + `python -m pytest tests/proyeccion -q` verde. `ruff` limpio. `git diff -- app/proyeccion/motor.py` vacío.
- [ ] **Step 5: Commit** — `feat(proyeccion): actuals_mensuales (ingreso/gasto/caja real por mes, excluye ajuste)`.

---

### Task 2: Calc `tendencia_real` — `cfo/calc/tendencias.py` (3a)

**Files:** Create `backend/app/cfo/calc/tendencias.py` · Test `backend/tests/cfo/calc/test_tendencias.py`

**Interfaces:**
- Consumes: `proyeccion.service.actuals_mensuales` + `ActualMes`; `proyeccion.service.ProyeccionError`.
- Produces: `async def tendencia_real(*, metrica: str) -> list[ResultadoCFO]`. `metrica ∈ {"ingreso","gasto","caja"}`. Conceptos (unidad "COP"): `{metrica}_real_m0` (más reciente), `{metrica}_real_m1`, `{metrica}_real_m2` (si hay 3), y `delta_{metrica}_real` (m0 − m1, `ref="direccion:<sube|baja|estable>"`). `< 2` meses → un `ResultadoCFO(disponible=False)`. Helper `_dir(delta, pos, neg, zero) -> str`.

- [ ] **Step 1: failing test** (monkeypatch `tendencias.proy_service.actuals_mensuales`):

```python
# backend/tests/cfo/calc/test_tendencias.py
from decimal import Decimal
import pytest
from app.cfo.calc import tendencias

def _actual(mes, ing, gas, caja):
    from app.proyeccion.service import ActualMes
    return ActualMes(mes=mes, ingreso_real=Decimal(ing), gasto_real=Decimal(gas), caja_real=Decimal(caja))

@pytest.mark.asyncio
async def test_tendencia_gasto_sube(monkeypatch):
    async def fake(*, meses=3):
        return [_actual("2026-05","0","800000","0"), _actual("2026-06","0","1000000","0"),
                _actual("2026-07","0","1500000","0")]
    monkeypatch.setattr(tendencias.proy_service, "actuals_mensuales", fake)
    rs = await tendencias.tendencia_real(metrica="gasto")
    by = {r.concepto: r for r in rs}
    assert by["gasto_real_m0"].valor == Decimal("1500000")   # más reciente
    assert by["gasto_real_m1"].valor == Decimal("1000000")
    assert by["gasto_real_m2"].valor == Decimal("800000")
    assert by["delta_gasto_real"].valor == Decimal("500000") # 1.5M - 1.0M
    assert by["delta_gasto_real"].evidencia.ref == "direccion:sube"
    assert all(r.disponible for r in rs)

@pytest.mark.asyncio
async def test_tendencia_caja_baja_y_metrica_caja(monkeypatch):
    async def fake(*, meses=3):
        return [_actual("2026-06","0","0","5000000"), _actual("2026-07","0","0","4000000")]
    monkeypatch.setattr(tendencias.proy_service, "actuals_mensuales", fake)
    rs = await tendencias.tendencia_real(metrica="caja")
    by = {r.concepto: r for r in rs}
    assert by["caja_real_m0"].valor == Decimal("4000000")
    assert by["delta_caja_real"].valor == Decimal("-1000000")
    assert by["delta_caja_real"].evidencia.ref == "direccion:baja"
    assert "caja_real_m2" not in by  # solo 2 meses

@pytest.mark.asyncio
async def test_tendencia_abstiene_sin_historia(monkeypatch):
    async def fake(*, meses=3):
        return [_actual("2026-07","0","0","4000000")]  # 1 mes
    monkeypatch.setattr(tendencias.proy_service, "actuals_mensuales", fake)
    rs = await tendencias.tendencia_real(metrica="caja")
    assert len(rs) == 1 and rs[0].disponible is False
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** `tendencias.py`:

```python
"""FABS · tendencias (inc4 rebanada 3): compara data REAL en el tiempo. Envuelve
servicios de COMPAS que ya agregan actuals; NO recalcula, NO importa dominio ni el
proyector interno (aislamiento S1). La direccion (sube/baja/...) la computa COMPAS a
partir de las cifras y viaja en evidencia.ref; el modelo la relata, no la infiere."""

from decimal import Decimal

from app.cfo.calc.evidencia import Evidencia, ResultadoCFO
from app.proyeccion import service as proy_service
from app.proyeccion.service import ProyeccionError

_UNIDAD = "COP"
_METRICAS = {"ingreso": "ingreso_real", "gasto": "gasto_real", "caja": "caja_real"}


def _dir(delta: Decimal, pos: str, neg: str, zero: str) -> str:
    if delta > 0:
        return pos
    if delta < 0:
        return neg
    return zero


def _abstencion(concepto: str, ref: str, fuente: str) -> list[ResultadoCFO]:
    return [ResultadoCFO(concepto=concepto, valor=None, unidad=_UNIDAD,
        disponible=False, evidencia=Evidencia(fuente=fuente, fecha_corte=None, ref=ref))]


async def tendencia_real(*, metrica: str) -> list[ResultadoCFO]:
    fuente = "proyeccion.service.actuals_mensuales"
    if metrica not in _METRICAS:
        raise ValueError(f"metrica no soportada: {metrica}")
    campo = _METRICAS[metrica]
    try:
        serie = await proy_service.actuals_mensuales(meses=3)
    except ProyeccionError:
        return _abstencion(f"{metrica}_real", "sin-config", fuente)
    if len(serie) < 2:
        return _abstencion(f"{metrica}_real", "sin-historia", fuente)
    recientes = serie[::-1]  # m0 = más reciente
    out: list[ResultadoCFO] = []
    for i, a in enumerate(recientes[:3]):
        out.append(ResultadoCFO(concepto=f"{metrica}_real_m{i}", valor=getattr(a, campo),
            unidad=_UNIDAD, disponible=True,
            evidencia=Evidencia(fuente=fuente, fecha_corte=None, ref=a.mes)))
    delta = getattr(recientes[0], campo) - getattr(recientes[1], campo)
    out.append(ResultadoCFO(concepto=f"delta_{metrica}_real", valor=delta, unidad=_UNIDAD,
        disponible=True, evidencia=Evidencia(fuente=fuente, fecha_corte=None,
            ref=f"direccion:{_dir(delta, 'sube', 'baja', 'estable')}")))
    return out
```

- [ ] **Step 4: Run → PASS.** `ruff` limpio. Confirmar que `tendencias.py` NO contiene la subcadena `motor` (guarda S1).
- [ ] **Step 5: Commit** — `feat(cfo): calc tendencia_real (ingreso/gasto/caja real mes-a-mes + direccion)`.

---

### Task 3: Tool `tendencia_real` + prompt + e2e — `cfo/agente/` (3a)

**Files:** Modify `backend/app/cfo/agente/tools.py`, `backend/app/cfo/agente/prompt.py` · Test `backend/tests/cfo/agente/test_tools.py`, `test_prompt.py`, `test_servicio.py`

**Interfaces:** entrada `tendencia_real` en `DISPATCH` + `TOOLS_SCHEMA`. Wrapper `_tendencia_real(entrada: dict)` valida `metrica ∈ {ingreso,gasto,caja}` y llama `tendencias.tendencia_real(metrica=...)`. Schema estricto `required:["metrica"]`, `metrica` enum.

- [ ] **Step 1: failing tests**
  - `test_tools.py`: `tendencia_real` en `TOOLS_SCHEMA` con `additionalProperties:false` + `required:["metrica"]` + enum `["ingreso","gasto","caja"]`; `ejecutar_tool("tendencia_real", {"metrica":"gasto"})` llega a la calc (monkeypatch `app.cfo.calc.tendencias.tendencia_real`); `metrica` inválida → raise.
  - `test_prompt.py`: el prompt menciona `tendencia_real` y "la dirección" + "ref" + reitera "sin porcentajes/%".
  - `test_servicio.py` (e2e ClienteFake): el modelo pide `tendencia_real`, cita `[[gasto_real_m0]]`/`[[delta_gasto_real]]`, relata la dirección; texto sustituido (sin `[[...]]`); cifra cruda → reintento → abstención `motivo="verificacion"` (monkeypatch `app.cfo.calc.tendencias.tendencia_real`).
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** — `import tendencias`; `_tendencia_real(entrada)` (validación de `metrica`, mismo molde que `_kwargs_palanca`/`_simular_palanca`); registrar en `DISPATCH` + `TOOLS_SCHEMA`; bloque de prompt aditivo tras el de palancas (usar `tendencia_real` para "¿cómo viene X vs el mes pasado?"; cita cada `[[..._real_m0/m1/m2]]` y `[[delta_..._real]]`; **la dirección viene en el `ref` del delta — relátala, no la calcules**; **NO des porcentajes**).
- [ ] **Step 4: Run → PASS** + `tests/cfo -q` verde.
- [ ] **Step 5: Commit** — `feat(cfo): tool + prompt tendencia_real (3a end-to-end)`.

---

### Task 4: Calc `rumbo_caja` — `cfo/calc/tendencias.py` (3b)

**Files:** Modify `backend/app/cfo/calc/tendencias.py` · Test `backend/tests/cfo/calc/test_tendencias.py` (añadir)

**Interfaces:**
- Consumes: `proy_service.comparar_vigente` (tramo real) + `proy_service.proyectar_vigente` (piso/quiebre) + `ProyeccionError`; `core.time.now_bogota`.
- Produces: `async def rumbo_caja() -> list[ResultadoCFO]`. Conceptos (COP): `caja_real_ult` (última `actuals[].caja_real`), `caja_real_previo` (penúltima; omitir si solo hay 1), `piso_proyectado` (`Decimal(data["piso_caja"])`, `ref="quiebre:<mes|nunca>"` = primer `meses[].estado!="ok"`), `delta_caja_rumbo` (ult − previo, `ref="direccion:<sube|baja|estable>"`; omitir si <2 actuals). Sin actuals → abstención. **`comparar_vigente`/`proyectar_vigente` devuelven money-STRINGS → `Decimal(...)`.**

- [ ] **Step 1: failing test** (monkeypatch ambos servicios):

```python
@pytest.mark.asyncio
async def test_rumbo_caja_arma_real_y_proyectado(monkeypatch):
    async def fake_comp(**kw):
        return {"ancla": {"mes":"2026-07","caja_real":"4000000"},
            "actuals":[{"mes":"2026-06","caja_real":"5000000"},{"mes":"2026-07","caja_real":"4000000"}],
            "forecast":[{"mes":"2026-08","caja":"3500000"}]}
    async def fake_proy(**kw):
        return {"piso_caja":"3000000","runway_meses":None,
            "meses":[{"mes":"2026-08","estado":"ok"},{"mes":"2026-09","estado":"critico"}]}
    monkeypatch.setattr(tendencias.proy_service, "comparar_vigente", fake_comp)
    monkeypatch.setattr(tendencias.proy_service, "proyectar_vigente", fake_proy)
    rs = await tendencias.rumbo_caja()
    by = {r.concepto: r for r in rs}
    assert by["caja_real_ult"].valor == Decimal("4000000")
    assert by["caja_real_previo"].valor == Decimal("5000000")
    assert by["piso_proyectado"].valor == Decimal("3000000")
    assert by["piso_proyectado"].evidencia.ref == "quiebre:2026-09"
    assert by["delta_caja_rumbo"].valor == Decimal("-1000000")
    assert by["delta_caja_rumbo"].evidencia.ref == "direccion:baja"

@pytest.mark.asyncio
async def test_rumbo_caja_abstiene_sin_actuals(monkeypatch):
    async def fake_comp(**kw): return {"ancla": None, "actuals": [], "forecast": []}
    async def fake_proy(**kw): return {"piso_caja":"0","runway_meses":None,"meses":[]}
    monkeypatch.setattr(tendencias.proy_service, "comparar_vigente", fake_comp)
    monkeypatch.setattr(tendencias.proy_service, "proyectar_vigente", fake_proy)
    rs = await tendencias.rumbo_caja()
    assert len(rs) == 1 and rs[0].disponible is False
```

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** en `tendencias.py`: `from app.core.time import now_bogota`. `rumbo_caja` llama `comparar_vigente(escenario="base", ancla_modo="movimientos", horizonte_meses=None, mes_inicio_defecto=(ahora.year, ahora.month))` y `proyectar_vigente(escenario="base", mes_inicio=(ahora.year, ahora.month), horizonte_meses=None)`; sin `actuals` → abstención (`concepto="rumbo_caja"`); arma los conceptos con `Decimal(...)` sobre los money-strings; `quiebre = next((m["mes"] for m in data["meses"] if m["estado"] != "ok"), "nunca")`; delta solo si len(actuals) ≥ 2. Envuelve ambas llamadas en `try/except ProyeccionError` → abstención.
- [ ] **Step 4: Run → PASS.** `ruff` limpio.
- [ ] **Step 5: Commit** — `feat(cfo): calc rumbo_caja (real hasta hoy + piso/quiebre proyectado)`.

---

### Task 5: Tool `rumbo_caja` (no-param) + prompt + e2e — `cfo/agente/` (3b)

**Files:** Modify `tools.py`, `prompt.py` · Test `test_tools.py`, `test_prompt.py`, `test_servicio.py`

**Interfaces:** `rumbo_caja` en `DISPATCH` cableada DIRECTO a `tendencias.rumbo_caja` (no-param; `ejecutar_tool` la llama `calc()` y normaliza la lista). `TOOLS_SCHEMA` con `input_schema:{type:"object", properties:{}, additionalProperties:false}` (como `caja_disponible_hoy`).

- [ ] **Step 1: failing tests**: `test_tools.py` (rumbo_caja en schema, sin params; `ejecutar_tool("rumbo_caja")` sin `entrada` llega a la calc — monkeypatch `app.cfo.calc.tendencias.rumbo_caja`); `test_prompt.py` (menciona `rumbo_caja` + "rumbo"/"umbral"); `test_servicio.py` (e2e: cita `[[caja_real_ult]]`/`[[piso_proyectado]]`/`[[delta_caja_rumbo]]`, sustituido; cifra cruda → abstención).
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** — `DISPATCH["rumbo_caja"] = tendencias.rumbo_caja`; entrada en `TOOLS_SCHEMA`; bloque de prompt (usar `rumbo_caja` para "¿voy en rumbo?/¿hacia dónde va la caja?"; cita los tokens; la dirección en el `ref` del delta; sin %).
- [ ] **Step 4: Run → PASS** + `tests/cfo -q` verde.
- [ ] **Step 5: Commit** — `feat(cfo): tool + prompt rumbo_caja (3b end-to-end)`.

---

### Task 6: `real_vs_presupuesto_mes` — `presupuesto/service.py` (3c)

**Files:** Modify `backend/app/presupuesto/service.py` · Test `backend/tests/presupuesto/test_real_vs_presupuesto_mes.py`

**Interfaces — Produces:**
- `@dataclass(frozen=True) PresupuestoMes(mes: str, gasto_real: Decimal, presupuesto_aprobado: Decimal)`.
- `async def real_vs_presupuesto_mes(mes: str | None = None) -> PresupuestoMes | None`: `mes` por defecto = último MesControl `CERRADO`; `gasto_real` = Σ EGRESO ejecutado del mes (excluyendo Ajuste de conciliación); `presupuesto_aprobado` = Σ `monto_definido` de las `PresupuestoLinea` vigentes del mes (ignorando None). Sin mes cerrado / sin líneas aprobadas → `None`.

- [ ] **Step 1: failing test** (harness Beanie; sembrar un MesControl CERRADO 2026-06 con: 2 tx EGRESO (1.0M + 0.5M) y 1 tx al rubro Ajuste (0.3M, NO cuenta); 2 PresupuestoLinea vigentes con `monto_definido` 1.2M y 0.6M):

```python
# backend/tests/presupuesto/test_real_vs_presupuesto_mes.py — imports del harness
@pytest.mark.asyncio
async def test_real_vs_presupuesto_mes_cerrado(db):
    out = await presu_svc.real_vs_presupuesto_mes()   # último cerrado = 2026-06
    assert out is not None
    assert out.mes == "2026-06"
    assert out.gasto_real == Decimal("1500000")            # 1.0M + 0.5M (ajuste excluido)
    assert out.presupuesto_aprobado == Decimal("1800000")  # 1.2M + 0.6M

@pytest.mark.asyncio
async def test_real_vs_presupuesto_mes_sin_cerrado(db):
    # sin MesControl cerrado sembrado
    assert await presu_svc.real_vs_presupuesto_mes() is None
```
(El implementer completa el seeding copiando un test existente de `tests/presupuesto/` que ya cree `PresupuestoLinea`/`Transaccion`/`MesControl`; montos esperados recalculados arriba.)

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** en `presupuesto/service.py` (ya tiene `_ejecutados_por_rubro_mes`, `MesControl`, `EstadoMes`, `Transaccion`, `TipoFlujo`, `PresupuestoLinea` en scope; importar `_rubro_ajuste` de `app.cierre.service` si no está):

```python
@dataclass(frozen=True)
class PresupuestoMes:
    mes: str
    gasto_real: Decimal
    presupuesto_aprobado: Decimal


async def _gasto_real_mes(mes_id, rubro_ajuste_id) -> Decimal:
    total = Decimal("0")
    async for t in Transaccion.find(Transaccion.mes_id == mes_id):
        if t.tipo_flujo == TipoFlujo.EGRESO and t.rubro_id != rubro_ajuste_id:
            total += t.valor
    return total


async def _aprobado_mes(mes_id) -> Decimal:
    total = Decimal("0")
    async for ln in PresupuestoLinea.find(
        PresupuestoLinea.mes_id == mes_id, PresupuestoLinea.vigente == True  # noqa: E712
    ):
        if ln.monto_definido is not None:
            total += ln.monto_definido
    return total


async def real_vs_presupuesto_mes(mes: str | None = None) -> PresupuestoMes | None:
    if mes is None:
        mc = await (
            MesControl.find(MesControl.estado == EstadoMes.CERRADO)
            .sort(-MesControl.mes).limit(1).to_list()
        )
        mc = mc[0] if mc else None
    else:
        mc = await MesControl.find_one(
            MesControl.mes == f"{mes}-01", MesControl.estado == EstadoMes.CERRADO
        )
    if mc is None:
        return None
    rubro_aj = await _rubro_ajuste()
    aprobado = await _aprobado_mes(mc.id)
    if aprobado == 0:
        return None
    return PresupuestoMes(
        mes=mc.mes[:7],
        gasto_real=await _gasto_real_mes(mc.id, rubro_aj.id),
        presupuesto_aprobado=aprobado,
    )
```
(Nota: `_gasto_real_mes` duplica la lógica de `proyeccion.service._egreso_real_mes` de Task 1 pero en otro módulo/colección de import; si el implementer ve una vía limpia de reusar sin romper S1/imports, mejor — si no, la duplicación mínima es aceptable y NO se comparte con proyeccion para no crear un import cruzado presupuesto→proyeccion.)

- [ ] **Step 4: Run → PASS** + `python -m pytest tests/presupuesto -q` verde. `ruff` limpio.
- [ ] **Step 5: Commit** — `feat(presupuesto): real_vs_presupuesto_mes (gasto real vs aprobado del mes cerrado)`.

---

### Task 7: Calc `real_vs_presupuesto` — `cfo/calc/tendencias.py` (3c)

**Files:** Modify `backend/app/cfo/calc/tendencias.py` · Test `backend/tests/cfo/calc/test_tendencias.py` (añadir)

**Interfaces:**
- Consumes: `presupuesto.service.real_vs_presupuesto_mes` + `PresupuestoMes`.
- Produces: `async def real_vs_presupuesto(*, mes: str | None = None) -> list[ResultadoCFO]`. Conceptos (COP): `gasto_real_mes`, `presupuesto_mes`, `desvio_presupuesto` (gasto_real − presupuesto, `ref="direccion:<sobre|bajo|en-linea>"`). `None` → abstención.

- [ ] **Step 1: failing test** (monkeypatch `tendencias.presu_service.real_vs_presupuesto_mes`):

```python
@pytest.mark.asyncio
async def test_real_vs_presupuesto_sobre(monkeypatch):
    from app.presupuesto.service import PresupuestoMes
    async def fake(mes=None):
        return PresupuestoMes(mes="2026-06", gasto_real=Decimal("1500000"), presupuesto_aprobado=Decimal("1200000"))
    monkeypatch.setattr(tendencias.presu_service, "real_vs_presupuesto_mes", fake)
    rs = await tendencias.real_vs_presupuesto()
    by = {r.concepto: r for r in rs}
    assert by["gasto_real_mes"].valor == Decimal("1500000")
    assert by["presupuesto_mes"].valor == Decimal("1200000")
    assert by["desvio_presupuesto"].valor == Decimal("300000")
    assert by["desvio_presupuesto"].evidencia.ref == "direccion:sobre"

@pytest.mark.asyncio
async def test_real_vs_presupuesto_abstiene(monkeypatch):
    async def fake(mes=None): return None
    monkeypatch.setattr(tendencias.presu_service, "real_vs_presupuesto_mes", fake)
    rs = await tendencias.real_vs_presupuesto()
    assert len(rs) == 1 and rs[0].disponible is False
```

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** en `tendencias.py`: `from app.presupuesto import service as presu_service`. `real_vs_presupuesto`: llama `real_vs_presupuesto_mes(mes=mes)`; si `None` → abstención (`concepto="presupuesto"`, ref `"sin-cerrado"`); si no, arma los 3 conceptos con `ref=a.mes` para gasto/presupuesto y `ref=f"direccion:{_dir(desvio,'sobre','bajo','en-linea')}"` para el desvío. (S1: importar `presupuesto.service` es un servicio, permitido.)
- [ ] **Step 4: Run → PASS.** `ruff` limpio; `tendencias.py` sin la subcadena `motor`.
- [ ] **Step 5: Commit** — `feat(cfo): calc real_vs_presupuesto (gasto real vs aprobado + desvio)`.

---

### Task 8: Tool `real_vs_presupuesto` + prompt + e2e — `cfo/agente/` (3c)

**Files:** Modify `tools.py`, `prompt.py` · Test `test_tools.py`, `test_prompt.py`, `test_servicio.py`

**Interfaces:** `real_vs_presupuesto` en `DISPATCH` vía wrapper `_real_vs_presupuesto(entrada: dict)` (lee `mes` opcional string `YYYY-MM`, lo pasa como kwarg). `TOOLS_SCHEMA`: `properties:{mes:{type:"string"}}`, `additionalProperties:false`, `required:[]`.

- [ ] **Step 1: failing tests**: `test_tools.py` (schema estricto, `mes` opcional; `ejecutar_tool("real_vs_presupuesto", {})` y `{"mes":"2026-06"}` llegan a la calc — monkeypatch `app.cfo.calc.tendencias.real_vs_presupuesto`); `test_prompt.py` (menciona `real_vs_presupuesto` + "presupuesto"); `test_servicio.py` (e2e: cita `[[gasto_real_mes]]`/`[[presupuesto_mes]]`/`[[desvio_presupuesto]]`, sustituido, relata dirección; cifra cruda → abstención).
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** — `_real_vs_presupuesto(entrada)` (extrae `mes = entrada.get("mes")`), `DISPATCH` + `TOOLS_SCHEMA`; bloque de prompt (usar `real_vs_presupuesto` para "¿gasté más/menos de lo presupuestado?"; cita los tokens; dirección en el `ref` del desvío; sin %).
- [ ] **Step 4: Run → PASS** + `tests/cfo -q` verde.
- [ ] **Step 5: Commit** — `feat(cfo): tool + prompt real_vs_presupuesto (3c end-to-end)`.

---

### Task 9: Cierre — regresión, guardas, roadmap

**Files:** Modify `docs/COMPAS_FABS_ROADMAP.md` · (verificación) toda la suite

- [ ] **Step 1: Regresión + guardas** (reportar salidas verbatim):
  - `cd backend && python -m pytest tests/cfo tests/proyeccion tests/presupuesto -q` (pass/skip/fail).
  - `python -m pytest tests/cfo/test_s1_aislamiento.py -q` verde.
  - `ruff check app/cfo/ app/proyeccion/service.py app/presupuesto/service.py` + `ruff format --check` limpios.
  - `git diff <MERGE_BASE=origin/main>..HEAD -- backend/app/proyeccion/motor.py backend/app/presupuesto/motor.py` VACÍO.
  - `grep -rn "float(" app/cfo/calc/tendencias.py` sin resultados.
  - **Guarda de colisión de conceptos:** confirmar que ningún concepto nuevo (`*_real_m0/m1/m2`, `delta_*_real`, `caja_real_ult/previo`, `piso_proyectado`, `delta_caja_rumbo`, `gasto_real_mes`, `presupuesto_mes`, `desvio_presupuesto`) colisiona con los de rebanadas 1–2 (grep de los nombres en `app/cfo/calc/*.py`; `delta_caja_real` solo lo emite 3a, `delta_caja_rumbo` solo 3b).
- [ ] **Step 2: Cierre** — `docs/COMPAS_FABS_ROADMAP.md`: rebanada 3 construida (registro fechado; 3 tools tendencia_real/rumbo_caja/real_vs_presupuesto; sin %; gate-waiver + GO CEO; NADA de Kimi). NO tocar el `.xlsx` (lo hace el controlador post-SDD). Commit: `feat(cfo): cierre rebanada 3 tendencias (3a+3b+3c, gate-waiver GO CEO)`.

---

## Self-Review (autor del plan)

**1. Cobertura del spec:** §5.1 actuals_mensuales→T1 · §5.2 real_vs_presupuesto_mes→T6 · §5.3 calc tendencia_real→T2, rumbo_caja→T4, real_vs_presupuesto→T7 · §5.4 tools→T3/T5/T8 · §5.5 prompt→T3/T5/T8 · §6 conceptos namespaced→T2/T4/T7 (+ guarda T9) · §7 meses (movimientos/cerrado)→T1/T6 · §8 trampas (excluir ajuste→T1/T6; partes→nota T1; dirección COMPAS→T2/T4/T7; sin %→prompts; namespaced→Global+T9)→cubiertas · §9 abstención→T2/T4/T7 · §10 pruebas→cada task · §11 innegociables→Global+T9 · §12 sub-rebanadas→T1-3/T4-5/T6-8.

**2. Placeholders:** el seeding de los tests de servicio (T1/T6) dice "copiar el patrón de un test existente en tests/cierre|presupuesto" — es una instrucción concreta (nombra el directorio y da los montos esperados recalculados), no lógica pendiente; el resto trae código real.

**3. Consistencia de tipos:** `actuals_mensuales(*, meses=3) -> list[ActualMes(mes,ingreso_real,gasto_real,caja_real)]` (T1) ↔ consumido por `tendencia_real` (T2, campos vía `_METRICAS`). `real_vs_presupuesto_mes(mes=None) -> PresupuestoMes(mes,gasto_real,presupuesto_aprobado)|None` (T6) ↔ `real_vs_presupuesto` (T7). Conceptos T2 (`{metrica}_real_m0/m1/m2`,`delta_{metrica}_real`), T4 (`caja_real_ult/previo`,`piso_proyectado`,`delta_caja_rumbo`), T7 (`gasto_real_mes`,`presupuesto_mes`,`desvio_presupuesto`) — nombres usados idénticos en calc/tool/prompt/e2e. `delta_caja_real`(3a) ≠ `delta_caja_rumbo`(3b): colisión eliminada por construcción.

---
*Rebanada 3 del inc4. Ejecutar por SDD. Gate-waiver + GO CEO (NADA de Kimi, NUNCA simular). `motor.py` intocable. `%` y desglose por grupo → rebanadas siguientes.*
