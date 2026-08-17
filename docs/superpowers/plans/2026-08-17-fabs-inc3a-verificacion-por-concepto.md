# FABS inc3 Pieza A — Verificación por concepto (citación estructurada) · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cerrar el hueco caja/IVA de inc2 quitándole al modelo la posibilidad de escribir números: cita conceptos con `[[token]]`, el servicio sustituye el valor concept-bound, el verificador prohíbe cifras crudas.

**Architecture:** El modelo ya no ve el `valor` (solo `{concepto, disponible, unidad, evidencia}`). Narra con tokens `[[caja_hoy]]`/`[[runway]]`/`[[iva_cuatrimestre]]`. El verificador rechaza CUALQUIER cifra cruda y valida que cada token sea un concepto disponible ESTE turno. El servicio, tras verificar, sustituye cada token por su valor formateado (con contexto interpretativo server-bound: runway=duración, IVA=vencimiento+días). Orden crítico: **verificar → sustituir** (el texto final con valores NO se re-verifica).

**Tech Stack:** Python 3.12, FastAPI, Pydantic strict, `decimal.Decimal`, pytest, `ClienteFake` (sin API real).

**Spec:** `docs/superpowers/specs/2026-08-17-fabs-inc3a-verificacion-por-concepto-design.md`

## Global Constraints

- **Dinero = Decimal, nunca float.** Formateo es-CO con `decimal`/`int`, cero `float`. (regla 1)
- **El modelo NUNCA ve el `valor`** — `resultado_a_dict` omite `valor` y `detalle`.
- **Orden verificar→sustituir:** `verificar()` corre sobre el texto del modelo (con tokens) ANTES de sustituir; el texto final (con valores) NUNCA se re-verifica (se auto-cazaría).
- **Frescura por turno:** un token `[[X]]` es válido solo si `X` es un `concepto` con `disponible=True` y `valor is not None` en los `ResultadoCFO` de ESTE turno.
- **Tope de reintento (D-3):** exactamente 1 reintento correctivo; reincidencia ⇒ abstención `motivo="verificacion"`, jamás loop.
- **D-1:** las sustituciones cargan el contexto interpretativo server-bound (runway=duración; IVA=`vence el {fecha}, en {N} días`). NO se juzga magnitud contra umbral (no-alcance declarado).
- **Flag `CFO_ENABLED` apagado** ⇒ COMPAS byte-idéntico. `motor.py` cero diffs. `app/cfo/calc/*` sin cambios. S1 intacto. `ruff` limpio.
- **Branch guard (contención):** verificar `git branch --show-current` == `feat/fabs-inc3a-concepto` antes de cada commit; si no, STOP + BLOCKED (una sesión paralela ha cambiado de rama antes).
- Rama base: `main` (`61ded9c`+). Todo con `ClienteFake` ⇒ CI verde sin `ANTHROPIC_API_KEY`.

**Nombres de concepto (de `ResultadoCFO.concepto`, distintos de los nombres de tool):** `caja_hoy`, `runway`, `iva_cuatrimestre`. Los tokens usan ESTOS nombres.

---

### Task 1: `conceptos.py` — registro, formateo server-bound y sustitución

**Files:**
- Create: `backend/app/cfo/agente/conceptos.py`
- Test: `backend/tests/cfo/agente/test_conceptos.py`

