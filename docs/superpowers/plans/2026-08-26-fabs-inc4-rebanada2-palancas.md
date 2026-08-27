# FABS inc4 · Rebanada 2 — What-if de palancas · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que FABS responda "¿qué pasa si vendo a 78 semanas / bajo la cuota inicial / subo la cuota semanal?" (para un modelo o todos) re-proyectando el motor real y narrando impacto en caja + mes de quiebre, con evidencia, sin que el modelo calcule.

**Architecture:** Reusa el pipeline vivo. En `proyeccion/service.py` se agrega `impacto_palanca_raw` (ADITIVO): carga params+modelos vigentes, corre `_resultado_con` (motor→E1→D2) para la base y para los modelos con el campo cambiado (`ModeloMoto.model_copy`), y devuelve un dataclass PLANO `PalancaImpacto` (Decimals/str — sin tipos de dominio, para que `cfo/calc` lo consuma respetando S1). `cfo/calc/palanca.py::impacto_palanca` lo envuelve en `ResultadoCFO`; `tools.py` registra `simular_palanca`; el prompt lo enseña.

**Tech Stack:** Python 3.12, FastAPI, Beanie/Motor, Pydantic strict, `decimal.Decimal`, pytest. FABS con `ClienteFake`/mocks (CI verde sin API key ni Mongo).

**Spec:** `docs/superpowers/specs/2026-08-26-fabs-inc4-rebanada2-palancas-design.md`

> **Refinamiento del spec §5.1 (registrar como decisión):** el spec sugería "generalizar `fabrica_proyectar_unidades` → `fabrica_proyectar_con_overrides`". Esa fábrica devuelve un `Callable[[int], …]` (forma de SOLVER, para bisección). La rebanada 2 NO bisecta: necesita base+con UNA vez. Por eso se agrega `impacto_palanca_raw` (devuelve valores planos), en vez de generalizar la fábrica. Mismo reuso (`_resultado_con` + override por `model_copy`), misma S1, y `fabrica_proyectar_unidades` (rebanada 1) queda **intacta**.

## Global Constraints

- **Dinero = Decimal, nunca float**; string en el borde; cero `float(` en la ruta nueva.
- **`motor.py` cero diffs.** Aditivo: `impacto_palanca_raw` (proyeccion), calc/tool/prompt (cfo). Reusa `_resultado_con`.
- **El modelo NUNCA produce una cifra.** Cita `[[piso_sin]]`/`[[piso_con]]`/`[[impacto]]`; el verificador rechaza cifras/mes/conteo crudos; el servicio sustituye tras verificar. **Resultados en COP/mes — SIN `%`** (el mix, que trae `%`, es rebanada 4).
- **S1:** `cfo/**` NO importa `app.domain.*` ni `motor`; `impacto_palanca_raw` (que sí toca dominio/motor) vive en `proyeccion/service.py` y devuelve un dataclass plano; `cfo/calc` solo lo llama. `test_s1_aislamiento.py` verde.
- **Reconciliación:** base y con corren el MISMO `_resultado_con` (motor→E1→D2) → el impacto de la palanca no da falsa confianza.
- **Catálogo de auditoría:** SIN eventos nuevos (reusa `cfo.consulta`/`cfo.respuesta`).
- **Flag `CFO_ENABLED`.** `ruff` limpio. Gate-waiver GO CEO; Kimi diseño+código RETROACTIVOS pendientes (Kimi ~semanas; NUNCA simular). Construcción por SDD **desde 29-ago**.
- **Branch guard:** `git branch --show-current` == `feat/fabs-inc4-rebanada2-palancas` antes de cada commit. Rama desde main `41cb535`.
- **Firmas reales reusadas:** `_resultado_con(params: ParametrosProyeccion, modelos: list[ModeloMoto], *, escenario, mes_inicio: tuple[int,int], horizonte_meses: int|None, …) -> tuple[ResultadoProyeccion, …]` (service.py:610; el 1er elemento `r` trae `.piso_caja: Decimal` y `.meses[i].{mes, estado∈{ok,critico,negativo}}`); `modelos_moto.service.listar_modelos(activo=True)`; `parametros_proyeccion.service.obtener_vigente() -> ParametrosProyeccion|None`; `ModeloMoto` (`nombre: str`, `plazo_semanas: int`, `cuota_inicial: Money`, `cuota_semanal: Money`) — `model_copy(update={campo: valor})`; `ProyeccionError(detalle, status)`. Patrón de calc + abstención: `cfo/calc/escenario.py` (rebanada 1) y `runway.py`. Patrón de tool parametrizada: `cfo/agente/tools.py` (wrappers de escenario de la rebanada 1).

