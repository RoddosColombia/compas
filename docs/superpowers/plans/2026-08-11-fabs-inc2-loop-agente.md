# FABS Incremento 2 — Loop del agente + verificador cifra→evidencia · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Conectar el LLM sobre el cimiento de inc1 con un loop acotado y un verificador que impide publicar cualquier cifra sin evidencia; todo detrás del flag `CFO_ENABLED`.

**Architecture:** Módulo nuevo `backend/app/cfo/agente/` (cliente Anthropic inyectable → tools de solo lectura sobre los 3 conceptos de inc1 → loop acotado → verificador cifra→evidencia → servicio orquestador con auditoría). Endpoint `POST /api/v1/cfo` con doble barrera (router condicional por flag + `require_permission`). El modelo NUNCA calcula: narra valores de tools; cifra sin evidencia ⇒ abstención.

**Tech Stack:** Python 3.12, FastAPI, Pydantic strict, `anthropic` (SDK async, lazy import), pytest. Cliente MOCKEADO en todos los tests ⇒ CI verde sin `ANTHROPIC_API_KEY`.

## Global Constraints

- **Dinero = Decimal, nunca float.** API/serialización: montos como **string**. Cero `float` en el pipeline. (regla 1)
- **Zona horaria única América/Bogotá** (`now_bogota`/`today_bogota`); fechas `YYYY-MM-DD`. (regla 2)
- **Pydantic `strict=True, extra="forbid"`** en todo modelo nuevo. (regla 3)
- **Aislamiento S1:** `app/cfo/**` solo importa la capa de **servicios** de COMPAS (`app.<dominio>.service`, `app.audit.service`, `app.auth.*`, `app.core.*`, `app.cfo.*`); **prohibido** importar `app.domain.*` o el driver de Mongo directo. Escribe solo en colecciones `cfo_*`.
- **`motor.py` cero diffs** (`backend/app/proyeccion/motor.py`). Prohibido tocarlo.
- **Catálogo de eventos CERRADO** (regla 11): solo se agregan `cfo.consulta` y `cfo.respuesta`, con comentario-CR. No inventar más.
- **Flag `CFO_ENABLED` apagado por defecto** ⇒ COMPAS byte-idéntico (router ausente de `main.py`).
- **Ningún secreto en el repo** (regla 12): `ANTHROPIC_API_KEY` solo por env var; jamás hardcodeada ni en tests.
- **Ruff limpio** (`ruff check app/cfo/` — reglas E,F,I,UP,B,ASYNC; line-length 88). Corre `ruff check --fix` antes de cada commit para el orden de imports (I001).
- **Modelo por config:** `CFO_MODEL` default `claude-haiku-4-5-20251001`.

---

### Task 1: Must-do — `iva_cuatrimestre` fail-closed por periodicidad

**Files:**
- Modify: `backend/app/cfo/calc/iva.py`
- Test: `backend/tests/cfo/test_calc_iva.py`

**Interfaces:**
- Consumes: `_liquidacion()` (existente) devuelve `dict` con clave `"periodicidad"` (str: `"cuatrimestral"`/`"bimestral"`) y `"periodos"`.
- Produces: `iva_cuatrimestre() -> ResultadoCFO` — sin cambio de firma; ahora **abstiene** (`disponible=False`, `valor=None`, `evidencia.ref="periodicidad-no-cuatrimestral"`) si la periodicidad vigente no es cuatrimestral.

- [ ] **Step 1: Write the failing test**

```python
# en backend/tests/cfo/test_calc_iva.py — añadir
import pytest
from app.cfo.calc import iva as iva_calc


@pytest.mark.asyncio
async def test_iva_cuatrimestre_abstiene_si_periodicidad_no_cuatrimestral(monkeypatch):
    async def fake_liq():
        return {
            "periodicidad": "bimestral",
            "periodos": [
                {"anio": 2026, "periodo": 4, "etiqueta": "2026-B4",
                 "neto_a_pagar": "10000.00", "proximo_pago": {"fecha": "2026-09-10"}}
            ],
        }
    monkeypatch.setattr(iva_calc, "_liquidacion", fake_liq)
    r = await iva_calc.iva_cuatrimestre()
    assert r.disponible is False
    assert r.valor is None
    assert r.evidencia.ref == "periodicidad-no-cuatrimestral"
    assert r.detalle == {"periodicidad": "bimestral"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/cfo/test_calc_iva.py::test_iva_cuatrimestre_abstiene_si_periodicidad_no_cuatrimestral -v`
Expected: FAIL (hoy devuelve disponible=True con índice erróneo).

- [ ] **Step 3: Write minimal implementation**

En `backend/app/cfo/calc/iva.py`, insertar el guard justo después de `data = await _liquidacion()` (antes del `next(...)`):

```python
    data = await _liquidacion()
    if data.get("periodicidad") != "cuatrimestral":
        # Fail-closed: el concepto asume cuatrimestral; con otra periodicidad el
        # índice y la etiqueta del período serían erróneos. Regla #1: antes que
        # publicar una cifra mal ubicada, se abstiene honestamente.
        return ResultadoCFO(
            concepto="iva_cuatrimestre",
            valor=None,
            unidad="COP",
            disponible=False,
            evidencia=Evidencia(
                fuente=fuente, fecha_corte=None, ref="periodicidad-no-cuatrimestral"
            ),
            detalle={"periodicidad": data.get("periodicidad")},
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/cfo/test_calc_iva.py -v`
Expected: PASS (nuevo test + los previos verdes).

- [ ] **Step 5: Commit**

```bash
cd backend && ruff check --fix app/cfo/calc/iva.py tests/cfo/test_calc_iva.py
git add app/cfo/calc/iva.py tests/cfo/test_calc_iva.py
git commit -m "fix(cfo): iva_cuatrimestre fail-closed si la periodicidad no es cuatrimestral"
```

---

### Task 2: Config — modelo, api_key y límites del loop

**Files:**
- Modify: `backend/app/cfo/config.py`
- Test: `backend/tests/cfo/test_config.py`

**Interfaces:**
- Produces: `cfo_model() -> str`, `cfo_api_key() -> str | None`, `cfo_max_iter() -> int`, `cfo_max_tokens() -> int`, `cfo_timeout_s() -> float`. Defaults: modelo `claude-haiku-4-5-20251001`, max_iter 3, max_tokens 1024, timeout 60.0. `cfo_api_key()` devuelve `None` si la env var está vacía/ausente.

- [ ] **Step 1: Write the failing test**

```python
# en backend/tests/cfo/test_config.py — añadir
from app.cfo import config as cfo_config


def test_cfo_model_default_y_override(monkeypatch):
    monkeypatch.delenv("CFO_MODEL", raising=False)
    assert cfo_config.cfo_model() == "claude-haiku-4-5-20251001"
    monkeypatch.setenv("CFO_MODEL", "claude-sonnet-5")
    assert cfo_config.cfo_model() == "claude-sonnet-5"


def test_cfo_api_key_none_si_ausente(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert cfo_config.cfo_api_key() is None
    monkeypatch.setenv("ANTHROPIC_API_KEY", "  ")
    assert cfo_config.cfo_api_key() is None
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert cfo_config.cfo_api_key() == "sk-test"


def test_cfo_limites_default(monkeypatch):
    for k in ("CFO_MAX_ITER", "CFO_MAX_TOKENS", "CFO_TIMEOUT_S"):
        monkeypatch.delenv(k, raising=False)
    assert cfo_config.cfo_max_iter() == 3
    assert cfo_config.cfo_max_tokens() == 1024
    assert cfo_config.cfo_timeout_s() == 60.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/cfo/test_config.py -v`
Expected: FAIL (funciones inexistentes).

- [ ] **Step 3: Write minimal implementation**

Añadir a `backend/app/cfo/config.py`:

```python
def cfo_model() -> str:
    """Modelo Claude que orquesta y narra (nunca calcula). Barato por default
    (el modelo solo elige tools y redacta); override por env a un modelo mayor."""
    return os.environ.get("CFO_MODEL", "claude-haiku-4-5-20251001").strip()


def cfo_api_key() -> str | None:
    """API key de Anthropic (SOLO env var en Render; nunca en repo). Vacía ⇒ None
    ⇒ FABS se abstiene con motivo 'sin_api_key' (nunca crashea)."""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    return key or None


def cfo_max_iter() -> int:
    return int(os.environ.get("CFO_MAX_ITER", "3"))


def cfo_max_tokens() -> int:
    return int(os.environ.get("CFO_MAX_TOKENS", "1024"))


def cfo_timeout_s() -> float:
    return float(os.environ.get("CFO_TIMEOUT_S", "60"))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/cfo/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd backend && ruff check --fix app/cfo/config.py tests/cfo/test_config.py
git add app/cfo/config.py tests/cfo/test_config.py
git commit -m "feat(cfo): config del loop (modelo, api_key, limites)"
```