**Interfaces:**
- Produces:
  - `CONCEPTOS_CITABLES: frozenset[str]` = {`caja_hoy`, `runway`, `iva_cuatrimestre`}.
  - `def formatear(r: ResultadoCFO, hoy: date | None = None) -> str` — valor concept-bound + contexto.
  - `def sustituir_tokens(texto: str, resultados: list[ResultadoCFO], hoy: date | None = None) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/cfo/agente/test_conceptos.py
from datetime import date
from decimal import Decimal

from app.cfo.agente.conceptos import CONCEPTOS_CITABLES, formatear, sustituir_tokens
from app.cfo.calc.evidencia import Evidencia, ResultadoCFO


def _r(concepto, valor, unidad, fecha):
    return ResultadoCFO(
        concepto=concepto, valor=valor, unidad=unidad, disponible=True,
        evidencia=Evidencia(fuente="f", fecha_corte=fecha, ref="x"),
    )


def test_citables():
    assert CONCEPTOS_CITABLES == frozenset({"caja_hoy", "runway", "iva_cuatrimestre"})


def test_formatear_caja_money_es_co_con_fecha():
    r = _r("caja_hoy", Decimal("704722003.00"), "COP", "2026-08-11")
    assert formatear(r) == "$704.722.003 (al 2026-08-11)"


def test_formatear_runway_meses_coma():
    r = _r("runway", Decimal("4.20"), "meses", None)
    assert formatear(r) == "4,2 meses"


def test_formatear_iva_vencimiento_y_dias():
    r = _r("iva_cuatrimestre", Decimal("36204698.10"), "COP", "2026-09-10")
    # hoy fijo para que 'en N días' sea determinista
    assert formatear(r, hoy=date(2026, 8, 17)) == "$36.204.698 (vence el 2026-09-10, en 24 días)"


def test_sustituir_multiple():
    caja = _r("caja_hoy", Decimal("704722003.00"), "COP", "2026-08-11")
    iva = _r("iva_cuatrimestre", Decimal("36204698.10"), "COP", "2026-09-10")
    texto = "Tu caja es [[caja_hoy]] y el IVA es [[iva_cuatrimestre]]."
    out = sustituir_tokens(texto, [caja, iva], hoy=date(2026, 8, 17))
    assert out == ("Tu caja es $704.722.003 (al 2026-08-11) y el IVA es "
                   "$36.204.698 (vence el 2026-09-10, en 24 días).")


def test_sustituir_token_desconocido_se_deja_igual():
    # defensivo: verificar ya garantiza validez; un token sin resultado se deja tal cual
    assert sustituir_tokens("x [[ventas]] y", []) == "x [[ventas]] y"
```

- [ ] **Step 2: Run test to verify it fails** — `cd backend && python -m pytest tests/cfo/agente/test_conceptos.py -v` → FAIL (módulo inexistente).

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/cfo/agente/conceptos.py
"""FABS · conceptos citables + formateo server-bound + sustitución de tokens.

El modelo cita conceptos con `[[concepto]]` (sin ver valores); tras verificar, el
servicio sustituye cada token por el valor concept-bound, ya formateado es-CO y con
el contexto interpretativo que COMPAS computa (runway=duración; IVA=vencimiento+días,
D-1 del gate de diseño). Money=Decimal, formateo con `decimal`/`int`, cero float."""

import re
from datetime import date
from decimal import Decimal

from app.cfo.calc.evidencia import ResultadoCFO
from app.core.time import today_bogota

CONCEPTOS_CITABLES: frozenset[str] = frozenset({"caja_hoy", "runway", "iva_cuatrimestre"})

_RE_TOKEN = re.compile(r"\[\[(\w+)\]\]")


def _money_es(d: Decimal) -> str:
    # COP para display: parte entera con separador de miles es-CO ('.'), sin centavos.
    entero = int(d)
    return "$" + f"{entero:,}".replace(",", ".")


def _meses_es(d: Decimal) -> str:
    return f"{d:.1f}".replace(".", ",") + " meses"


def formatear(r: ResultadoCFO, hoy: date | None = None) -> str:
    """Valor concept-bound listo para prosa, con su contexto server-bound."""
    if r.concepto == "runway":
        return _meses_es(r.valor)
    base = _money_es(r.valor)
    fecha = r.evidencia.fecha_corte
    if r.concepto == "iva_cuatrimestre":
        if fecha:
            dias = (date.fromisoformat(fecha) - (hoy or today_bogota())).days
            return f"{base} (vence el {fecha}, en {dias} días)"
        return base
    # caja_hoy (y cualquier otro COP con fecha de corte)
    return f"{base} (al {fecha})" if fecha else base