---

### Task 1: `impacto_palanca_raw` + `PalancaImpacto` — `proyeccion/service.py`

**Files:** Modify `backend/app/proyeccion/service.py` · Test `backend/tests/proyeccion/test_impacto_palanca_raw.py`

**Interfaces — Produces:**
- `@dataclass(frozen=True) PalancaImpacto(piso_sin: Decimal, piso_con: Decimal, mes_quiebre: str, impacto: Decimal)` (`mes_quiebre` = "YYYY-MM" o "nunca"; `impacto` = piso_con − piso_sin, computado aquí en Decimal).
- `async def impacto_palanca_raw(*, palanca: str, nuevo_valor: Decimal, modelo: str = "todos", escenario: str, mes_inicio: tuple[int,int], horizonte_meses: int|None) -> PalancaImpacto`. Carga params+modelos vigentes (abstención vía `ProyeccionError` si faltan). Valida `palanca ∈ {plazo_semanas, cuota_inicial, cuota_semanal}` y `modelo` existente (o "todos"). Tipa el valor por palanca (plazo→int>0; cuotas→Decimal≥0). Corre `_resultado_con` para base y para modelos con `model_copy(update={palanca: valor})` en el/los modelo(s) objetivo. Devuelve `PalancaImpacto`.

- [ ] **Step 1: Write the failing test** (monkeypatchea `_resultado_con` y `listar_modelos`/`obtener_vigente` para no tocar Mongo/motor)

```python
# backend/tests/proyeccion/test_impacto_palanca_raw.py
from dataclasses import dataclass
from decimal import Decimal
import pytest
from app.proyeccion import service as svc


@dataclass
class _Mes:
    mes: str
    estado: str

@dataclass
class _R:
    piso_caja: Decimal
    meses: list

def _modelo(nombre, plazo=52, ci="500000", cs="80000"):
    from app.domain.modelo_moto import ModeloMoto
    return ModeloMoto(nombre=nombre, costo_auteco=Decimal("1"), precio_venta=Decimal("1"),
        iva_venta=Decimal("0"), cuota_inicial=Decimal(ci), cuota_semanal=Decimal(cs),
        plazo_semanas=plazo, participacion_mix=Decimal("0.5"))

@pytest.mark.asyncio
async def test_impacto_palanca_plazo_todos(monkeypatch):
    modelos = [_modelo("Raider", 52), _modelo("Apache", 52)]
    monkeypatch.setattr(svc.modelos_service, "listar_modelos", lambda activo=True: _aw(modelos))
    monkeypatch.setattr(svc.params_service, "obtener_vigente", lambda: _aw(_vig()))
    llamadas = []
    async def fake_rc(params, mods, *, escenario, mes_inicio, horizonte_meses, **kw):
        # base: plazo 52 -> piso 100M ; con: algún modelo a 78 -> piso 120M + quiebre nunca
        plazos = tuple(m.plazo_semanas for m in mods)
        llamadas.append(plazos)
        piso = Decimal("120000000") if 78 in plazos else Decimal("100000000")
        return (_R(piso, [_Mes("2026-09", "ok")]), None, [], None, None)
    monkeypatch.setattr(svc, "_resultado_con", fake_rc)
    out = await svc.impacto_palanca_raw(palanca="plazo_semanas", nuevo_valor=Decimal("78"),
        modelo="todos", escenario="base", mes_inicio=(2026, 9), horizonte_meses=None)
    assert out.piso_sin == Decimal("100000000")
    assert out.piso_con == Decimal("120000000")
    assert out.impacto == Decimal("20000000")
    assert out.mes_quiebre == "nunca"
    assert llamadas[1] == (78, 78)  # "todos" -> ambos modelos a 78

@pytest.mark.asyncio
async def test_impacto_palanca_modelo_especifico(monkeypatch):
    modelos = [_modelo("Raider", 52), _modelo("Apache", 52)]
    monkeypatch.setattr(svc.modelos_service, "listar_modelos", lambda activo=True: _aw(modelos))
    monkeypatch.setattr(svc.params_service, "obtener_vigente", lambda: _aw(_vig()))
    vistos = []
    async def fake_rc(params, mods, **kw):
        vistos.append(tuple((m.nombre, m.plazo_semanas) for m in mods))
        return (_R(Decimal("50000000"), [_Mes("2026-11", "critico")]), None, [], None, None)
    monkeypatch.setattr(svc, "_resultado_con", fake_rc)
    out = await svc.impacto_palanca_raw(palanca="plazo_semanas", nuevo_valor=Decimal("78"),
        modelo="Raider", escenario="base", mes_inicio=(2026, 9), horizonte_meses=None)
    assert vistos[1] == (("Raider", 78), ("Apache", 52))  # solo Raider cambió
    assert out.mes_quiebre == "2026-11"

@pytest.mark.asyncio
async def test_impacto_palanca_modelo_desconocido_abstiene(monkeypatch):
    monkeypatch.setattr(svc.modelos_service, "listar_modelos", lambda activo=True: _aw([_modelo("Raider")]))
    monkeypatch.setattr(svc.params_service, "obtener_vigente", lambda: _aw(_vig()))
    with pytest.raises(svc.ProyeccionError):
        await svc.impacto_palanca_raw(palanca="plazo_semanas", nuevo_valor=Decimal("78"),
            modelo="Ghost", escenario="base", mes_inicio=(2026, 9), horizonte_meses=None)
```
(Helpers `_aw` = coroutine que devuelve el valor; `_vig()` = un `ParametrosProyeccion` mínimo válido. Definirlos en el test siguiendo el patrón de `tests/proyeccion/` para construir un `ParametrosProyeccion`; el implementer verifica los campos requeridos.)