---

### Task 3: CR-CFO-1 — eventos `cfo.consulta` y `cfo.respuesta` en el catálogo

**Files:**
- Modify: `backend/app/audit/events.py`
- Create: `planning/phases/fabs-inc2/CR-CFO-1.md`
- Test: `backend/tests/test_audit_events.py` (o donde viva la completitud del catálogo — buscar `CATALOGO_EVENTOS`)

**Interfaces:**
- Produces: `AuditEvento.cfo_consulta = "cfo.consulta"`, `AuditEvento.cfo_respuesta = "cfo.respuesta"`. `CATALOGO_EVENTOS` crece 60→62.

- [ ] **Step 1: Localizar y ajustar el test de completitud del catálogo**

Buscar el test que fija el tamaño/miembros del catálogo:
Run: `cd backend && grep -rn "CATALOGO_EVENTOS\|cfo.consulta\|len(.*Evento" tests/`
Si existe una aserción de tamaño (p. ej. `assert len(CATALOGO_EVENTOS) == 60`), escribir el test nuevo que espera **62** e incluye los dos valores:

```python
# donde se prueba el catálogo — añadir/ajustar
from app.audit.events import CATALOGO_EVENTOS

def test_catalogo_incluye_eventos_cfo():
    assert "cfo.consulta" in CATALOGO_EVENTOS
    assert "cfo.respuesta" in CATALOGO_EVENTOS
```
Si había un `assert len(...) == 60`, actualizarlo a `== 62` en el mismo commit (precedente: inc1 subió DOMAIN_DOCUMENTS 19→20).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/ -k catalogo -v`
Expected: FAIL (eventos no existen).

- [ ] **Step 3: Añadir los eventos al enum**

Al final del `class AuditEvento` en `backend/app/audit/events.py`, tras `meta_ingreso_eliminada`:

```python
    # ── CR-CFO-1 (2) — FABS incremento 2 (agente CFO, GO CEO 2026-08-11) ──
    # Rastro forense de cada interacción con FABS (lectura/asesoría; no mueve plata).
    # `cfo.consulta` = pregunta recibida (actor_id = usuario real); `cfo.respuesta` =
    # lo que FABS respondió, con {abstuvo, motivo, conceptos_usados, cifras+evidencia,
    # uso}. La abstención es un `cfo.respuesta` {abstuvo: true} — sin evento extra.
    # Catálogo 60 -> 62.
    cfo_consulta = "cfo.consulta"
    cfo_respuesta = "cfo.respuesta"
```

- [ ] **Step 4: Escribir el CR**

Crear `planning/phases/fabs-inc2/CR-CFO-1.md`:

```markdown
# CR-CFO-1 — Eventos de auditoría de FABS (agente CFO)

- **Fecha:** 2026-08-11 · **GO:** CEO (gate-waiver inc2; Kimi retroactivo con el paquete de inc2)
- **Regla 11:** el catálogo de eventos es cerrado; este CR lo amplía 60 → 62.

## Eventos nuevos
- `cfo.consulta` — se emite al recibir una pregunta para FABS. `entidad="cfo"`,
  `actor_id`=usuario autenticado real, `metadata={pregunta, canal:"api"}`.
- `cfo.respuesta` — se emite tras responder. `metadata={abstuvo, motivo, conceptos_usados,
  cifras:[{valor,unidad,evidencia}], uso:{modelo,tokens_in,tokens_out,iteraciones}}`.
  La **abstención** es un `cfo.respuesta` con `abstuvo=true` (no hay evento propio).

## Política de fallo (O1)
Una consulta a FABS es **lectura** (no mueve plata). Si la escritura de auditoría falla,
se registra `logger.error`+Sentry y **se continúa** (rama "eventos no críticos" de
`emit_audit`). `cfo.consulta` se emite ANTES de responder (rastro de la pregunta aun si el
loop falla).

## Por qué es crítico / gate
FABS lee y narra cifras de plata para decisiones. El rastro forense de qué preguntó cada
usuario y qué respondió FABS (con qué evidencia) es requisito del sistema.
```

- [ ] **Step 5: Run tests + commit**

Run: `cd backend && python -m pytest tests/ -k "catalogo or audit" -v`
Expected: PASS.

```bash
cd backend && ruff check --fix app/audit/events.py
git add app/audit/events.py tests/ ../planning/phases/fabs-inc2/CR-CFO-1.md
git commit -m "feat(cfo): CR-CFO-1 eventos cfo.consulta/cfo.respuesta (catalogo 60->62)"
```

---

### Task 4: `modelos.py` — salida tipada `RespuestaCFO`

**Files:**
- Create: `backend/app/cfo/agente/__init__.py` (vacío)
- Create: `backend/app/cfo/agente/modelos.py`
- Test: `backend/tests/cfo/agente/__init__.py` (vacío) + `backend/tests/cfo/agente/test_modelos.py`

**Interfaces:**
- Produces: `RespuestaCFO`, `CifraPublicada`, `UsoLLM` (todos `strict=True, extra="forbid"`).
  - `CifraPublicada{valor:str, unidad:str, evidencia:Evidencia}`
  - `UsoLLM{modelo:str, tokens_in:int, tokens_out:int, iteraciones:int}`
  - `RespuestaCFO{texto:str, abstuvo:bool, motivo:str|None=None, conceptos_usados:list[str]=[], cifras:list[CifraPublicada]=[], uso:UsoLLM}`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/cfo/agente/test_modelos.py
import pytest
from pydantic import ValidationError

from app.cfo.agente.modelos import CifraPublicada, RespuestaCFO, UsoLLM
from app.cfo.calc.evidencia import Evidencia


def _uso():
    return UsoLLM(modelo="claude-haiku-4-5-20251001", tokens_in=10, tokens_out=20, iteraciones=1)


def test_respuesta_cfo_valida():
    ev = Evidencia(fuente="caja.service.caja_diaria", fecha_corte="2026-08-11", ref="2026-08")
    r = RespuestaCFO(
        texto="La caja hoy es $704.722.003.",
        abstuvo=False,
        conceptos_usados=["caja_hoy"],
        cifras=[CifraPublicada(valor="704722003", unidad="COP", evidencia=ev)],
        uso=_uso(),
    )
    assert r.abstuvo is False
    assert r.cifras[0].valor == "704722003"


def test_respuesta_cfo_rechaza_campo_extra():
    with pytest.raises(ValidationError):
        RespuestaCFO(texto="x", abstuvo=True, uso=_uso(), foo=1)
```

- [ ] **Step 2: Run test to verify it fails** — `python -m pytest tests/cfo/agente/test_modelos.py -v` → FAIL (módulo inexistente).

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/cfo/agente/modelos.py
"""FABS · salida tipada del agente. Ninguna cifra viaja suelta: cada una lleva su
Evidencia. `strict=True, extra="forbid"` (regla 3). Montos como string (regla 1)."""

from pydantic import BaseModel, ConfigDict, Field

from app.cfo.calc.evidencia import Evidencia