def sustituir_tokens(
    texto: str, resultados: list[ResultadoCFO], hoy: date | None = None
) -> str:
    por_concepto = {
        r.concepto: r for r in resultados if r.disponible and r.valor is not None
    }

    def _repl(m: re.Match) -> str:
        r = por_concepto.get(m.group(1))
        return formatear(r, hoy) if r is not None else m.group(0)

    return _RE_TOKEN.sub(_repl, texto)
```

- [ ] **Step 4: Run test** → PASS. Also `cd backend && python -m ruff check --fix app/cfo/agente/conceptos.py tests/cfo/agente/test_conceptos.py` + `python -m ruff format` (ruff no está en PATH; usar `python -m ruff`).

- [ ] **Step 5: Commit**

```bash
cd backend && git add app/cfo/agente/conceptos.py tests/cfo/agente/test_conceptos.py
git commit -m "feat(cfo): conceptos.py — formateo server-bound + sustitucion de tokens"
```

---

### Task 2: `tools.py` — el modelo deja de ver `valor` y `detalle`

**Files:**
- Modify: `backend/app/cfo/agente/tools.py` (`resultado_a_dict`)
- Test: `backend/tests/cfo/agente/test_tools.py`

**Interfaces:**
- Produces: `resultado_a_dict(r)` ahora devuelve `{concepto, disponible, unidad, evidencia{fuente,fecha_corte,ref}}` — **sin `valor` ni `detalle`**. (El `ResultadoCFO` completo, con `valor`, sigue viajando por el loop para que el servicio lo use al sustituir; solo cambia lo que se SERIALIZA hacia el modelo.)

- [ ] **Step 1: Write the failing test** (reemplaza los tests de `valor` existentes — el `valor` ya no se expone por diseño)

```python
# en backend/tests/cfo/agente/test_tools.py — REEMPLAZAR test_resultado_a_dict_serializa_valor_a_string
# y test_resultado_a_dict_cero_legitimo_es_cero_no_none (el valor ya no se expone) por:
def test_resultado_a_dict_no_expone_valor_ni_detalle():
    d = tools.resultado_a_dict(_res(Decimal("704722003")))
    assert "valor" not in d
    assert "detalle" not in d
    assert d["concepto"] == "caja_hoy"
    assert d["disponible"] is True
    assert d["unidad"] == "COP"
    assert d["evidencia"] == {"fuente": "f", "fecha_corte": "2026-08-11", "ref": "2026-08"}
```
(Reusar el helper `_res` existente del archivo; ajustar sus campos de evidencia a los que ya usa.)

- [ ] **Step 2: Run test** → FAIL (hoy `valor` está presente).

- [ ] **Step 3: Write minimal implementation** — en `tools.py`, `resultado_a_dict`:

```python
def resultado_a_dict(r: ResultadoCFO) -> dict:
    # El modelo NO ve valores: cita conceptos con [[token]] y el servicio sustituye el
    # valor concept-bound tras verificar (inc3 Pieza A). Sin `valor` no puede fabricar,
    # mal-etiquetar ni calcular.
    return {
        "concepto": r.concepto,
        "disponible": r.disponible,
        "unidad": r.unidad,
        "evidencia": {
            "fuente": r.evidencia.fuente,
            "fecha_corte": r.evidencia.fecha_corte,
            "ref": r.evidencia.ref,
        },
    }