- [ ] **Step 2: Run → FAIL** — `cd backend && python -m pytest tests/proyeccion/test_impacto_palanca_raw.py -v`.

- [ ] **Step 3: Implement** en `service.py` (junto a `fabrica_proyectar_unidades`):

```python
_PALANCAS_ESCALARES = {"plazo_semanas", "cuota_inicial", "cuota_semanal"}


@dataclass(frozen=True)
class PalancaImpacto:
    piso_sin: Decimal
    piso_con: Decimal
    mes_quiebre: str  # 'YYYY-MM' o 'nunca'
    impacto: Decimal  # piso_con - piso_sin (lo computa COMPAS, no el modelo)


def _mes_de_quiebre_raw(r) -> str:
    return next((m.mes for m in r.meses if m.estado != "ok"), "nunca")


def _tipar_palanca(palanca: str, nuevo_valor: Decimal) -> object:
    if palanca == "plazo_semanas":
        v = int(nuevo_valor)
        if v <= 0:
            raise ProyeccionError("plazo_semanas debe ser > 0", 422)
        return v
    if nuevo_valor < 0:  # cuota_inicial / cuota_semanal
        raise ProyeccionError(f"{palanca} no puede ser negativa", 422)
    return nuevo_valor


async def impacto_palanca_raw(
    *, palanca: str, nuevo_valor: Decimal, modelo: str = "todos",
    escenario: str, mes_inicio: tuple[int, int], horizonte_meses: int | None,
) -> PalancaImpacto:
    if palanca not in _PALANCAS_ESCALARES:
        raise ProyeccionError(f"palanca no soportada: {palanca}", 422)
    vig = await params_service.obtener_vigente()
    if vig is None:
        raise ProyeccionError("no hay parámetros de proyección vigentes", 409)
    modelos = await modelos_service.listar_modelos(activo=True)
    if not modelos:
        raise ProyeccionError("no hay modelos de moto activos", 409)
    if modelo != "todos" and not any(m.nombre == modelo for m in modelos):
        raise ProyeccionError(f"modelo desconocido: {modelo}", 422)
    valor = _tipar_palanca(palanca, nuevo_valor)

    def _override(m):
        if modelo == "todos" or m.nombre == modelo:
            return m.model_copy(update={palanca: valor})
        return m

    kw = dict(escenario=escenario, mes_inicio=mes_inicio, horizonte_meses=horizonte_meses)
    r_sin, *_ = await _resultado_con(vig, modelos, **kw)
    r_con, *_ = await _resultado_con(vig, [_override(m) for m in modelos], **kw)
    return PalancaImpacto(
        piso_sin=r_sin.piso_caja,
        piso_con=r_con.piso_caja,
        mes_quiebre=_mes_de_quiebre_raw(r_con),
        impacto=r_con.piso_caja - r_sin.piso_caja,
    )
```
(Confirmar que `params_service`/`modelos_service` ya están importados en `service.py` — la rebanada 1 usa `modelos_service`; si `params_service` no está, importarlo: `from app.parametros_proyeccion import service as params_service`. `dataclass`/`Decimal` ya importados.)