class CifraPublicada(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    valor: str
    unidad: str
    evidencia: Evidencia


class UsoLLM(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    modelo: str
    tokens_in: int
    tokens_out: int
    iteraciones: int


class RespuestaCFO(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    texto: str
    abstuvo: bool
    motivo: str | None = None
    conceptos_usados: list[str] = Field(default_factory=list)
    cifras: list[CifraPublicada] = Field(default_factory=list)
    uso: UsoLLM
```

- [ ] **Step 4: Run test** → PASS.
- [ ] **Step 5: Commit**

```bash
cd backend && ruff check --fix app/cfo/agente/ tests/cfo/agente/
git add app/cfo/agente/__init__.py app/cfo/agente/modelos.py tests/cfo/agente/
git commit -m "feat(cfo): modelos de salida del agente (RespuestaCFO)"
```

---

### Task 5: `tools.py` — esquemas + dispatcher de solo lectura

**Files:**
- Create: `backend/app/cfo/agente/tools.py`
- Test: `backend/tests/cfo/agente/test_tools.py`

**Interfaces:**
- Consumes: `app.cfo.calc.caja.caja_hoy`, `app.cfo.calc.runway.runway`, `app.cfo.calc.iva.iva_cuatrimestre` (todas `() -> ResultadoCFO`).
- Produces:
  - `TOOLS_SCHEMA: list[dict]` — definiciones de tools Anthropic (3, sin parámetros).
  - `DISPATCH: dict[str, Callable[[], Awaitable[ResultadoCFO]]]` — nombres: `caja_disponible_hoy`, `runway_meses`, `iva_del_cuatrimestre`.
  - `async def ejecutar_tool(nombre: str) -> ResultadoCFO` — `KeyError` si el nombre no está.
  - `def resultado_a_dict(r: ResultadoCFO) -> dict` — serializa para el modelo (valor→str|None).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/cfo/agente/test_tools.py
from decimal import Decimal

import pytest

from app.cfo.agente import tools
from app.cfo.calc.evidencia import Evidencia, ResultadoCFO


def _res(valor):
    return ResultadoCFO(
        concepto="caja_hoy", valor=valor, unidad="COP", disponible=valor is not None,
        evidencia=Evidencia(fuente="f", fecha_corte="2026-08-11", ref="2026-08"),
    )


def test_schema_tres_tools_sin_parametros():
    nombres = {t["name"] for t in tools.TOOLS_SCHEMA}
    assert nombres == {"caja_disponible_hoy", "runway_meses", "iva_del_cuatrimestre"}
    for t in tools.TOOLS_SCHEMA:
        assert t["input_schema"]["properties"] == {}


def test_resultado_a_dict_serializa_valor_a_string():
    d = tools.resultado_a_dict(_res(Decimal("704722003")))
    assert d["valor"] == "704722003"
    assert d["disponible"] is True
    assert d["evidencia"]["ref"] == "2026-08"
    d0 = tools.resultado_a_dict(_res(None))
    assert d0["valor"] is None
    assert d0["disponible"] is False


@pytest.mark.asyncio
async def test_ejecutar_tool_despacha(monkeypatch):
    async def fake():
        return _res(Decimal("123"))
    monkeypatch.setitem(tools.DISPATCH, "caja_disponible_hoy", fake)
    r = await tools.ejecutar_tool("caja_disponible_hoy")
    assert r.valor == Decimal("123")


@pytest.mark.asyncio
async def test_ejecutar_tool_desconocida_falla():
    with pytest.raises(KeyError):
        await tools.ejecutar_tool("no_existe")
```

- [ ] **Step 2: Run test** → FAIL.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/cfo/agente/tools.py
"""FABS · tools de SOLO LECTURA que el modelo puede invocar. Cada tool envuelve un
concepto de `app.cfo.calc` y devuelve su ResultadoCFO completo (incl. disponible y
evidencia). El dispatcher es cerrado: una tool desconocida es error, nunca se inventa.
Serialización para el modelo: valor→string (regla 1, jamás float)."""

from collections.abc import Awaitable, Callable

from app.cfo.calc import caja, iva, runway
from app.cfo.calc.evidencia import ResultadoCFO

DISPATCH: dict[str, Callable[[], Awaitable[ResultadoCFO]]] = {
    "caja_disponible_hoy": caja.caja_hoy,
    "runway_meses": runway.runway,
    "iva_del_cuatrimestre": iva.iva_cuatrimestre,
}

TOOLS_SCHEMA: list[dict] = [
    {
        "name": "caja_disponible_hoy",
        "description": (
            "Caja disponible HOY en COP: último saldo real de la serie diaria de "
            "COMPAS, con su fecha de corte. Si no hay datos, disponible=false."
        ),
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "runway_meses",
        "description": (
            "Meses de caja restantes al ritmo de quema actual (KPI runway de la "
            "proyección vigente). Sin quema neta o sin configuración, disponible=false."
        ),
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "iva_del_cuatrimestre",
        "description": (
            "IVA neto a pagar del cuatrimestre fiscal vigente en COP, con la fecha "
            "límite DIAN. Solo válido con periodicidad cuatrimestral; si no, disponible=false."
        ),
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
]


async def ejecutar_tool(nombre: str) -> ResultadoCFO:
    return await DISPATCH[nombre]()


def resultado_a_dict(r: ResultadoCFO) -> dict:
    return {
        "concepto": r.concepto,
        "disponible": r.disponible,
        "valor": str(r.valor) if r.valor is not None else None,
        "unidad": r.unidad,
        "evidencia": {
            "fuente": r.evidencia.fuente,
            "fecha_corte": r.evidencia.fecha_corte,
            "ref": r.evidencia.ref,
        },
        "detalle": r.detalle,
    }
```

- [ ] **Step 4: Run test** → PASS.
- [ ] **Step 5: Commit**

```bash
cd backend && ruff check --fix app/cfo/agente/tools.py tests/cfo/agente/test_tools.py
git add app/cfo/agente/tools.py tests/cfo/agente/test_tools.py
git commit -m "feat(cfo): tools de solo lectura + dispatcher del agente"
```

---

### Task 6: `prompt.py` — system prompt (el modelo nunca calcula)

**Files:**
- Create: `backend/app/cfo/agente/prompt.py`
- Test: `backend/tests/cfo/agente/test_prompt.py`

**Interfaces:**
- Produces: `SYSTEM_PROMPT: str` (invariantes del sistema) y `CORRECTIVO: str` (plantilla para el reintento; contiene `{cifras}` y `{valores}` como marcadores `str.format`).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/cfo/agente/test_prompt.py
from app.cfo.agente.prompt import CORRECTIVO, SYSTEM_PROMPT


def test_system_prompt_fija_invariantes():
    p = SYSTEM_PROMPT.lower()
    assert "nunca calcul" in p          # el modelo no calcula
    assert "herramienta" in p or "tool" in p
    assert "abst" in p                   # abstenerse
    assert "evidencia" in p or "fecha de corte" in p


def test_correctivo_es_formateable():
    out = CORRECTIVO.format(cifras="$999", valores="caja=$704.722.003")
    assert "$999" in out and "704.722.003" in out
```

- [ ] **Step 2: Run test** → FAIL.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/cfo/agente/prompt.py
"""FABS · system prompt. Codifica la regla #1: el modelo NUNCA calcula ni inventa;
solo narra los valores que devuelven las herramientas, con su fecha de corte; si un
dato no está disponible, se abstiene honestamente."""

SYSTEM_PROMPT = (
    "Eres FABS, el analista financiero de IA de RODDOS S.A.S. Complementas al CFO "
    "humano; no lo reemplazas. Respondes en español, claro y conciso.\n\n"
    "REGLAS INQUEBRANTABLES:\n"
    "1. NUNCA calculas, sumas, estimas ni extrapolas cifras. Toda cifra que menciones "
    "debe provenir LITERALMENTE del resultado de una herramienta. Si necesitas un "
    "número, llama la herramienta correspondiente.\n"
    "2. Cada herramienta devuelve un valor con su evidencia (fuente + fecha de corte). "
    "Al dar una cifra, menciona su fecha de corte.\n"
    "3. Si una herramienta responde disponible=false, NO inventes un número: dilo con "
    "honestidad ('con los datos disponibles no puedo confirmar X'). Jamás un $0 falso.\n"
    "4. Si la pregunta requiere algo para lo que no tienes herramienta, dilo con "
    "claridad; no improvises.\n"
    "5. No mueves dinero ni ejecutas operaciones: solo informas.\n\n"
    "Herramientas disponibles: caja disponible hoy, runway (meses de caja), IVA del "
    "cuatrimestre. Úsalas para responder con cifras reales y trazables."
)

CORRECTIVO = (
    "Tu respuesta anterior incluyó cifras que NO provienen de ninguna herramienta: "
    "{cifras}. Reescribe la respuesta usando EXCLUSIVAMENTE estos valores verificados: "
    "{valores}. Si no puedes responder con ellos, abstente honestamente. No inventes números."
)
```

- [ ] **Step 4: Run test** → PASS.
- [ ] **Step 5: Commit**

```bash
cd backend && ruff check --fix app/cfo/agente/prompt.py tests/cfo/agente/test_prompt.py
git add app/cfo/agente/prompt.py tests/cfo/agente/test_prompt.py
git commit -m "feat(cfo): system prompt del agente (el modelo nunca calcula)"
```

---

### Task 7: `verificador.py` — cifra→evidencia (el control crítico)

**Files:**
- Create: `backend/app/cfo/agente/verificador.py`
- Test: `backend/tests/cfo/agente/test_verificador.py`

**Interfaces:**
- Consumes: `ResultadoCFO` (con `disponible`, `valor: Decimal|None`, `unidad` ∈ {"COP","meses"}).
- Produces:
  - `def extraer_cifras(texto: str) -> list[tuple[Decimal, str, str]]` — `(valor, unidad, token_original)`; `unidad` ∈ {"COP","meses"}.
  - `Veredicto` (dataclass frozen): `ok: bool`, `cifras_sin_evidencia: list[str]` (tokens originales huérfanos).
  - `def verificar(texto: str, resultados: list[ResultadoCFO]) -> Veredicto`.

- [ ] **Step 1: Write the failing test (batería adversarial)**

```python
# backend/tests/cfo/agente/test_verificador.py
from decimal import Decimal

from app.cfo.agente.verificador import extraer_cifras, verificar
from app.cfo.calc.evidencia import Evidencia, ResultadoCFO


def _cop(valor):
    return ResultadoCFO(concepto="caja_hoy", valor=valor, unidad="COP", disponible=True,
                        evidencia=Evidencia(fuente="f", fecha_corte="2026-08-11", ref="2026-08"))


def _meses(valor):
    return ResultadoCFO(concepto="runway", valor=valor, unidad="meses", disponible=True,
                        evidencia=Evidencia(fuente="f", fecha_corte=None, ref="2026-08"))


def test_extrae_montos_y_meses_ignora_anios_y_fechas():
    texto = ("En 2026, al 10 de septiembre, la caja es $704.722.003 y el runway "
             "es de 4,2 meses. Período C2.")
    cifras = {(v, u) for v, u, _ in extraer_cifras(texto)}
    assert (Decimal("704722003"), "COP") in cifras
    assert (Decimal("4.2"), "meses") in cifras
    # 2026 (año), 10 (día), C2 (etiqueta) NO son cifras monetarias/unitarias
    assert all(not (v == Decimal("2026")) for v, _, _ in extraer_cifras(texto))


def test_ok_cuando_toda_cifra_tiene_evidencia():
    texto = "La caja hoy es $704.722.003 (al 2026-08-11)."
    v = verificar(texto, [_cop(Decimal("704722003"))])
    assert v.ok is True
    assert v.cifras_sin_evidencia == []


def test_atrapa_monto_inventado():
    texto = "La caja hoy es $704.722.003, pero podrías tener hasta $50.000.000 extra."
    v = verificar(texto, [_cop(Decimal("704722003"))])
    assert v.ok is False
    assert any("50.000.000" in t for t in v.cifras_sin_evidencia)


def test_atrapa_suma_inventada():
    # el modelo sumó dos evidencias — resultado sin respaldo directo
    texto = "En total son $740.926.701."
    v = verificar(texto, [_cop(Decimal("704722003")), _cop(Decimal("36204698"))])
    assert v.ok is False


def test_tolerancia_cop_1_peso():
    texto = "Caja $704.722.004."  # +1 por redondeo
    v = verificar(texto, [_cop(Decimal("704722003"))])
    assert v.ok is True


def test_meses_fuera_de_tolerancia_falla():
    texto = "El runway es de 6 meses."
    v = verificar(texto, [_meses(Decimal("4.2"))])
    assert v.ok is False


def test_evidencia_no_disponible_no_respalda_cifra():
    # un ResultadoCFO abstenido NO respalda ninguna cifra
    r = ResultadoCFO(concepto="iva_cuatrimestre", valor=None, unidad="COP", disponible=False,
                     evidencia=Evidencia(fuente="f", fecha_corte=None, ref="x"))
    v = verificar("El IVA es $36.204.698.", [r])
    assert v.ok is False


def test_dolares_cero_falso_es_atrapado():
    v = verificar("No debes nada: $0.", [_cop(Decimal("704722003"))])
    assert v.ok is False
```

- [ ] **Step 2: Run test** → FAIL (módulo inexistente).

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/cfo/agente/verificador.py
"""FABS · verificador cifra→evidencia (EL control crítico, lección Deloitte).

Toda cifra monetaria o con unidad que aparezca en la respuesta del modelo debe estar
dentro de tolerancia de ALGÚN valor devuelto por las tools de este turno (conjunto
cerrado de evidencias). Si una cifra no tiene respaldo, el veredicto es `ok=False` y
esa cifra no debe publicarse (regla #1). Heurística conservadora: exige evidencia a
los montos ($ / separador de miles) y a los números con unidad de meses; ignora años,
fechas y ordinales pequeños sin formato de dinero (para no abstenerse de lo inocuo)."""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.cfo.calc.evidencia import ResultadoCFO

_TOL_COP = Decimal("1")       # ±$1 COP por redondeo
_TOL_MESES = Decimal("0.1")   # ±0,1 meses

# Monto: prefijo $ (con o sin separadores) O número con separador de miles es-CO.
_RE_MONTO = re.compile(
    r"\$\s?\d+(?:\.\d{3})*(?:,\d{1,2})?"          # $50.000.000 · $0 · $1.234,56
    r"|(?<![\d.,])\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?"  # 704.722.003 (requiere separador)
)
# Meses: número (posible decimal con coma) seguido de 'mes'/'meses'.
_RE_MESES = re.compile(r"(\d+(?:,\d+)?)\s*mes(?:es)?\b", re.IGNORECASE)


def _a_decimal_es(token: str) -> Decimal | None:
    t = token.replace("$", "").replace(" ", "").strip()
    t = t.replace(".", "").replace(",", ".")
    try:
        return Decimal(t)
    except InvalidOperation:
        return None


@dataclass(frozen=True)
class Veredicto:
    ok: bool
    cifras_sin_evidencia: list[str]


def extraer_cifras(texto: str) -> list[tuple[Decimal, str, str]]:
    cifras: list[tuple[Decimal, str, str]] = []
    # Meses primero, y marcamos sus tramos para no re-capturar el número como monto.
    tramos_meses: list[tuple[int, int]] = []
    for m in _RE_MESES.finditer(texto):
        val = _a_decimal_es(m.group(1))
        if val is not None:
            cifras.append((val, "meses", m.group(0)))
            tramos_meses.append((m.start(1), m.end(1)))
    for m in _RE_MONTO.finditer(texto):
        # saltar si el número pertenece a un tramo de 'meses'
        if any(s <= m.start() < e for s, e in tramos_meses):
            continue
        val = _a_decimal_es(m.group(0))
        if val is not None:
            cifras.append((val, "COP", m.group(0)))
    return cifras


def verificar(texto: str, resultados: list[ResultadoCFO]) -> Veredicto:
    ev_cop = [r.valor for r in resultados
              if r.disponible and r.valor is not None and r.unidad == "COP"]
    ev_meses = [r.valor for r in resultados
                if r.disponible and r.valor is not None and r.unidad == "meses"]
    huerfanas: list[str] = []
    for valor, unidad, token in extraer_cifras(texto):
        pool = ev_cop if unidad == "COP" else ev_meses
        tol = _TOL_COP if unidad == "COP" else _TOL_MESES
        if not any(abs(valor - e) <= tol for e in pool):
            huerfanas.append(token)
    return Veredicto(ok=not huerfanas, cifras_sin_evidencia=huerfanas)
```

- [ ] **Step 4: Run test** → PASS (los 8 casos adversariales).

Nota para el revisor: este es el punto más delicado del inc2. Si un caso adversarial no pasa, ajustar la heurística SIN debilitar la detección de montos inventados (preferir falso-positivo→reintento antes que falso-negativo→cifra sin evidencia publicada).

- [ ] **Step 5: Commit**

```bash
cd backend && ruff check --fix app/cfo/agente/verificador.py tests/cfo/agente/test_verificador.py
git add app/cfo/agente/verificador.py tests/cfo/agente/test_verificador.py
git commit -m "feat(cfo): verificador cifra->evidencia (control critico anti-alucinacion)"
```

---

### Task 8: `cliente.py` — wrapper Anthropic (lazy, inyectable) + dep

**Files:**
- Create: `backend/app/cfo/agente/cliente.py`
- Modify: `backend/requirements.txt`
- Create: `backend/tests/cfo/agente/fakes.py` (helper de tests reutilizable)
- Test: `backend/tests/cfo/agente/test_cliente.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) BloqueTexto{texto:str}`
  - `@dataclass(frozen=True) BloqueToolUse{id:str, nombre:str, input:dict}`
  - `@dataclass(frozen=True) RespuestaLLM{stop_reason:str, bloques:list, tokens_in:int, tokens_out:int}`
  - `class ClienteLLM(Protocol)`: `async def crear(self, *, system:str, messages:list[dict], tools:list[dict]) -> RespuestaLLM`
  - `class ClienteAnthropic` — implementación real (import perezoso de `anthropic`).
  - `def crear_cliente() -> ClienteLLM | None` — `None` si no hay `ANTHROPIC_API_KEY`.
  - `def contenido_asistente(bloques: list) -> list[dict]` — reconstruye el `content` del turno assistant en formato wire Anthropic (para el historial del loop).
- En `fakes.py`: `class ClienteFake` con `__init__(self, guiones: list[RespuestaLLM])` que devuelve un guion por llamada a `crear`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/cfo/agente/test_cliente.py
from app.cfo.agente import cliente as cli


def test_crear_cliente_none_sin_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert cli.crear_cliente() is None


def test_crear_cliente_instancia_con_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    c = cli.crear_cliente()
    assert isinstance(c, cli.ClienteAnthropic)


def test_contenido_asistente_reconstruye_wire():
    bloques = [cli.BloqueTexto(texto="hola"),
               cli.BloqueToolUse(id="t1", nombre="caja_disponible_hoy", input={})]
    wire = cli.contenido_asistente(bloques)
    assert wire[0] == {"type": "text", "text": "hola"}
    assert wire[1] == {"type": "tool_use", "id": "t1",
                       "name": "caja_disponible_hoy", "input": {}}
```

- [ ] **Step 2: Run test** → FAIL.

- [ ] **Step 3a: Añadir la dependencia**

En `backend/requirements.txt`, añadir (pin a la última estable que instale limpio; verificar con `pip install anthropic` y fijar la versión resultante):

```
anthropic==0.69.0  # FABS inc2: SDK del LLM del agente CFO (import perezoso; solo runtime)
```
(Si 0.69.0 no resuelve, usar la última estable que `pip install anthropic && python -c "import anthropic"` acepte y fijarla.)

- [ ] **Step 3b: Write minimal implementation**

```python
# backend/app/cfo/agente/cliente.py
"""FABS · wrapper del SDK Anthropic. Import PEREZOSO (la dep solo se toca al invocar de
verdad; los tests usan un cliente falso). Normaliza la respuesta del SDK a RespuestaLLM
para desacoplar el loop del formato del SDK. Sin API key ⇒ crear_cliente() = None."""

from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Protocol

from app.cfo import config


@dataclass(frozen=True)
class BloqueTexto:
    texto: str


@dataclass(frozen=True)
class BloqueToolUse:
    id: str
    nombre: str
    input: dict


@dataclass(frozen=True)
class RespuestaLLM:
    stop_reason: str
    bloques: list  # list[BloqueTexto | BloqueToolUse]
    tokens_in: int
    tokens_out: int


class ClienteLLM(Protocol):
    def crear(
        self, *, system: str, messages: list[dict], tools: list[dict]
    ) -> Awaitable[RespuestaLLM]: ...


def contenido_asistente(bloques: list) -> list[dict]:
    out: list[dict] = []
    for b in bloques:
        if isinstance(b, BloqueTexto):
            out.append({"type": "text", "text": b.texto})
        elif isinstance(b, BloqueToolUse):
            out.append({"type": "tool_use", "id": b.id, "name": b.nombre, "input": b.input})
    return out


class ClienteAnthropic:
    def __init__(self, api_key: str, modelo: str, max_tokens: int, timeout_s: float):
        from anthropic import AsyncAnthropic  # import perezoso

        self._client = AsyncAnthropic(api_key=api_key, timeout=timeout_s)
        self._modelo = modelo
        self._max_tokens = max_tokens

    async def crear(
        self, *, system: str, messages: list[dict], tools: list[dict]
    ) -> RespuestaLLM:
        resp = await self._client.messages.create(
            model=self._modelo,
            max_tokens=self._max_tokens,
            temperature=0.1,
            system=system,
            messages=messages,
            tools=tools,
        )
        bloques: list = []
        for b in resp.content:
            if b.type == "text":
                bloques.append(BloqueTexto(texto=b.text))
            elif b.type == "tool_use":
                bloques.append(BloqueToolUse(id=b.id, nombre=b.name, input=dict(b.input)))
        return RespuestaLLM(
            stop_reason=resp.stop_reason,
            bloques=bloques,
            tokens_in=resp.usage.input_tokens,
            tokens_out=resp.usage.output_tokens,
        )


def crear_cliente() -> ClienteLLM | None:
    key = config.cfo_api_key()
    if key is None:
        return None
    return ClienteAnthropic(
        api_key=key,
        modelo=config.cfo_model(),
        max_tokens=config.cfo_max_tokens(),
        timeout_s=config.cfo_timeout_s(),
    )
```

- [ ] **Step 3c: Fake reutilizable**

```python
# backend/tests/cfo/agente/fakes.py
"""Cliente LLM falso para tests del loop/servicio (sin API real)."""

from app.cfo.agente.cliente import RespuestaLLM


class ClienteFake:
    def __init__(self, guiones: list[RespuestaLLM]):
        self._guiones = list(guiones)
        self.llamadas: list[dict] = []

    async def crear(self, *, system: str, messages: list[dict], tools: list[dict]) -> RespuestaLLM:
        self.llamadas.append({"system": system, "messages": messages, "tools": tools})
        if not self._guiones:
            raise AssertionError("ClienteFake sin más guiones")
        return self._guiones.pop(0)
```

- [ ] **Step 4: Run test** → PASS. (No se instala `anthropic` en local para el test: `crear_cliente()` con key construye `ClienteAnthropic`, cuyo `__init__` importa `anthropic`. Si la dep no está instalada localmente, el test `test_crear_cliente_instancia_con_key` fallará al importar. Instalar la dep en el entorno de test: `pip install anthropic`. En CI la dep está en requirements.txt.)

- [ ] **Step 5: Commit**

```bash
cd backend && ruff check --fix app/cfo/agente/cliente.py tests/cfo/agente/
git add app/cfo/agente/cliente.py tests/cfo/agente/test_cliente.py tests/cfo/agente/fakes.py requirements.txt
git commit -m "feat(cfo): cliente Anthropic inyectable (lazy) + dep anthropic"
```

---

### Task 9: `loop.py` — ciclo acotado modelo↔tool

**Files:**
- Create: `backend/app/cfo/agente/loop.py`
- Test: `backend/tests/cfo/agente/test_loop.py`

**Interfaces:**
- Consumes: `ClienteLLM` (`.crear`), `RespuestaLLM`/`BloqueTexto`/`BloqueToolUse`/`contenido_asistente` (cliente.py), `tools.TOOLS_SCHEMA`/`ejecutar_tool`/`resultado_a_dict`, `prompt.SYSTEM_PROMPT`.
- Produces:
  - `@dataclass ResultadoLoop{texto: str|None, resultados: list[ResultadoCFO], tokens_in:int, tokens_out:int, iteraciones:int}`
  - `async def conversar(cliente, mensajes: list[dict], *, max_iter: int, system: str = SYSTEM_PROMPT) -> ResultadoLoop` — corre el ciclo; `texto=None` si agota `max_iter` sin texto final.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/cfo/agente/test_loop.py
from decimal import Decimal

import pytest

from app.cfo.agente import loop as loop_mod
from app.cfo.agente.cliente import BloqueTexto, BloqueToolUse, RespuestaLLM
from app.cfo.calc.evidencia import Evidencia, ResultadoCFO
from tests.cfo.agente.fakes import ClienteFake


def _res():
    return ResultadoCFO(concepto="caja_hoy", valor=Decimal("704722003"), unidad="COP",
                        disponible=True,
                        evidencia=Evidencia(fuente="f", fecha_corte="2026-08-11", ref="2026-08"))


@pytest.mark.asyncio
async def test_conversar_tool_luego_texto(monkeypatch):
    async def fake_tool(nombre):
        return _res()
    monkeypatch.setattr(loop_mod, "ejecutar_tool", fake_tool)
    guiones = [
        RespuestaLLM("tool_use", [BloqueToolUse(id="t1", nombre="caja_disponible_hoy", input={})], 5, 3),
        RespuestaLLM("end_turn", [BloqueTexto(texto="La caja es $704.722.003.")], 4, 8),
    ]
    r = await loop_mod.conversar(ClienteFake(guiones), [{"role": "user", "content": "¿caja?"}], max_iter=3)
    assert r.texto == "La caja es $704.722.003."
    assert len(r.resultados) == 1 and r.resultados[0].valor == Decimal("704722003")
    assert r.tokens_in == 9 and r.tokens_out == 11 and r.iteraciones == 2


@pytest.mark.asyncio
async def test_conversar_agota_iteraciones(monkeypatch):
    async def fake_tool(nombre):
        return _res()
    monkeypatch.setattr(loop_mod, "ejecutar_tool", fake_tool)
    # siempre pide tool → nunca da texto
    guiones = [RespuestaLLM("tool_use", [BloqueToolUse(id=f"t{i}", nombre="caja_disponible_hoy", input={})], 1, 1)
               for i in range(5)]
    r = await loop_mod.conversar(ClienteFake(guiones), [{"role": "user", "content": "x"}], max_iter=3)
    assert r.texto is None
    assert r.iteraciones == 3
```

- [ ] **Step 2: Run test** → FAIL.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/cfo/agente/loop.py
"""FABS · loop acotado modelo↔tool (D1). Corre ≤ max_iter rondas: si el modelo pide
tools, se ejecutan (solo lectura) y se realimentan; si da texto final, termina. No
verifica (eso lo hace el servicio). Determinista: temp 0.1 la fija el cliente."""

import json
from dataclasses import dataclass

from app.cfo.agente.cliente import (
    BloqueTexto,
    BloqueToolUse,
    ClienteLLM,
    contenido_asistente,
)
from app.cfo.agente.prompt import SYSTEM_PROMPT
from app.cfo.agente.tools import TOOLS_SCHEMA, ejecutar_tool, resultado_a_dict
from app.cfo.calc.evidencia import ResultadoCFO


@dataclass
class ResultadoLoop:
    texto: str | None
    resultados: list[ResultadoCFO]
    tokens_in: int
    tokens_out: int
    iteraciones: int


def _texto_de(bloques: list) -> str | None:
    partes = [b.texto for b in bloques if isinstance(b, BloqueTexto)]
    return "\n".join(partes).strip() if partes else None


async def conversar(
    cliente: ClienteLLM,
    mensajes: list[dict],
    *,
    max_iter: int,
    system: str = SYSTEM_PROMPT,
) -> ResultadoLoop:
    mensajes = list(mensajes)
    resultados: list[ResultadoCFO] = []
    tin = tout = 0
    for i in range(1, max_iter + 1):
        resp = await cliente.crear(system=system, messages=mensajes, tools=TOOLS_SCHEMA)
        tin += resp.tokens_in
        tout += resp.tokens_out
        usos = [b for b in resp.bloques if isinstance(b, BloqueToolUse)]
        if not usos:
            return ResultadoLoop(_texto_de(resp.bloques), resultados, tin, tout, i)
        # ejecutar tools y realimentar
        mensajes.append({"role": "assistant", "content": contenido_asistente(resp.bloques)})
        contenido_tool: list[dict] = []
        for u in usos:
            r = await ejecutar_tool(u.nombre)
            resultados.append(r)
            contenido_tool.append({
                "type": "tool_result",
                "tool_use_id": u.id,
                "content": json.dumps(resultado_a_dict(r), ensure_ascii=False),
            })
        mensajes.append({"role": "user", "content": contenido_tool})
    return ResultadoLoop(None, resultados, tin, tout, max_iter)
```

- [ ] **Step 4: Run test** → PASS.
- [ ] **Step 5: Commit**

```bash
cd backend && ruff check --fix app/cfo/agente/loop.py tests/cfo/agente/test_loop.py
git add app/cfo/agente/loop.py tests/cfo/agente/test_loop.py
git commit -m "feat(cfo): loop acotado modelo<->tool"
```

---

### Task 10: `servicio.py` — orquestador (verify/retry/abstención + auditoría)

**Files:**
- Create: `backend/app/cfo/agente/servicio.py`
- Test: `backend/tests/cfo/agente/test_servicio.py`

**Interfaces:**
- Consumes: `crear_cliente`/`ClienteLLM` (cliente), `conversar`/`ResultadoLoop` (loop), `verificar` (verificador), `CORRECTIVO` (prompt), `RespuestaCFO`/`CifraPublicada`/`UsoLLM` (modelos), `config.cfo_max_iter`/`cfo_model`, `emit_audit`/`AuditEvento` (audit.service/events).
- Produces: `async def consultar(pregunta: str, *, actor_id: str, cliente: ClienteLLM | None = None) -> RespuestaCFO`. Si `cliente is None`, usa `crear_cliente()`; si sigue `None` (sin key) ⇒ abstención `motivo="sin_api_key"`. Emite `cfo.consulta` (antes) y `cfo.respuesta` (después), ambos fail-soft.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/cfo/agente/test_servicio.py
from decimal import Decimal

import pytest

from app.cfo.agente import servicio as srv
from app.cfo.agente.cliente import BloqueTexto, BloqueToolUse, RespuestaLLM
from app.cfo.calc.evidencia import Evidencia, ResultadoCFO
from tests.cfo.agente.fakes import ClienteFake


@pytest.fixture(autouse=True)
def _audit(monkeypatch):
    eventos = []
    async def fake_emit(evento, entidad, entidad_id=None, actor_id=None, metadata=None):
        eventos.append((str(evento), metadata))
    monkeypatch.setattr(srv, "emit_audit", fake_emit)
    return eventos


def _res():
    return ResultadoCFO(concepto="caja_hoy", valor=Decimal("704722003"), unidad="COP",
                        disponible=True,
                        evidencia=Evidencia(fuente="f", fecha_corte="2026-08-11", ref="2026-08"))


@pytest.mark.asyncio
async def test_sin_key_abstiene(monkeypatch, _audit):
    monkeypatch.setattr(srv, "crear_cliente", lambda: None)
    r = await srv.consultar("¿caja?", actor_id="u1")
    assert r.abstuvo is True and r.motivo == "sin_api_key"
    assert [e[0] for e in _audit] == ["cfo.consulta", "cfo.respuesta"]


@pytest.mark.asyncio
async def test_camino_feliz(monkeypatch, _audit):
    async def fake_tool(nombre):
        return _res()
    monkeypatch.setattr("app.cfo.agente.loop.ejecutar_tool", fake_tool)
    guiones = [
        RespuestaLLM("tool_use", [BloqueToolUse(id="t1", nombre="caja_disponible_hoy", input={})], 5, 3),
        RespuestaLLM("end_turn", [BloqueTexto(texto="La caja hoy es $704.722.003.")], 4, 8),
    ]
    r = await srv.consultar("¿caja?", actor_id="u1", cliente=ClienteFake(guiones))
    assert r.abstuvo is False
    assert r.cifras[0].valor == "704722003"
    assert "caja_hoy" in r.conceptos_usados
    resp_meta = [m for e, m in _audit if e == "cfo.respuesta"][0]
    assert resp_meta["abstuvo"] is False


@pytest.mark.asyncio
async def test_alucinacion_reintento_falla_abstiene(monkeypatch, _audit):
    async def fake_tool(nombre):
        return _res()
    monkeypatch.setattr("app.cfo.agente.loop.ejecutar_tool", fake_tool)
    # 1ª conversación: tool + texto con cifra inventada. Reintento: texto sigue inventando.
    guiones = [
        RespuestaLLM("tool_use", [BloqueToolUse(id="t1", nombre="caja_disponible_hoy", input={})], 1, 1),
        RespuestaLLM("end_turn", [BloqueTexto(texto="Tienes $999.999.999.")], 1, 1),
        RespuestaLLM("end_turn", [BloqueTexto(texto="Bueno, $888.888.888.")], 1, 1),
    ]
    r = await srv.consultar("¿caja?", actor_id="u1", cliente=ClienteFake(guiones))
    assert r.abstuvo is True and r.motivo == "verificacion"
```

- [ ] **Step 2: Run test** → FAIL.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/cfo/agente/servicio.py
"""FABS · orquestador de una consulta (D2). Flujo: emite cfo.consulta → corre el loop
→ verifica cifra→evidencia → si falla, UN reintento correctivo → verifica → publica o
se abstiene (dura). Emite cfo.respuesta. La auditoría es fail-soft (lectura: no bloquea
la respuesta si la BD de auditoría falla; O1 rama no-crítica)."""

import logging

from app.audit.events import AuditEvento
from app.audit.service import emit_audit
from app.cfo import config
from app.cfo.agente.cliente import ClienteLLM, crear_cliente
from app.cfo.agente.loop import ResultadoLoop, conversar
from app.cfo.agente.modelos import CifraPublicada, RespuestaCFO, UsoLLM
from app.cfo.agente.prompt import CORRECTIVO
from app.cfo.agente.verificador import verificar
from app.cfo.calc.evidencia import ResultadoCFO

logger = logging.getLogger(__name__)

_ABSTENCION = (
    "Con los datos disponibles no puedo confirmar esa cifra con evidencia. "
    "Prefiero no darte un número que no pueda respaldar."
)


async def _audit_soft(evento, metadata: dict, actor_id: str) -> None:
    try:
        await emit_audit(evento, entidad="cfo", actor_id=actor_id, metadata=metadata)
    except Exception:  # noqa: BLE001 — lectura: no bloquear la respuesta
        logger.exception("fallo al auditar %s", evento)


def _cifras(resultados: list[ResultadoCFO]) -> list[CifraPublicada]:
    return [
        CifraPublicada(valor=str(r.valor), unidad=r.unidad, evidencia=r.evidencia)
        for r in resultados
        if r.disponible and r.valor is not None
    ]


def _abstencion(motivo: str, res: ResultadoLoop | None, actor_id: str) -> RespuestaCFO:
    uso = UsoLLM(
        modelo=config.cfo_model(),
        tokens_in=res.tokens_in if res else 0,
        tokens_out=res.tokens_out if res else 0,
        iteraciones=res.iteraciones if res else 0,
    )
    return RespuestaCFO(texto=_ABSTENCION, abstuvo=True, motivo=motivo,
                        conceptos_usados=[], cifras=[], uso=uso)


async def consultar(
    pregunta: str, *, actor_id: str, cliente: ClienteLLM | None = None
) -> RespuestaCFO:
    await _audit_soft(AuditEvento.cfo_consulta, {"pregunta": pregunta, "canal": "api"}, actor_id)

    if cliente is None:
        cliente = crear_cliente()
    if cliente is None:
        r = _abstencion("sin_api_key", None, actor_id)
        await _audit_soft(AuditEvento.cfo_respuesta, _meta(r), actor_id)
        return r

    try:
        res = await conversar(cliente, [{"role": "user", "content": pregunta}],
                              max_iter=config.cfo_max_iter())
    except Exception:  # noqa: BLE001 — fallo del LLM
        logger.exception("fallo del LLM en FABS")
        r = _abstencion("error_llm", None, actor_id)
        await _audit_soft(AuditEvento.cfo_respuesta, _meta(r), actor_id)
        return r

    if res.texto is None:
        r = _abstencion("tope_iter", res, actor_id)
        await _audit_soft(AuditEvento.cfo_respuesta, _meta(r), actor_id)
        return r

    veredicto = verificar(res.texto, res.resultados)
    if not veredicto.ok:
        # UN reintento correctivo con los valores válidos
        valores = "; ".join(
            f"{r.concepto}={r.valor} {r.unidad}"
            for r in res.resultados if r.disponible and r.valor is not None
        ) or "(ninguno disponible)"
        correccion = CORRECTIVO.format(
            cifras=", ".join(veredicto.cifras_sin_evidencia), valores=valores
        )
        mensajes = [
            {"role": "user", "content": pregunta},
            {"role": "assistant", "content": res.texto},
            {"role": "user", "content": correccion},
        ]
        try:
            res2 = await conversar(cliente, mensajes, max_iter=config.cfo_max_iter())
        except Exception:  # noqa: BLE001
            logger.exception("fallo del LLM en reintento FABS")
            r = _abstencion("error_llm", res, actor_id)
            await _audit_soft(AuditEvento.cfo_respuesta, _meta(r), actor_id)
            return r
        # acumular resultados de ambas conversaciones para las cifras/evidencia
        res.resultados.extend(res2.resultados)
        if res2.texto is None or not verificar(res2.texto, res.resultados).ok:
            r = _abstencion("verificacion", res, actor_id)
            await _audit_soft(AuditEvento.cfo_respuesta, _meta(r), actor_id)
            return r
        texto_final = res2.texto
        tin, tout, iters = res.tokens_in + res2.tokens_in, res.tokens_out + res2.tokens_out, res.iteraciones + res2.iteraciones
    else:
        texto_final = res.texto
        tin, tout, iters = res.tokens_in, res.tokens_out, res.iteraciones

    r = RespuestaCFO(
        texto=texto_final,
        abstuvo=False,
        motivo=None,
        conceptos_usados=[x.concepto for x in res.resultados],
        cifras=_cifras(res.resultados),
        uso=UsoLLM(modelo=config.cfo_model(), tokens_in=tin, tokens_out=tout, iteraciones=iters),
    )
    await _audit_soft(AuditEvento.cfo_respuesta, _meta(r), actor_id)
    return r


def _meta(r: RespuestaCFO) -> dict:
    return {
        "abstuvo": r.abstuvo,
        "motivo": r.motivo,
        "conceptos_usados": r.conceptos_usados,
        "cifras": [{"valor": c.valor, "unidad": c.unidad,
                    "evidencia": c.evidencia.model_dump()} for c in r.cifras],
        "uso": r.uso.model_dump(),
    }
```

- [ ] **Step 4: Run test** → PASS. (Nota: el `_meta` se referencia antes de definirse a nivel de módulo; en Python está bien porque se resuelve en tiempo de llamada, no de definición.)

- [ ] **Step 5: Commit**

```bash
cd backend && ruff check --fix app/cfo/agente/servicio.py tests/cfo/agente/test_servicio.py
git add app/cfo/agente/servicio.py tests/cfo/agente/test_servicio.py
git commit -m "feat(cfo): servicio orquestador (verify/retry/abstencion + auditoria)"
```

---

### Task 11: Endpoint `POST /api/v1/cfo` + capacidad RBAC (doble barrera)

**Files:**
- Create: `backend/app/cfo/router.py`
- Modify: `backend/app/auth/permissions.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/cfo/agente/test_router.py`

**Interfaces:**
- Consumes: `servicio.consultar`, `require_permission` (auth.deps), `cfo_enabled` (cfo.config), `get_current_user` (para `user.id`).
- Produces: capacidad `"cfo:consultar"` en `PERMISSIONS` (roles `financiero, directivo, admin`). Router `cfo` montado en `main.py` SOLO si `cfo_enabled()`. `POST /api/v1/cfo` body `{pregunta: str}` → `RespuestaCFO`.

- [ ] **Step 1: Añadir la capacidad + su test**

En `backend/app/auth/permissions.py`, dentro de `PERMISSIONS` (tras `capacidad_pago:ver` o al final del bloque §4.1):

```python
    # ── CR-CFO-1 (FABS inc2): consultar al agente CFO. Mismo público que
    # capacidad_pago:ver (ve cifras de plata). El endpoint está además tras el flag.
    "cfo:consultar": frozenset({Role.financiero, Role.directivo, Role.admin}),
```

Test (donde se prueben permisos, p. ej. `tests/test_permissions.py`):
```python
def test_cfo_consultar_para_financiero_directivo_admin():
    from app.auth.permissions import has_permission
    from app.auth.roles import Role
    for rol in (Role.financiero, Role.directivo, Role.admin):
        assert has_permission(rol, "cfo:consultar")
```
(Si hay un test que fija el número total de capacidades, actualizarlo +1.)

- [ ] **Step 2: Run test** → FAIL (capacidad inexistente).

- [ ] **Step 3a: Router**

```python
# backend/app/cfo/router.py
"""FABS · endpoint POST /api/v1/cfo (incremento 2). Doble barrera: (1) solo se monta
en main si CFO_ENABLED; (2) guard 404 defensivo si se alcanza con el flag apagado.
RBAC: require_permission('cfo:consultar')."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from app.auth.deps import require_permission
from app.auth.models import User
from app.cfo.agente import servicio
from app.cfo.agente.modelos import RespuestaCFO
from app.cfo.config import cfo_enabled

router = APIRouter(prefix="/api/v1/cfo", tags=["cfo"])


class ConsultaBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    pregunta: str


@router.post("", response_model=RespuestaCFO)
async def consultar(
    body: ConsultaBody,
    user: User = Depends(require_permission("cfo:consultar")),
) -> RespuestaCFO:
    if not cfo_enabled():  # guard defensivo (barrera 2)
        raise HTTPException(404, "No encontrado.")
    return await servicio.consultar(body.pregunta, actor_id=str(user.id))
```

- [ ] **Step 3b: Registro condicional en main**

En `backend/app/main.py`, donde se incluyen routers, añadir (import arriba, registro condicional):
```python
    # FABS (agente CFO) — solo con el flag encendido (doble barrera; apagado ⇒ ausente)
    from app.cfo.config import cfo_enabled
    if cfo_enabled():
        from app.cfo.router import router as cfo_router
        app.include_router(cfo_router)
```
(Ubicarlo junto a los demás `app.include_router(...)`. Buscar el patrón exacto con `grep -n "include_router" app/main.py` y seguirlo.)

- [ ] **Step 3c: Test del router (flag on/off) con cliente falso**

```python
# backend/tests/cfo/agente/test_router.py
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.cfo.agente.modelos import RespuestaCFO, UsoLLM


@pytest.mark.asyncio
async def test_endpoint_responde_con_flag_on(monkeypatch):
    monkeypatch.setenv("CFO_ENABLED", "true")
    # servicio mockeado (no LLM real) + auth mockeada
    async def fake_consultar(pregunta, *, actor_id):
        return RespuestaCFO(texto="ok", abstuvo=False,
                            uso=UsoLLM(modelo="m", tokens_in=1, tokens_out=1, iteraciones=1))
    import app.cfo.router as r
    monkeypatch.setattr(r.servicio, "consultar", fake_consultar)

    app = FastAPI()
    # override de la dependencia de permiso para el test
    from app.auth.deps import require_permission

    class _U:  # user con id
        id = "u1"
    app.dependency_overrides[require_permission("cfo:consultar")] = lambda: _U()
    # OJO: require_permission devuelve una función nueva cada llamada; en su lugar
    # sobre-escribir get_current_user y permisos. Ver nota abajo.
    app.include_router(r.router)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as ac:
        resp = await ac.post("/api/v1/cfo", json={"pregunta": "¿caja?"})
    assert resp.status_code == 200
    assert resp.json()["texto"] == "ok"
```

Nota de implementación para el override de auth: `require_permission("cfo:consultar")` crea una dependencia nueva en cada llamada, así que `dependency_overrides` por identidad no aplica. Seguir el patrón que ya usan los tests de routers del repo (buscar `dependency_overrides` en `tests/` y `app.dependency_overrides[get_current_user] = ...`). Implementar el override igual que el router de facturas/obligaciones para inyectar un `User` con rol autorizado. Si el patrón del repo usa un `app` de fixture (app real), reusarlo con `CFO_ENABLED=true` y un token de rol admin.

- [ ] **Step 4: Run test** → PASS (endpoint responde; con flag off el router no se monta / guard 404).

- [ ] **Step 5: Commit**

```bash
cd backend && ruff check --fix app/cfo/router.py app/auth/permissions.py app/main.py tests/cfo/agente/test_router.py
git add app/cfo/router.py app/auth/permissions.py app/main.py tests/cfo/agente/test_router.py tests/test_permissions.py
git commit -m "feat(cfo): endpoint POST /api/v1/cfo con doble barrera + capacidad cfo:consultar"
```

---

### Task 12: Cierre — flag-off = COMPAS idéntico + suite + S1 + ruff

**Files:**
- Test: `backend/tests/cfo/test_s1_aislamiento.py` (verificar que sigue no-vacío y verde con `agente/`)
- Verificación de regresión (sin cambios de código salvo fixes que surjan)

**Interfaces:** ninguno nuevo. Tarea de verificación/regresión.

- [ ] **Step 1: S1 cubre el nuevo paquete**

Confirmar que el guard S1 escanea `app/cfo/agente/**` (además de `calc`/`goldens`). Si el test lista subpaquetes explícitos, añadir `agente`. Run:
`cd backend && python -m pytest tests/cfo/test_s1_aislamiento.py -v` → PASS.
Si el nuevo código importara algo prohibido (`app.domain.*`, driver Mongo), el test debe fallar; corregir el import, no el test.

- [ ] **Step 2: Flag-off = COMPAS idéntico**

Con `CFO_ENABLED` ausente/false, verificar que el router `cfo` NO está montado:
```python
# añadir a tests/cfo/agente/test_router.py
@pytest.mark.asyncio
async def test_flag_off_no_monta_router(monkeypatch):
    monkeypatch.delenv("CFO_ENABLED", raising=False)
    from app.main import crear_app  # o el factory real del repo
    app = crear_app()
    rutas = {r.path for r in app.routes}
    assert "/api/v1/cfo" not in rutas
```
(Ajustar al nombre real del factory de la app — `grep -n "def crear_app\|app = FastAPI" app/main.py`.)

- [ ] **Step 3: Suite completa + motor intocable + ruff**

```bash
cd backend && git diff --stat origin/main -- app/proyeccion/motor.py   # DEBE estar vacío
cd backend && ruff check app/cfo/
cd backend && python -m pytest -q
```
Expected: `motor.py` sin diffs; ruff limpio; suite **verde** (los ~955 previos + los nuevos de cfo).

- [ ] **Step 4: Regla 1 — cero float en el pipeline nuevo**

```bash
cd backend && grep -rn "float(" app/cfo/agente/ || echo "sin float: OK"
```
Expected: ninguna coerción a `float` sobre montos (solo Decimal/str).

- [ ] **Step 5: Commit (si hubo fixes) + roadmap**

```bash
cd backend && git add -A && git commit -m "test(cfo): cierre inc2 — S1 + flag-off idéntico + regresión verde" || echo "sin cambios"
```
Actualizar `docs/COMPAS_FABS_ROADMAP.md`: registro fechado del cierre de cada pieza y, al terminar, dejar inc2 listo para el gate Kimi (paquete en `planning/phases/fabs-inc2/auditorias/PR1-I/`).

---

## Self-Review (hecho por el autor del plan)

**1. Cobertura del spec:**
- §1.1 must-do periodicidad → Task 1 ✅
- §3.1 tools → Task 5 ✅ · §3.2 verificador → Task 7 ✅ · §3.3 loop → Task 9 · abstención/retry → Task 10 ✅
- §3.4 RespuestaCFO → Task 4 ✅ · prompt → Task 6 ✅ · cliente/dep → Task 8 ✅
- §4 CR eventos → Task 3 ✅ · §6 config → Task 2 ✅ · endpoint+RBAC → Task 11 ✅
- §8 DoD (flag-off idéntico, S1, Decimal, ruff, verificador adversarial) → Task 12 + baterías ✅

**2. Placeholders:** los tests traen código real; el único punto con "seguir el patrón del repo" es el override de auth en Task 11 (por ser específico del harness de tests del repo) — documentado, no un placeholder de lógica.

**3. Consistencia de tipos:** `ResultadoCFO`/`Evidencia` (inc1), `RespuestaLLM`/`BloqueTexto`/`BloqueToolUse` (Task 8) consumidos consistentemente en loop (9) y servicio (10); `ejecutar_tool`/`resultado_a_dict`/`TOOLS_SCHEMA` (5) usados en loop (9); `verificar`/`Veredicto` (7) en servicio (10); `RespuestaCFO`/`CifraPublicada`/`UsoLLM` (4) en servicio (10) y router (11).

---
*Plan del inc2. Ejecutar por SDD (subagente fresco por tarea + review de dos etapas). Ante conflicto de alcance mandan `COMPAS_NORTE.md`, `CLAUDE.md`, el roadmap de FABS y el spec `2026-08-11-fabs-inc2-loop-agente-design.md`.*