```

- [ ] **Step 4: Run tests** → `cd backend && python -m pytest tests/cfo/agente/test_tools.py -v` → PASS. Ruff limpio.

- [ ] **Step 5: Commit**

```bash
cd backend && git add app/cfo/agente/tools.py tests/cfo/agente/test_tools.py
git commit -m "feat(cfo): el modelo deja de ver el valor (resultado_a_dict solo concepto+evidencia)"
```

---

### Task 3: `verificador.py` — nuevo contrato (cifras crudas prohibidas + tokens válidos)

**Files:**
- Modify: `backend/app/cfo/agente/verificador.py` (`Veredicto`, `verificar`; añadir `_RE_TOKEN`)
- Test: `backend/tests/cfo/agente/test_verificador.py` (reescribir para el nuevo contrato)

**Interfaces:**
- Consumes: `extraer_cifras` (sin cambios; sigue detectando lo crudo).
- Produces: `Veredicto{ok: bool, cifras_sin_evidencia: list[str], tokens_invalidos: list[str]}` y `verificar(texto, resultados) -> Veredicto` con el contrato nuevo: `ok = (no hay cifras crudas) and (no hay tokens inválidos)`. Un token `[[X]]` es válido sii `X` es `concepto` con `disponible=True` y `valor is not None` en `resultados`.

- [ ] **Step 1: Write the failing test** (el archivo de tests se reescribe para el nuevo contrato — el viejo probaba cifra→valor por tolerancia, que ya no aplica)

```python
# backend/tests/cfo/agente/test_verificador.py — nuevo contrato
from decimal import Decimal

from app.cfo.agente.verificador import verificar
from app.cfo.calc.evidencia import Evidencia, ResultadoCFO


def _r(concepto, valor, unidad, disp=True):
    return ResultadoCFO(concepto=concepto, valor=valor, unidad=unidad, disponible=disp,
                        evidencia=Evidencia(fuente="f", fecha_corte="2026-08-11", ref="x"))


def _caja(): return _r("caja_hoy", Decimal("704722003.00"), "COP")
def _iva(): return _r("iva_cuatrimestre", Decimal("36204698.10"), "COP")


def test_tokens_validos_pasan():
    v = verificar("Tu caja es [[caja_hoy]] y el IVA es [[iva_cuatrimestre]].", [_caja(), _iva()])
    assert v.ok is True
    assert v.cifras_sin_evidencia == [] and v.tokens_invalidos == []


def test_cifra_cruda_se_rechaza():
    # el modelo escribió un número en vez de un token
    v = verificar("Tu caja es $704.722.003.", [_caja()])
    assert v.ok is False
    assert any("704.722.003" in c for c in v.cifras_sin_evidencia)


def test_el_caso_vinculante_caja_con_valor_de_iva_se_rechaza():
    # el modelo escribe crudo el valor del IVA bajo etiqueta 'caja' → cifra cruda → rechazo
    v = verificar("Tu caja es $36.204.698.", [_caja(), _iva()])
    assert v.ok is False  # ya no puede pasar por 'está en el pool COP'


def test_token_de_concepto_inexistente_se_rechaza():
    v = verificar("Las ventas fueron [[ventas]].", [_caja()])
    assert v.ok is False
    assert "[[ventas]]" in v.tokens_invalidos


def test_token_de_concepto_no_disponible_se_rechaza():
    v = verificar("El runway es [[runway]].", [_caja(), _r("runway", None, "meses", disp=False)])
    assert v.ok is False
    assert "[[runway]]" in v.tokens_invalidos


def test_porcentaje_crudo_se_rechaza():
    v = verificar("El IVA es el 25% de tus ingresos.", [_caja()])
    assert v.ok is False


def test_respuesta_sin_cifras_ni_tokens_pasa():
    v = verificar("Con los datos disponibles no puedo confirmar eso.", [])
    assert v.ok is True