- [ ] **Step 4: Run → PASS** + regresión de proyeccion (`python -m pytest tests/proyeccion -q`) verde. `ruff` limpio. `git diff -- app/proyeccion/motor.py` vacío.

- [ ] **Step 5: Commit** — `feat(proyeccion): impacto_palanca_raw — re-proyecta el pipeline completo con override de ModeloMoto`.

---

### Task 2: Calc `impacto_palanca` — `cfo/calc/palanca.py`

**Files:** Create `backend/app/cfo/calc/palanca.py` · Test `backend/tests/cfo/calc/test_palanca.py`

**Interfaces:**
- Consumes: `proyeccion.service.impacto_palanca_raw` + `ProyeccionError`; `core.time.now_bogota`.
- Produces: `async def impacto_palanca(*, palanca: str, nuevo_valor: Decimal, modelo: str = "todos") -> list[ResultadoCFO]` → conceptos `piso_sin`, `piso_con` (COP; `evidencia.ref="quiebre:<...>"`), `impacto` (COP). Sin config/inválido (`ProyeccionError`) → un `ResultadoCFO(disponible=False)`. `escenario="base"`, `mes_inicio=(año,mes)` de `now_bogota`, `horizonte_meses=None`. Evidencia con ancla de horizonte (`ref=f"{ahora.year:04d}-{ahora.month:02d}"` salvo `piso_con` que usa `quiebre:`).

- [ ] **Step 1: failing test** (monkeypatchea `palanca.proy_service.impacto_palanca_raw`)