```

- [ ] **Step 2: Run test** → FAIL (contrato viejo: `test_tokens_validos_pasan` falla porque hoy `verificar` no conoce tokens; `Veredicto` no tiene `tokens_invalidos`).

- [ ] **Step 3: Write minimal implementation** — en `verificador.py`:

Añadir tras `_RE_PORCENTAJE`:
```python
# Cita de concepto: [[caja_hoy]] / [[runway]] / [[iva_cuatrimestre]]. El modelo cita,
# no escribe números (inc3 Pieza A).
_RE_TOKEN = re.compile(r"\[\[(\w+)\]\]")
```
Cambiar `Veredicto`:
```python
@dataclass(frozen=True)
class Veredicto:
    ok: bool
    cifras_sin_evidencia: list[str]
    tokens_invalidos: list[str]
```
Reemplazar el cuerpo de `verificar` (conservar el docstring, actualizándolo al nuevo contrato):
```python
def verificar(texto: str, resultados: list[ResultadoCFO]) -> Veredicto:
    """Contrato inc3 Pieza A (citación estructurada): el modelo NO escribe cifras,
    cita conceptos con `[[concepto]]`. Veredicto ok sii (1) NO hay ninguna cifra
    cruda (COP/meses/%) en el texto — cualquier número es violación, el modelo debió
    usar un token — y (2) todo token `[[X]]` referencia un concepto con evidencia
    disponible ESTE turno (frescura por turno). Esto cierra el hueco cifra→concepto
    de inc2 por construcción: el modelo no puede mal-etiquetar un valor porque no
    escribe valores. El servicio sustituye los tokens por el valor concept-bound
    DESPUÉS de este veredicto (el texto sustituido nunca se re-verifica)."""
    crudas = [token for _, _, token in extraer_cifras(texto)]
    disponibles = {
        r.concepto for r in resultados if r.disponible and r.valor is not None
    }
    tokens_invalidos = [
        m.group(0) for m in _RE_TOKEN.finditer(texto) if m.group(1) not in disponibles
    ]
    ok = not crudas and not tokens_invalidos
    return Veredicto(
        ok=ok, cifras_sin_evidencia=crudas, tokens_invalidos=tokens_invalidos
    )
```
`extraer_cifras`/`_es_monto`/`_a_decimal_*`/`_RE_*` de detección: **sin cambios**.

- [ ] **Step 4: Run test** → `cd backend && python -m pytest tests/cfo/agente/test_verificador.py -v` → PASS. Ruff limpio.

- [ ] **Step 5: Commit**

```bash
cd backend && git add app/cfo/agente/verificador.py tests/cfo/agente/test_verificador.py
git commit -m "feat(cfo): verificador — cifras crudas prohibidas + tokens de concepto validos"
```

---

### Task 4: `prompt.py` — el modelo cita con tokens, nunca escribe números

**Files:**
- Modify: `backend/app/cfo/agente/prompt.py` (`SYSTEM_PROMPT`, `CORRECTIVO`)
- Test: `backend/tests/cfo/agente/test_prompt.py`

**Interfaces:**
- Produces: `SYSTEM_PROMPT` con la regla de citación por token; `CORRECTIVO` formateable con `.format(cifras=..., tokens=..., disponibles=...)`.

- [ ] **Step 1: Write the failing test**

```python
# en backend/tests/cfo/agente/test_prompt.py — añadir/ajustar
from app.cfo.agente.prompt import CORRECTIVO, SYSTEM_PROMPT


def test_prompt_exige_tokens_de_concepto():
    p = SYSTEM_PROMPT
    assert "[[caja_hoy]]" in p and "[[runway]]" in p and "[[iva_cuatrimestre]]" in p
    assert "nunca escrib" in p.lower() or "no escrib" in p.lower()  # no escribir números


def test_correctivo_formateable_con_tokens():
    out = CORRECTIVO.format(cifras="$999", tokens="[[ventas]]", disponibles="[[caja_hoy]]")
    assert "$999" in out and "[[ventas]]" in out and "[[caja_hoy]]" in out
```

- [ ] **Step 2: Run test** → FAIL.

- [ ] **Step 3: Write minimal implementation** — en `prompt.py`, ajustar `SYSTEM_PROMPT` (regla 1 + regla nueva de tokens) y `CORRECTIVO`:

```python
SYSTEM_PROMPT = (
    "Eres FABS, el analista financiero de IA de RODDOS S.A.S. Complementas al CFO "
    "humano; no lo reemplazas. Respondes en español, claro y conciso.\n\n"
    "REGLAS INQUEBRANTABLES:\n"
    "1. NUNCA escribas cifras (montos, meses, porcentajes) directamente, ni las "
    "calcules, sumes, estimes o extrapoles. Para mencionar un número, usa su TOKEN "
    "DE CONCEPTO entre dobles corchetes: [[caja_hoy]], [[runway]], "
    "[[iva_cuatrimestre]]. El sistema los reemplaza por el valor real con su fecha "
    "de corte. Tú nunca ves ni escribes el número.\n"
    "2. Solo cita un concepto si su herramienta lo devolvió como disponible en ESTE "
    "turno. Si un concepto no está disponible, dilo con honestidad y NO lo cites.\n"
    "3. Si una herramienta responde disponible=false, abstente honestamente ('con los "
    "datos disponibles no puedo confirmar X'). Jamás un dato falso.\n"
    "4. Si la pregunta requiere algo para lo que no tienes herramienta, dilo con "
    "claridad; no improvises.\n"
    "5. No mueves dinero ni ejecutas operaciones: solo informas.\n\n"
    "Herramientas disponibles: caja disponible hoy ([[caja_hoy]]), runway/meses de "
    "caja ([[runway]]), IVA del cuatrimestre ([[iva_cuatrimestre]]). Llámalas y cita "
    "el token del concepto; nunca escribas el número."
)

CORRECTIVO = (
    "Tu respuesta anterior escribió cifras crudas ({cifras}) o citó conceptos no "
    "disponibles ({tokens}). NO escribas números. Usa ÚNICAMENTE estos tokens de "
    "concepto disponibles: {disponibles}. El sistema los reemplaza por el valor real. "
    "Si un dato no está disponible, dilo sin cifra."
)
```
(OJO: revisar que no queden caracteres no-ASCII accidentales — usar "ESTE", no "ESटE".)

- [ ] **Step 4: Run test** → PASS. Ruff limpio.

- [ ] **Step 5: Commit**

```bash
cd backend && git add app/cfo/agente/prompt.py tests/cfo/agente/test_prompt.py
git commit -m "feat(cfo): prompt — el modelo cita con [[token]], nunca escribe numeros"
```

---

### Task 5: `servicio.py` — sustituir tras verificar + correctivo con tokens + tope de reintento

**Files:**
- Modify: `backend/app/cfo/agente/servicio.py`
- Test: `backend/tests/cfo/agente/test_servicio.py`

**Interfaces:**
- Consumes: `conceptos.sustituir_tokens` (Task 1), `Veredicto.tokens_invalidos` (Task 3), `CORRECTIVO` con `{cifras}/{tokens}/{disponibles}` (Task 4).
- Produces: `consultar(...)` sin cambio de firma; el `RespuestaCFO.texto` publicado tiene los **valores concept-bound sustituidos** (ya no tokens). El reintento ahora le da al modelo los TOKENS disponibles (no valores). Tope: 1 reintento, reincidencia ⇒ `motivo="verificacion"`.

- [ ] **Step 1: Write the failing test**

```python
# en backend/tests/cfo/agente/test_servicio.py — añadir (reusar el patrón de ClienteFake + _audit del archivo)
from decimal import Decimal

import pytest

from app.cfo.agente import servicio as srv
from app.cfo.agente.cliente import BloqueTexto, BloqueToolUse, RespuestaLLM
from app.cfo.calc.evidencia import Evidencia, ResultadoCFO
from tests.cfo.agente.fakes import ClienteFake