```python
# backend/tests/cfo/calc/test_palanca.py
from decimal import Decimal
import pytest
from app.cfo.calc import palanca


@pytest.mark.asyncio
async def test_impacto_palanca_arma_conceptos(monkeypatch):
    from app.proyeccion.service import PalancaImpacto
    async def fake_raw(**kw):
        return PalancaImpacto(piso_sin=Decimal("100000000"), piso_con=Decimal("120000000"),
                              mes_quiebre="nunca", impacto=Decimal("20000000"))
    monkeypatch.setattr(palanca.proy_service, "impacto_palanca_raw", fake_raw)
    rs = await palanca.impacto_palanca(palanca="plazo_semanas", nuevo_valor=Decimal("78"), modelo="todos")
    by = {r.concepto: r for r in rs}
    assert by["piso_sin"].valor == Decimal("100000000")
    assert by["piso_con"].valor == Decimal("120000000")
    assert by["piso_con"].evidencia.ref == "quiebre:nunca"
    assert by["impacto"].valor == Decimal("20000000")
    assert all(r.disponible for r in rs)


@pytest.mark.asyncio
async def test_impacto_palanca_abstiene(monkeypatch):
    async def boom(**kw):
        raise palanca.ProyeccionError("sin config", 409)
    monkeypatch.setattr(palanca.proy_service, "impacto_palanca_raw", boom)
    rs = await palanca.impacto_palanca(palanca="plazo_semanas", nuevo_valor=Decimal("78"))
    assert len(rs) == 1 and rs[0].disponible is False
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** `palanca.py` (mismo molde que `escenario.py`): `from app.proyeccion import service as proy_service`, `from app.proyeccion.service import ProyeccionError`; construir los 3 `ResultadoCFO` (`unidad="COP"`), `piso_con.evidencia.ref=f"quiebre:{res.mes_quiebre}"`, los otros con ancla de horizonte; `detalle` puede llevar `{palanca, modelo, nuevo_valor}` para trazabilidad (no citable). `try/except ProyeccionError` → abstención (patrón `runway.py`).

- [ ] **Step 4: Run → PASS.** `ruff` limpio.

- [ ] **Step 5: Commit** — `feat(cfo): calc impacto_palanca (envuelve impacto_palanca_raw, evidencia + quiebre)`.

---

### Task 3: Tool `simular_palanca` — `cfo/agente/tools.py`

**Files:** Modify `backend/app/cfo/agente/tools.py` · Test `backend/tests/cfo/agente/test_tools.py` (añadir)

**Interfaces:** entrada en `DISPATCH` + `TOOLS_SCHEMA`. Wrapper async de UN dict posicional (como los de la rebanada 1): valida `palanca ∈ {plazo_semanas,cuota_inicial,cuota_semanal}` y `modelo ∈ {Raider,Apache,Sport,todos}` (default "todos"), parsea `nuevo_valor` string→`Decimal` (finito; raise si inválido), llama `palanca.impacto_palanca(...)` con kwargs, devuelve `list[ResultadoCFO]`. `input_schema` estricto: `additionalProperties:false`, `required:["palanca","nuevo_valor"]`, `palanca` enum, `nuevo_valor` string, `modelo` enum. *Nota: el enum de `modelo` en el schema es la lista fija de modelos actuales (Raider/Apache/Sport/todos); si mañana hay más modelos, el calc valida contra los vigentes de todos modos (el enum del schema es orientación para el modelo, la validación dura está en `impacto_palanca_raw`).*

- [ ] **Step 1: failing test** (mismo patrón que los tests de tools de escenario de la rebanada 1): assert `simular_palanca` en `TOOLS_SCHEMA` con `additionalProperties:false` + `required`; `ejecutar_tool("simular_palanca", {"palanca":"plazo_semanas","nuevo_valor":"78"})` parsea `nuevo_valor` a `Decimal("78")` y llega a la calc (monkeypatch `app.cfo.calc.palanca.impacto_palanca`); `palanca` inválida y `nuevo_valor` no numérico → raise.

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** — reusar el helper de parseo/validación de la rebanada 1 (o uno análogo `_kwargs_palanca(entrada)` que valide palanca/modelo + parsee `nuevo_valor`); registrar wrapper async + schema. Dispatcher cerrado; tools existentes intactas.

- [ ] **Step 4: Run → PASS** + `tests/cfo/agente/ -q` verde. `ruff` limpio.

- [ ] **Step 5: Commit** — `feat(cfo): registra tool simular_palanca (schema estricto, palanca/modelo validados, valor string→Decimal)`.

---

### Task 4: Prompt — `cfo/agente/prompt.py`

**Files:** Modify `backend/app/cfo/agente/prompt.py` · Test `backend/tests/cfo/agente/test_prompt.py` (añadir)

**Interfaces:** el `SYSTEM_PROMPT` menciona `simular_palanca` para "¿qué pasa si cambio el plazo/cuota…?"; devuelve `[[piso_sin]]`/`[[piso_con]]`/`[[impacto]]`; citar con tokens, nunca escribir cifras. Regla 1/2 sin cambios (solo alcance). NO tocar el bloque de escenarios de la rebanada 1.

- [ ] **Step 1: failing test** — assert que el prompt menciona `simular_palanca` y los 3 tokens (`[[piso_sin]]`,`[[piso_con]]`,`[[impacto]]`) + la instrucción de no escribir la cifra.
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** — añadir un bloque corto tras el de escenarios; sin tocar reglas existentes.
- [ ] **Step 4: Run → PASS** + tests de prompt existentes verdes.
- [ ] **Step 5: Commit** — `feat(cfo): prompt enseña simular_palanca (what-if de palancas)`.

---

### Task 5: e2e + golden + cierre

**Files:** Test `backend/tests/cfo/agente/test_servicio.py` (añadir) · Test/golden `backend/tests/cfo/test_palanca_golden.py` · Modify `docs/COMPAS_FABS_ROADMAP.md`

- [ ] **Step 1: failing tests**
  - `test_servicio.py`: `ClienteFake` que pide `simular_palanca` y responde citando `[[piso_sin]]`/`[[piso_con]]`/`[[impacto]]`; monkeypatch de `palanca.impacto_palanca` con valores conocidos; assert `r.abstuvo is False` y `r.texto` con valores sustituidos (no `[[...]]`); + caso de cifra cruda → reintento → abstención `motivo="verificacion"`.
  - `test_palanca_golden.py`: un cambio de palanca de referencia (p. ej. plazo 52→78 en un `ParametrosProyeccion`/modelos fijos) con `piso_sin`/`piso_con`/`impacto`/quiebre conocidos "al peso" — corriendo `impacto_palanca_raw` REAL sobre una proyección en forma cerrada (fakear solo la carga de Mongo: `_resultado_con` con un motor determinista mínimo, o construir el `ParametrosProyeccion`/`ModeloMoto` y monkeypatchear la parte async de carga), matemática recalculada a mano en el docstring (no re-derivada del código bajo prueba).
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** — ajustes finos que falten (no lógica nueva mayor). Sembrar el golden.
- [ ] **Step 4: Regresión + guardas** — `python -m pytest -q` (reportar pass/skip/fail); `ruff check app/cfo/ app/proyeccion/service.py`; `git diff <MERGE_BASE=41cb535>..HEAD -- app/proyeccion/motor.py app/presupuesto/motor.py` VACÍO; `grep "float(" app/cfo/calc/palanca.py` sin resultados; `test_s1_aislamiento.py` verde.
- [ ] **Step 5: Cierre** — `docs/COMPAS_FABS_ROADMAP.md`: rebanada 2 construida (registro fechado; gate-waiver GO CEO, Kimi retroactivo pendiente, NUNCA simular; merge decidido con el CEO por el flag ON). NO tocar el `.xlsx`. Paquete Kimi INC4-R2 (diff embebido) lo arma el controlador post-SDD. Commit: `feat(cfo): palancas what-if end-to-end + golden + cierre rebanada 2 (gate-waiver GO CEO)`.

---

## Self-Review (autor del plan)

**1. Cobertura del spec:** §4 reuso `_resultado_con`→T1 · §5.1 (refinado) `impacto_palanca_raw`→T1 · §5.2 calc→T2 · §5.3 tool→T3 · §5.4 prompt→T4 · §6 conceptos (COP, quiebre ref)→T2 · §7 por-modelo (nombre / "todos" / desconocido→abstención)→T1/T2 · §8 trampas (quiebre por estado; reconciliación mismo pipeline; sin `%`)→T1 · §9 abstención→T1/T2/T3 · §10 pruebas→cada task+T5 · §11 innegociables→Global Constraints+T5.

**2. Placeholders:** los tests traen código real; los "confirmar contra el código" (campos de `ParametrosProyeccion` para `_vig()`, import de `params_service`) son verificaciones puntuales contra el repo, con el test definiendo el comportamiento — no lógica pendiente.

**3. Consistencia de tipos:** `impacto_palanca_raw(*, palanca, nuevo_valor: Decimal, modelo, escenario, mes_inicio, horizonte_meses) -> PalancaImpacto(piso_sin, piso_con, mes_quiebre, impacto)` (T1) usado por `impacto_palanca` (T2); `impacto_palanca(*, palanca, nuevo_valor: Decimal, modelo)` (T2) registrado por la tool (T3); conceptos `piso_sin`/`piso_con`/`impacto` idénticos en T2/T4/T5; `ModeloMoto.model_copy(update={palanca: valor})` con `palanca ∈ {plazo_semanas,cuota_inicial,cuota_semanal}` (campos reales).

---
*Rebanada 2 del inc4. Ejecutar por SDD (desde 29-ago). Gate-waiver GO CEO; Kimi retroactivo (NUNCA simular). Merge: flag ENCENDIDO ⇒ decidir con el CEO cómo soltar. `motor.py` intocable. Mix → rebanada 4.*