def _caja():
    return ResultadoCFO(concepto="caja_hoy", valor=Decimal("704722003.00"), unidad="COP",
                        disponible=True,
                        evidencia=Evidencia(fuente="f", fecha_corte="2026-08-11", ref="2026-08"))


@pytest.mark.asyncio
async def test_publica_con_tokens_sustituidos(monkeypatch, _audit):
    async def fake_tool(nombre):
        return _caja()
    monkeypatch.setattr("app.cfo.agente.loop.ejecutar_tool", fake_tool)
    guiones = [
        RespuestaLLM("tool_use", [BloqueToolUse(id="t1", nombre="caja_disponible_hoy", input={})], 1, 1),
        RespuestaLLM("end_turn", [BloqueTexto(texto="Tu caja hoy es [[caja_hoy]].")], 1, 1),
    ]
    r = await srv.consultar("¿caja?", actor_id="u1", cliente=ClienteFake(guiones))
    assert r.abstuvo is False
    assert "[[caja_hoy]]" not in r.texto
    assert "$704.722.003 (al 2026-08-11)" in r.texto


@pytest.mark.asyncio
async def test_reincidencia_en_cifra_cruda_abstiene_un_solo_reintento(monkeypatch, _audit):
    async def fake_tool(nombre):
        return _caja()
    monkeypatch.setattr("app.cfo.agente.loop.ejecutar_tool", fake_tool)
    # 1ª: tool + cifra cruda; reintento: vuelve a escribir cruda → abstención (jamás loop)
    guiones = [
        RespuestaLLM("tool_use", [BloqueToolUse(id="t1", nombre="caja_disponible_hoy", input={})], 1, 1),
        RespuestaLLM("end_turn", [BloqueTexto(texto="Tu caja es $704.722.003.")], 1, 1),
        RespuestaLLM("end_turn", [BloqueTexto(texto="Perdón: $704.722.003.")], 1, 1),
    ]
    fake = ClienteFake(guiones)
    r = await srv.consultar("¿caja?", actor_id="u1", cliente=fake)
    assert r.abstuvo is True and r.motivo == "verificacion"
    assert fake._guiones == []  # consumió exactamente 3 respuestas (1ª conv: tool+texto; reintento: 1 texto), no más
```

- [ ] **Step 2: Run test** → FAIL (hoy no sustituye; `test_publica_con_tokens_sustituidos` deja el token en el texto).

- [ ] **Step 3: Write minimal implementation** — en `servicio.py`:

Añadir import:
```python
from app.cfo.agente.conceptos import sustituir_tokens
```
En el bloque del reintento (donde hoy arma `valores`), reemplazar el cálculo de `valores`+`correccion` por (dar TOKENS disponibles, no valores):
```python
            disponibles = (
                ", ".join(
                    f"[[{r.concepto}]]"
                    for r in res.resultados
                    if r.disponible and r.valor is not None
                )
                or "(ninguno disponible)"
            )
            correccion = CORRECTIVO.format(
                cifras=", ".join(veredicto.cifras_sin_evidencia) or "(ninguna)",
                tokens=", ".join(veredicto.tokens_invalidos) or "(ninguno)",
                disponibles=disponibles,
            )
```
Y justo ANTES de construir `RespuestaCFO` (línea `r = RespuestaCFO(texto=texto_final, ...)`), sustituir los tokens por sus valores:
```python
        texto_final = sustituir_tokens(texto_final, res.resultados)
        r = RespuestaCFO(
            texto=texto_final,
            abstuvo=False,
            ...
        )
```
(El resto del flujo — verificar→retry→verificar, abstenciones, backstop, auditoría — NO cambia. El tope de 1 reintento ya es estructural.)

- [ ] **Step 4: Run tests** → `cd backend && python -m pytest tests/cfo/agente/test_servicio.py -v` → PASS. Ruff limpio.

- [ ] **Step 5: Commit**

```bash
cd backend && git add app/cfo/agente/servicio.py tests/cfo/agente/test_servicio.py
git commit -m "feat(cfo): servicio — sustituye [[token]] tras verificar + correctivo con tokens"
```

---

### Task 6: Cierre — flag-off idéntico + S1 + regresión + no-valor-al-modelo

**Files:**
- Test/verificación (sin cambios de lógica salvo fixes que surjan)

**Interfaces:** ninguno nuevo. Verificación/regresión.

- [ ] **Step 1: El modelo no ve valores (integración)** — confirmar que en el loop, lo que se serializa al modelo no trae `valor`:
`cd backend && python -m pytest tests/cfo/agente/test_loop.py tests/cfo/agente/test_tools.py -v` → verde. Si algún test de loop asumía `valor` en el tool_result, actualizarlo (el modelo ya no lo ve, por diseño).

- [ ] **Step 2: S1 sigue verde con `conceptos.py`** — `cd backend && python -m pytest tests/cfo/test_s1_aislamiento.py -v`. `conceptos.py` importa `app.cfo.calc.evidencia` y `app.core.time` (capa de servicios/core, permitido) — NO `app.domain.*` ni driver Mongo. Debe seguir verde (S1 ya escanea `agente/`).

- [ ] **Step 3: motor.py cero diffs + cero float** —
```bash
cd backend && git diff 61ded9c..HEAD -- app/proyeccion/motor.py   # DEBE estar vacío
cd backend && grep -rn "float(" app/cfo/agente/conceptos.py || echo "sin float: OK"
```

- [ ] **Step 4: Regresión completa + ruff** —
```bash
cd backend && python -m ruff check app/cfo/
cd backend && python -m pytest -q
```
Expected: `motor.py` sin diffs; ruff limpio; suite **verde** (los previos + los de cfo/agente reescritos). Flag apagado ⇒ COMPAS idéntico.

- [ ] **Step 5: Commit (si hubo fixes) + roadmap**
```bash
cd backend && git add -A && git commit -m "test(cfo): cierre inc3-A — S1 + flag-off identico + regresion verde" || echo "sin cambios"
```
Actualizar `docs/COMPAS_FABS_ROADMAP.md` (registro fechado del cierre de Pieza A). El paquete Kimi de código (`planning/phases/fabs/auditorias/INC3A-I/`) lo arma el controlador al terminar el SDD.

---

## Self-Review (autor del plan)

**1. Cobertura del spec:**
- §2/§3.2 (modelo no ve valor) → Task 2 ✅
- §3.1 (`conceptos.py` formateo + D-1 días) → Task 1 ✅
- §3.3 (verificar: cifras crudas + tokens) → Task 3 ✅
- §3.4 (prompt tokens) → Task 4 ✅
- §3.5 (servicio sustituye + correctivo) → Task 5 ✅
- §7 DoD 4 (D-3 tope reintento testeado) → Task 5 `test_reincidencia…` ✅
- §7 DoD 5 (flag-off/motor/float/S1/ruff) → Task 6 ✅

**2. Placeholders:** los tests traen código real; los cambios de código son literales. Sin TBD.

**3. Consistencia de tipos:** `Veredicto{ok, cifras_sin_evidencia, tokens_invalidos}` (Task 3) consumido en servicio (Task 5); `sustituir_tokens`/`formatear`/`CONCEPTOS_CITABLES` (Task 1) en servicio (Task 5); `CORRECTIVO.format(cifras,tokens,disponibles)` (Task 4) en servicio (Task 5); nombres de concepto (`caja_hoy`/`runway`/`iva_cuatrimestre`) consistentes en Task 1/3/5.

---
*Pieza A de inc3. Ejecutar por SDD (subagente fresco por tarea + review de dos etapas + review final). Ante conflicto de alcance mandan `COMPAS_NORTE.md`, `CLAUDE.md`, el roadmap de FABS y el spec de la Pieza A.*
