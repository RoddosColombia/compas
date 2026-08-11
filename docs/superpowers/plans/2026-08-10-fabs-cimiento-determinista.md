# FABS · Incremento 1 — Cimiento determinista · Plan de implementación

> **Para el ejecutor:** SUB-SKILL REQUERIDA: usa superpowers:subagent-driven-development (recomendado) o superpowers:executing-plans para implementar tarea por tarea. Los pasos usan checkbox (`- [ ]`).

**Goal:** Construir el motor de datos de solo lectura de FABS (3 conceptos con evidencia) + el arnés de goldens, dentro de `backend/app/cfo/`, con el motor de COMPAS intocado.

**Architecture:** Módulo interno de COMPAS bajo flag `CFO_ENABLED` (apagado). `cfo/calc/` envuelve funciones públicas de los servicios de COMPAS y devuelve cada cifra con su evidencia; `cfo/goldens/` verifica esos conceptos contra valores esperados. Nada escribe en datos de COMPAS; la única escritura es sembrar `cfo_goldens`.

**Tech Stack:** Python 3.12, FastAPI, Beanie/Motor (MongoDB), Pydantic strict, `decimal.Decimal`. Tests: pytest + mongomock_motor (patrón de la suite existente).

## Global Constraints (verbatim de las reglas + spec)

- Dinero = `decimal.Decimal`; en API/serialización como string; **NUNCA float**. (regla 1)
- Zona horaria América/Bogotá (`now_bogota`/`today_bogota`); fechas `YYYY-MM-DD`. (regla 2)
- Pydantic `strict=True, extra="forbid"` en todo modelo nuevo. (regla 3)
- **`backend/app/proyeccion/motor.py` y demás servicios de COMPAS: CERO diffs** (salvo el refactor DRY explícito de la Task 6, que preserva comportamiento).
- **S1:** `cfo/calc/` y `cfo/goldens/` importan SOLO funciones públicas de `app.<modulo>.service` (y tipos de dominio de lectura); la ÚNICA subruta que toca el driver de Mongo es `cfo/datos/repositorios.py`, y solo sobre colecciones con prefijo `cfo_`.
- Sin eventos de auditoría nuevos en este incremento (el catálogo cerrado no crece).
- Alegra = CERO referencias. CXC socios / devengado = fuera.
- Conventional Commits; commits frecuentes (uno por tarea).
- Verificación final: con `cfo/` presente y flag apagado, la suite de COMPAS pasa idéntica.

---

### Task 1: Tipos de evidencia — `cfo/calc/evidencia.py`

**Files:**
- Create: `backend/app/cfo/__init__.py` (vacío)
- Create: `backend/app/cfo/calc/__init__.py` (vacío)
- Create: `backend/app/cfo/calc/evidencia.py`
- Test: `backend/tests/cfo/test_evidencia.py` (crear `backend/tests/cfo/__init__.py` vacío)

**Interfaces:**
- Produces: `Evidencia(fuente:str, fecha_corte:str|None, ref:str)`; `ResultadoCFO(concepto:str, valor:Money|None, unidad:str, disponible:bool, evidencia:Evidencia, detalle:dict=Field(default_factory=dict))`. `Money = Decimal` (usa `app.core.money.Money`).

- [ ] **Step 1: Escribe el test que falla**

```python
# backend/tests/cfo/test_evidencia.py
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.cfo.calc.evidencia import Evidencia, ResultadoCFO


def test_resultado_ok_con_evidencia():
    r = ResultadoCFO(
        concepto="caja_hoy",
        valor=Decimal("704722003.00"),
        unidad="COP",
        disponible=True,
        evidencia=Evidencia(
            fuente="caja.service.caja_diaria", fecha_corte="2026-08-04", ref="2026-08"
        ),
    )
    assert r.valor == Decimal("704722003.00")
    assert r.evidencia.fecha_corte == "2026-08-04"
    assert r.detalle == {}


def test_abstencion_valor_none_disponible_false():
    r = ResultadoCFO(
        concepto="runway",
        valor=None,
        unidad="meses",
        disponible=False,
        evidencia=Evidencia(fuente="proyeccion", fecha_corte=None, ref="sin-config"),
    )
    assert r.valor is None and r.disponible is False


def test_rechaza_campo_extra_strict():
    with pytest.raises(ValidationError):
        Evidencia(fuente="x", fecha_corte=None, ref="y", inventado=1)
```

- [ ] **Step 2: Corre el test y verifica que falla**

Run: `cd backend && PYTHONUTF8=1 python -m pytest tests/cfo/test_evidencia.py -q`
Expected: FAIL — `ModuleNotFoundError: app.cfo.calc.evidencia`.

- [ ] **Step 3: Implementa el mínimo**

```python
# backend/app/cfo/calc/evidencia.py
"""FABS · contrato de evidencia. Toda cifra que FABS publica viaja envuelta en
ResultadoCFO con su Evidencia (fuente + fecha de corte + ref reproducible). Sin
evidencia no hay cifra; sin dato, `disponible=False` y `valor=None` (abstención)."""

from pydantic import BaseModel, ConfigDict, Field

from app.core.money import Money


class Evidencia(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    fuente: str
    fecha_corte: str | None  # 'YYYY-MM-DD' del dato más reciente (None si no aplica)
    ref: str  # identificador reproducible: mes de control, cuatrimestre, etc.


class ResultadoCFO(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    concepto: str
    valor: Money | None
    unidad: str
    disponible: bool
    evidencia: Evidencia
    detalle: dict = Field(default_factory=dict)
```

Crea también los `__init__.py` vacíos de `app/cfo/`, `app/cfo/calc/` y `tests/cfo/`.

- [ ] **Step 4: Corre el test y verifica que pasa**

Run: `cd backend && PYTHONUTF8=1 python -m pytest tests/cfo/test_evidencia.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/cfo/__init__.py backend/app/cfo/calc/ backend/tests/cfo/
git commit -m "feat(cfo): contrato de evidencia ResultadoCFO/Evidencia (FABS inc1)"
```

---

### Task 2: Flag `CFO_ENABLED` — `cfo/config.py`

**Files:**
- Create: `backend/app/cfo/config.py`
- Test: `backend/tests/cfo/test_config.py`

**Interfaces:**
- Produces: `cfo_enabled() -> bool` (lee `CFO_ENABLED` del entorno; default `False`).

- [ ] **Step 1: Test que falla**

```python
# backend/tests/cfo/test_config.py
from app.cfo.config import cfo_enabled


def test_flag_apagado_por_defecto(monkeypatch):
    monkeypatch.delenv("CFO_ENABLED", raising=False)
    assert cfo_enabled() is False


def test_flag_encendible_por_env(monkeypatch):
    monkeypatch.setenv("CFO_ENABLED", "true")
    assert cfo_enabled() is True
```

- [ ] **Step 2: Corre y verifica que falla**

Run: `cd backend && PYTHONUTF8=1 python -m pytest tests/cfo/test_config.py -q`
Expected: FAIL — módulo inexistente.

- [ ] **Step 3: Implementa**

```python
# backend/app/cfo/config.py
"""FABS · feature flag. Apagado por defecto ⇒ COMPAS byte-idéntico. La doble barrera
(router condicional + guard 404) aterriza con el primer endpoint (incremento 2)."""

import os


def cfo_enabled() -> bool:
    return os.environ.get("CFO_ENABLED", "false").strip().lower() == "true"
```

- [ ] **Step 4: Corre y verifica que pasa**

Run: `cd backend && PYTHONUTF8=1 python -m pytest tests/cfo/test_config.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/cfo/config.py backend/tests/cfo/test_config.py
git commit -m "feat(cfo): flag CFO_ENABLED (apagado por defecto)"
```

---

### Task 3: Concepto `caja_hoy` — `cfo/calc/caja.py`

**Files:**
- Create: `backend/app/cfo/calc/caja.py`
- Test: `backend/tests/cfo/test_calc_caja.py`

**Interfaces:**
- Consumes: `app.caja.service.caja_diaria(*, desde:str, hasta:str, caja_inicial:Decimal) -> dict` (devuelve `{"dias":[{"fecha","caja",...}], ...}` con montos string); `app.parametros_proyeccion.service` para la `caja_inicial` vigente y su `vigente_desde`; `app.core.time.today_bogota`.
- Produces: `async caja_hoy() -> ResultadoCFO` (concepto `"caja_hoy"`, unidad `"COP"`).

**Nota de binding:** ANTES del Step 3, lee `app/parametros_proyeccion/service.py` y anota el nombre exacto del getter de los parámetros vigentes (p. ej. `obtener_vigente()`), del que se toman `caja_inicial` (Decimal) y `vigente_desde` (`YYYY-MM-DD`). Úsalo en la implementación. Si no hay parámetros vigentes → `disponible=False`.

- [ ] **Step 1: Test que falla** (mongomock; patrón de la suite: init_beanie con `DOMAIN_DOCUMENTS`)

```python
# backend/tests/cfo/test_calc_caja.py
from decimal import Decimal

import pytest
import pytest_asyncio
from app.domain import DOMAIN_DOCUMENTS
from app.domain.mes_control import MesControl
from app.domain.parametros_proyeccion import ParametrosProyeccion  # ajustar al real
from app.domain.transaccion import Transaccion
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient


@pytest_asyncio.fixture
async def db(monkeypatch):
    c = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
    # parámetros vigentes con caja_inicial y vigente_desde (ajusta los campos al modelo real)
    await ParametrosProyeccion(
        caja_inicial=Decimal("700000000"), vigente_desde="2026-08-01", motos_base=80
    ).insert()  # rellenar los campos obligatorios que exija el modelo
    yield c


@pytest.mark.asyncio
async def test_caja_hoy_devuelve_ultimo_saldo_con_fecha_corte(db, monkeypatch):
    from app.core import time as tmod
    monkeypatch.setattr(tmod, "today_bogota", lambda: __import__("datetime").date(2026, 8, 4))
    mc = await MesControl.find_one(MesControl.mes == "2026-08-01")
    # dos ingresos reales en agosto
    for i, (f, v) in enumerate([("2026-08-02", "5000000"), ("2026-08-04", "3000000")]):
        await Transaccion(
            fecha=f, descripcion="ingreso", valor=Decimal(v), tipo_flujo="ingreso",
            rubro_id=(mc.id if mc else None) or __import__("bson").ObjectId(),
            mes_id=(mc.id if mc else __import__("bson").ObjectId()),
            banco="global66", id_banco=f"ING{i}|1",
        ).insert()

    from app.cfo.calc.caja import caja_hoy
    r = await caja_hoy()
    assert r.concepto == "caja_hoy" and r.unidad == "COP"
    assert r.disponible is True
    assert r.valor == Decimal("708000000.00")  # 700M + 5M + 3M
    assert r.evidencia.fecha_corte == "2026-08-04"


@pytest.mark.asyncio
async def test_caja_hoy_sin_parametros_abstiene(monkeypatch):
    c = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=c["compas_vacio"], document_models=DOMAIN_DOCUMENTS)
    from app.cfo.calc.caja import caja_hoy
    r = await caja_hoy()
    assert r.disponible is False and r.valor is None
```

*(Nota: ajusta el import y los campos de `ParametrosProyeccion` a los reales antes de correr; el nombre del modelo puede diferir.)*

- [ ] **Step 2: Corre y verifica que falla**

Run: `cd backend && PYTHONUTF8=1 python -m pytest tests/cfo/test_calc_caja.py -q`
Expected: FAIL — `app.cfo.calc.caja` inexistente.

- [ ] **Step 3: Implementa** (bindea el getter real de parámetros)

```python
# backend/app/cfo/calc/caja.py
"""FABS · concepto 'caja disponible hoy'. Lee la serie diaria real de COMPAS
(caja.service.caja_diaria) desde el ancla de caja inicial vigente hasta hoy (Bogotá) y
toma el último saldo, con su fecha de corte. Sin parámetros vigentes → abstención."""

from decimal import Decimal

from app.caja import service as caja_service
from app.cfo.calc.evidencia import Evidencia, ResultadoCFO
from app.core.time import today_bogota
from app.parametros_proyeccion import service as params_service  # ajustar al real


async def caja_hoy() -> ResultadoCFO:
    fuente = "caja.service.caja_diaria"
    vig = await params_service.obtener_vigente()  # ← nombre real del getter
    if vig is None:
        return ResultadoCFO(
            concepto="caja_hoy", valor=None, unidad="COP", disponible=False,
            evidencia=Evidencia(fuente=fuente, fecha_corte=None, ref="sin-parametros"),
        )
    hasta = today_bogota().isoformat()
    data = await caja_service.caja_diaria(
        desde=vig.vigente_desde, hasta=hasta, caja_inicial=Decimal(str(vig.caja_inicial))
    )
    dias = data["dias"]
    if not dias:
        return ResultadoCFO(
            concepto="caja_hoy",
            valor=Decimal(str(vig.caja_inicial)),
            unidad="COP", disponible=True,
            evidencia=Evidencia(fuente=fuente, fecha_corte=vig.vigente_desde, ref="sin-movimientos"),
        )
    ultimo = dias[-1]
    return ResultadoCFO(
        concepto="caja_hoy", valor=Decimal(ultimo["caja"]), unidad="COP", disponible=True,
        evidencia=Evidencia(fuente=fuente, fecha_corte=ultimo["fecha"], ref=hasta[:7]),
        detalle={"desde": vig.vigente_desde, "hasta": hasta},
    )
```

- [ ] **Step 4: Corre y verifica que pasa**

Run: `cd backend && PYTHONUTF8=1 python -m pytest tests/cfo/test_calc_caja.py -q`
Expected: PASS (ajusta bindings hasta verde).

- [ ] **Step 5: Commit**

```bash
git add backend/app/cfo/calc/caja.py backend/tests/cfo/test_calc_caja.py
git commit -m "feat(cfo): concepto caja_hoy con evidencia y fecha de corte"
```

---

### Task 4: Concepto `runway` — `cfo/calc/runway.py`

**Files:**
- Create: `backend/app/cfo/calc/runway.py`
- Test: `backend/tests/cfo/test_calc_runway.py`

**Interfaces:**
- Consumes: `app.proyeccion.service.proyectar_vigente(*, escenario, mes_inicio, horizonte_meses) -> dict` (clave `"runway_meses"`: string|None a nivel raíz); lanza `ProyeccionError` (409) si falta config.
- Produces: `async runway() -> ResultadoCFO` (concepto `"runway"`, unidad `"meses"`).

**Nota de binding:** el `mes_inicio` es `tuple[int,int]` = (año, mes) del mes vigente en Bogotá; `escenario="base"`; `horizonte_meses=None` (usa el default del servicio).

- [ ] **Step 1: Test que falla**

```python
# backend/tests/cfo/test_calc_runway.py
import pytest
from decimal import Decimal


@pytest.mark.asyncio
async def test_runway_sin_config_abstiene(monkeypatch):
    from app.cfo.calc import runway as mod
    async def _boom(**kw):
        from app.proyeccion.service import ProyeccionError
        raise ProyeccionError("no hay parametros", 409)
    monkeypatch.setattr(mod, "_proyectar", _boom)
    r = await mod.runway()
    assert r.disponible is False and r.valor is None and r.unidad == "meses"


@pytest.mark.asyncio
async def test_runway_toma_runway_meses(monkeypatch):
    from app.cfo.calc import runway as mod
    async def _ok(**kw):
        return {"runway_meses": "18.0", "meses": []}
    monkeypatch.setattr(mod, "_proyectar", _ok)
    r = await mod.runway()
    assert r.disponible is True and r.valor == Decimal("18.0")
    assert r.evidencia.fuente.startswith("proyeccion")
```

- [ ] **Step 2: Corre y verifica que falla**

Run: `cd backend && PYTHONUTF8=1 python -m pytest tests/cfo/test_calc_runway.py -q`
Expected: FAIL.

- [ ] **Step 3: Implementa**

```python
# backend/app/cfo/calc/runway.py
"""FABS · concepto 'runway' (meses de caja al ritmo actual). Lee el KPI runway_meses
de la proyección vigente de COMPAS. Sin config (ProyeccionError) → abstención."""

from decimal import Decimal

from app.cfo.calc.evidencia import Evidencia, ResultadoCFO
from app.core.time import now_bogota
from app.proyeccion import service as proy_service
from app.proyeccion.service import ProyeccionError


async def _proyectar(**kw) -> dict:
    return await proy_service.proyectar_vigente(**kw)


async def runway() -> ResultadoCFO:
    fuente = "proyeccion.service.proyectar_vigente"
    ahora = now_bogota()
    ref = f"{ahora.year:04d}-{ahora.month:02d}"
    try:
        data = await _proyectar(
            escenario="base", mes_inicio=(ahora.year, ahora.month), horizonte_meses=None
        )
    except ProyeccionError:
        return ResultadoCFO(
            concepto="runway", valor=None, unidad="meses", disponible=False,
            evidencia=Evidencia(fuente=fuente, fecha_corte=None, ref="sin-config"),
        )
    rm = data.get("runway_meses")
    if rm is None:
        return ResultadoCFO(
            concepto="runway", valor=None, unidad="meses", disponible=False,
            evidencia=Evidencia(fuente=fuente, fecha_corte=None, ref=ref),
            detalle={"nota": "sin quema neta: runway no aplica"},
        )
    return ResultadoCFO(
        concepto="runway", valor=Decimal(rm), unidad="meses", disponible=True,
        evidencia=Evidencia(fuente=fuente, fecha_corte=None, ref=ref),
    )
```

- [ ] **Step 4: Corre y verifica que pasa**

Run: `cd backend && PYTHONUTF8=1 python -m pytest tests/cfo/test_calc_runway.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/cfo/calc/runway.py backend/tests/cfo/test_calc_runway.py
git commit -m "feat(cfo): concepto runway desde la proyeccion vigente"
```

---

### Task 5: Extraer `liquidacion_iva()` a `facturas/service.py` (refactor DRY, comportamiento idéntico)

**Files:**
- Modify: `backend/app/facturas/service.py` (agrega `liquidacion_iva()`)
- Modify: `backend/app/facturas/router.py:140-167` (el endpoint llama al servicio)
- Test: la suite existente de facturas debe seguir verde (no se agrega test nuevo aquí).

**Interfaces:**
- Produces: `async liquidacion_iva() -> dict` con la MISMA forma que hoy devuelve `GET /facturas/liquidacion` (`{"periodicidad":..., "periodos":[{anio, periodo, etiqueta, generado, descontable, saldo, saldo_favor_previo, neto_a_pagar, saldo_favor_nuevo, proximo_pago}]}`).

- [ ] **Step 1: Localiza y confirma** los helpers `_etiqueta_periodo`, `_proximo_pago` y la función pura `liquidar` que usa el router (`backend/app/facturas/router.py`). Anota de qué módulo se importa `liquidar`.

- [ ] **Step 2: Mueve el cuerpo del endpoint a un servicio**

En `facturas/service.py`, agrega (importando `liquidar`, `_etiqueta_periodo`/`clave_dian` y helpers necesarios; mueve `_proximo_pago` y `_etiqueta_periodo` a `service.py` si el router es su único usuario, o impórtalos):

```python
async def liquidacion_iva() -> dict:
    """Liquidación de IVA por período (misma forma que GET /facturas/liquidacion)."""
    periodicidad = await obtener_periodicidad()
    items = await obtener_facturas_iva()
    calendario = await obtener_calendario_dian()
    return {
        "periodicidad": periodicidad.value,
        "periodos": [
            {
                "anio": c.anio,
                "periodo": c.periodo,
                "etiqueta": _etiqueta_periodo(c.anio, c.periodo, periodicidad),
                "generado": money_str(c.generado),
                "descontable": money_str(c.descontable),
                "saldo": money_str(c.saldo),
                "saldo_favor_previo": money_str(c.saldo_favor_previo),
                "neto_a_pagar": money_str(c.neto_a_pagar),
                "saldo_favor_nuevo": money_str(c.saldo_favor_nuevo),
                "proximo_pago": _proximo_pago(c.anio, c.periodo, periodicidad, calendario),
            }
            for c in liquidar(items, periodicidad)
        ],
    }
```

Reescribe el endpoint del router para que sea `return await service.liquidacion_iva()`.

- [ ] **Step 3: Corre la suite de facturas y verifica que sigue verde**

Run: `cd backend && PYTHONUTF8=1 python -m pytest tests/ -k "factura or iva" -q`
Expected: PASS (misma respuesta del endpoint; sin regresión).

- [ ] **Step 4: Commit**

```bash
git add backend/app/facturas/service.py backend/app/facturas/router.py
git commit -m "refactor(facturas): extraer liquidacion_iva() a servicio (DRY; endpoint idéntico)"
```

---

### Task 6: Concepto `iva_cuatrimestre` — `cfo/calc/iva.py`

**Files:**
- Create: `backend/app/cfo/calc/iva.py`
- Test: `backend/tests/cfo/test_calc_iva.py`

**Interfaces:**
- Consumes: `app.facturas.service.liquidacion_iva() -> dict` (Task 5).
- Produces: `async iva_cuatrimestre() -> ResultadoCFO` (concepto `"iva_cuatrimestre"`, unidad `"COP"`): el `neto_a_pagar` del período VIGENTE (el que contiene hoy) + su fecha DIAN en la evidencia.

- [ ] **Step 1: Test que falla**

```python
# backend/tests/cfo/test_calc_iva.py
import pytest
from decimal import Decimal


@pytest.mark.asyncio
async def test_iva_toma_neto_del_periodo_vigente(monkeypatch):
    from app.cfo.calc import iva as mod
    async def _liq():
        return {"periodicidad": "cuatrimestral", "periodos": [
            {"anio": 2026, "periodo": 2, "etiqueta": "2026-C2",
             "neto_a_pagar": "26000000.00",
             "proximo_pago": {"fecha": "2026-09-10", "dias": 31}},
        ]}
    monkeypatch.setattr(mod, "_liquidacion", _liq)
    # hoy dentro de C2 (may-ago): 2026-08-10
    monkeypatch.setattr(mod, "_periodo_vigente_idx", lambda: (2026, 2))
    r = await mod.iva_cuatrimestre()
    assert r.disponible is True and r.valor == Decimal("26000000.00")
    assert r.evidencia.fecha_corte == "2026-09-10" and r.evidencia.ref == "2026-C2"


@pytest.mark.asyncio
async def test_iva_sin_periodo_vigente_abstiene(monkeypatch):
    from app.cfo.calc import iva as mod
    async def _liq():
        return {"periodicidad": "cuatrimestral", "periodos": []}
    monkeypatch.setattr(mod, "_liquidacion", _liq)
    monkeypatch.setattr(mod, "_periodo_vigente_idx", lambda: (2026, 3))
    r = await mod.iva_cuatrimestre()
    assert r.disponible is False and r.valor is None
```

- [ ] **Step 2: Corre y verifica que falla**

Run: `cd backend && PYTHONUTF8=1 python -m pytest tests/cfo/test_calc_iva.py -q`
Expected: FAIL.

- [ ] **Step 3: Implementa** (el índice del cuatrimestre vigente se deriva del mes de hoy: C1 ene-abr, C2 may-ago, C3 sep-dic)

```python
# backend/app/cfo/calc/iva.py
"""FABS · concepto 'IVA del cuatrimestre'. Toma el neto a pagar del período fiscal
VIGENTE (el que contiene hoy) de la liquidación de COMPAS, con su fecha DIAN como
evidencia. Sin período vigente en la liquidación → abstención."""

from decimal import Decimal

from app.cfo.calc.evidencia import Evidencia, ResultadoCFO
from app.core.time import now_bogota
from app.facturas import service as fact_service


async def _liquidacion() -> dict:
    return await fact_service.liquidacion_iva()


def _periodo_vigente_idx() -> tuple[int, int]:
    ahora = now_bogota()
    idx = (ahora.month - 1) // 4 + 1  # 1..3 (cuatrimestral: ene-abr/may-ago/sep-dic)
    return (ahora.year, idx)


async def iva_cuatrimestre() -> ResultadoCFO:
    fuente = "facturas.service.liquidacion_iva"
    anio, idx = _periodo_vigente_idx()
    ref = f"{anio}-C{idx}"
    data = await _liquidacion()
    vig = next(
        (p for p in data["periodos"] if p["anio"] == anio and p["periodo"] == idx),
        None,
    )
    if vig is None:
        return ResultadoCFO(
            concepto="iva_cuatrimestre", valor=None, unidad="COP", disponible=False,
            evidencia=Evidencia(fuente=fuente, fecha_corte=None, ref=ref),
        )
    pago = vig.get("proximo_pago")
    fecha_dian = pago["fecha"] if pago else None
    return ResultadoCFO(
        concepto="iva_cuatrimestre", valor=Decimal(vig["neto_a_pagar"]), unidad="COP",
        disponible=True,
        evidencia=Evidencia(fuente=fuente, fecha_corte=fecha_dian, ref=vig["etiqueta"]),
        detalle={"generado": vig.get("generado"), "descontable": vig.get("descontable")},
    )
```

- [ ] **Step 4: Corre y verifica que pasa**

Run: `cd backend && PYTHONUTF8=1 python -m pytest tests/cfo/test_calc_iva.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/cfo/calc/iva.py backend/tests/cfo/test_calc_iva.py
git commit -m "feat(cfo): concepto iva_cuatrimestre (neto del periodo vigente + fecha DIAN)"
```

---

### Task 7: Modelo `cfo_goldens` + registro Beanie

**Files:**
- Create: `backend/app/cfo/goldens/__init__.py` (vacío)
- Create: `backend/app/cfo/goldens/modelo.py`
- Modify: `backend/app/domain/__init__.py` (registrar `CFOGolden` en `DOMAIN_DOCUMENTS`/`DOCUMENT_MODELS`)
- Test: `backend/tests/cfo/test_goldens_modelo.py`

**Interfaces:**
- Produces: `CFOGolden(Document)` con `concepto:str`, `filtros:dict`, `valor_esperado:Money|None`, `tolerancia:Decimal`, `unidad:str`, `origen:str`, `nota:str|None`, `creado_at:datetime`. Colección `cfo_goldens`.

- [ ] **Step 1: Test que falla**

```python
# backend/tests/cfo/test_goldens_modelo.py
from decimal import Decimal

import pytest
import pytest_asyncio
from app.domain import DOMAIN_DOCUMENTS
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient


@pytest_asyncio.fixture
async def db():
    c = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
    yield c


@pytest.mark.asyncio
async def test_persistir_y_leer_golden(db):
    from app.cfo.goldens.modelo import CFOGolden
    from app.core.time import now_bogota
    g = CFOGolden(
        concepto="runway", filtros={}, valor_esperado=Decimal("18.0"),
        tolerancia=Decimal("0.1"), unidad="meses", origen="semilla",
        nota="al 2026-08", creado_at=now_bogota(),
    )
    await g.insert()
    leido = await CFOGolden.find_one(CFOGolden.concepto == "runway")
    assert leido is not None and leido.valor_esperado == Decimal("18.0")
```

- [ ] **Step 2: Corre y verifica que falla**

Run: `cd backend && PYTHONUTF8=1 python -m pytest tests/cfo/test_goldens_modelo.py -q`
Expected: FAIL — `CFOGolden` no está registrado en Beanie / no existe.

- [ ] **Step 3: Implementa el modelo y regístralo**

```python
# backend/app/cfo/goldens/modelo.py
"""FABS · caso dorado. Un valor esperado (calculado a mano desde COMPAS) para un
concepto de cfo/calc, con su tolerancia. El runner compara el resultado real contra
esto. `valor_esperado=None` ⇒ caso de ABSTENCIÓN (el concepto debe dar disponible=False)."""

from datetime import datetime

from beanie import Document
from pydantic import ConfigDict, Field

from app.core.money import Money

CFO_GOLDENS_COLLECTION = "cfo_goldens"


class CFOGolden(Document):
    model_config = ConfigDict(strict=True, extra="forbid")

    concepto: str
    filtros: dict = Field(default_factory=dict)
    valor_esperado: Money | None
    tolerancia: Money  # Decimal; COP para montos, 0.1 para "meses"
    unidad: str
    origen: str  # 'semilla' | 'fabian'
    nota: str | None = None
    creado_at: datetime

    class Settings:
        name = CFO_GOLDENS_COLLECTION
```

En `backend/app/domain/__init__.py`, importa `CFOGolden` y agrégalo a la lista de documentos (`DOMAIN_DOCUMENTS` / `DOCUMENT_MODELS`). *(Lee el archivo para usar el nombre exacto de la lista y respetar el orden/formato.)*

- [ ] **Step 4: Corre y verifica que pasa**

Run: `cd backend && PYTHONUTF8=1 python -m pytest tests/cfo/test_goldens_modelo.py -q`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/cfo/goldens/ backend/app/domain/__init__.py backend/tests/cfo/test_goldens_modelo.py
git commit -m "feat(cfo): modelo cfo_goldens registrado en Beanie"
```

---

### Task 8: Runner de goldens — `cfo/goldens/runner.py`

**Files:**
- Create: `backend/app/cfo/goldens/runner.py`
- Test: `backend/tests/cfo/test_goldens_runner.py`

**Interfaces:**
- Consumes: `CFOGolden`; `app.cfo.calc.caja.caja_hoy`, `runway.runway`, `iva.iva_cuatrimestre` (todas `() -> ResultadoCFO`).
- Produces: `async correr_goldens() -> dict` → `{"total":int, "ok":int, "fallos":[{"concepto","esperado","obtenido","delta"}], "abstenciones_ok":int}`. Mapa `CONCEPTOS = {"caja_hoy": caja_hoy, "runway": runway, "iva_cuatrimestre": iva_cuatrimestre}`.

- [ ] **Step 1: Test que falla**

```python
# backend/tests/cfo/test_goldens_runner.py
from decimal import Decimal

import pytest
import pytest_asyncio
from app.domain import DOMAIN_DOCUMENTS
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient


@pytest_asyncio.fixture
async def db():
    c = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
    yield c


@pytest.mark.asyncio
async def test_runner_ok_fallo_y_abstencion(db, monkeypatch):
    from app.cfo.goldens import runner
    from app.cfo.goldens.modelo import CFOGolden
    from app.cfo.calc.evidencia import Evidencia, ResultadoCFO
    from app.core.time import now_bogota

    def _res(concepto, valor, unidad, disp=True):
        return ResultadoCFO(concepto=concepto, valor=valor, unidad=unidad, disponible=disp,
                            evidencia=Evidencia(fuente="x", fecha_corte=None, ref="r"))
    async def _runway():
        return _res("runway", Decimal("18.05"), "meses")
    async def _caja():
        return _res("caja_hoy", Decimal("700000000"), "COP")
    async def _iva():
        return _res("iva_cuatrimestre", None, "COP", disp=False)  # abstención
    monkeypatch.setattr(runner, "CONCEPTOS", {"runway": _runway, "caja_hoy": _caja, "iva_cuatrimestre": _iva})

    now = now_bogota()
    await CFOGolden(concepto="runway", valor_esperado=Decimal("18.0"), tolerancia=Decimal("0.1"),
                    unidad="meses", origen="semilla", creado_at=now).insert()   # OK (delta 0.05<0.1)
    await CFOGolden(concepto="caja_hoy", valor_esperado=Decimal("500000000"), tolerancia=Decimal("1"),
                    unidad="COP", origen="semilla", creado_at=now).insert()     # FALLO
    await CFOGolden(concepto="iva_cuatrimestre", valor_esperado=None, tolerancia=Decimal("1"),
                    unidad="COP", origen="semilla", creado_at=now).insert()     # abstención OK

    rep = await runner.correr_goldens()
    assert rep["total"] == 3 and rep["ok"] == 1 and rep["abstenciones_ok"] == 1
    assert len(rep["fallos"]) == 1 and rep["fallos"][0]["concepto"] == "caja_hoy"
```

- [ ] **Step 2: Corre y verifica que falla**

Run: `cd backend && PYTHONUTF8=1 python -m pytest tests/cfo/test_goldens_runner.py -q`
Expected: FAIL.

- [ ] **Step 3: Implementa**

```python
# backend/app/cfo/goldens/runner.py
"""FABS · runner de evaluación. Corre cada golden contra su concepto de cfo/calc y
compara dentro de tolerancia. Los goldens con valor_esperado=None son de ABSTENCIÓN:
pasan solo si el concepto devuelve disponible=False. No imprime: devuelve un reporte."""

from decimal import Decimal

from app.cfo.calc.caja import caja_hoy
from app.cfo.calc.iva import iva_cuatrimestre
from app.cfo.calc.runway import runway
from app.cfo.goldens.modelo import CFOGolden

CONCEPTOS = {
    "caja_hoy": caja_hoy,
    "runway": runway,
    "iva_cuatrimestre": iva_cuatrimestre,
}


async def correr_goldens() -> dict:
    total = ok = abst_ok = 0
    fallos: list[dict] = []
    async for g in CFOGolden.find_all():
        fn = CONCEPTOS.get(g.concepto)
        if fn is None:
            fallos.append({"concepto": g.concepto, "esperado": None,
                           "obtenido": None, "delta": "concepto desconocido"})
            total += 1
            continue
        r = await fn()
        total += 1
        if g.valor_esperado is None:  # caso de abstención
            if r.disponible is False and r.valor is None:
                abst_ok += 1
            else:
                fallos.append({"concepto": g.concepto, "esperado": "abstención",
                               "obtenido": str(r.valor), "delta": "no abstuvo"})
            continue
        if r.valor is None:
            fallos.append({"concepto": g.concepto, "esperado": str(g.valor_esperado),
                           "obtenido": None, "delta": "sin dato"})
            continue
        delta = (Decimal(r.valor) - Decimal(g.valor_esperado)).copy_abs()
        if delta <= Decimal(g.tolerancia):
            ok += 1
        else:
            fallos.append({"concepto": g.concepto, "esperado": str(g.valor_esperado),
                           "obtenido": str(r.valor), "delta": str(delta)})
    return {"total": total, "ok": ok, "fallos": fallos, "abstenciones_ok": abst_ok}
```

- [ ] **Step 4: Corre y verifica que pasa**

Run: `cd backend && PYTHONUTF8=1 python -m pytest tests/cfo/test_goldens_runner.py -q`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/cfo/goldens/runner.py backend/tests/cfo/test_goldens_runner.py
git commit -m "feat(cfo): runner de goldens (tolerancia + abstencion)"
```

---

### Task 9: Repositorio `cfo_*` + semilla de goldens

**Files:**
- Create: `backend/app/cfo/datos/__init__.py` (vacío)
- Create: `backend/app/cfo/datos/repositorios.py`
- Create: `backend/app/cfo/goldens/semilla.py`
- Test: `backend/tests/cfo/test_goldens_semilla.py`

**Interfaces:**
- Produces: `async sembrar_goldens(casos: list[CFOGolden]) -> tuple[int,int]` (insertados, ya-existentes) — idempotente por `(concepto, nota)`; escribe SOLO en `cfo_goldens`. `SEMILLA: list[dict]` con los casos iniciales.

- [ ] **Step 1: Test que falla**

```python
# backend/tests/cfo/test_goldens_semilla.py
import pytest
import pytest_asyncio
from app.domain import DOMAIN_DOCUMENTS
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient


@pytest_asyncio.fixture
async def db():
    c = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
    yield c


@pytest.mark.asyncio
async def test_sembrar_idempotente(db):
    from app.cfo.goldens.semilla import sembrar_semilla
    from app.cfo.goldens.modelo import CFOGolden
    ins1, dup1 = await sembrar_semilla()
    ins2, dup2 = await sembrar_semilla()  # segunda vez no duplica
    assert ins1 >= 1 and dup1 == 0
    assert ins2 == 0 and dup2 == ins1
    # todos los conceptos sembrados existen
    assert await CFOGolden.find_all().count() == ins1
```

- [ ] **Step 2: Corre y verifica que falla**

Run: `cd backend && PYTHONUTF8=1 python -m pytest tests/cfo/test_goldens_semilla.py -q`
Expected: FAIL.

- [ ] **Step 3: Implementa** el repositorio y la semilla

```python
# backend/app/cfo/datos/repositorios.py
"""FABS · única puerta de escritura del módulo. SOLO colecciones cfo_*. (S1: ninguna
otra subruta de cfo/ toca el driver de Mongo.)"""

from app.cfo.goldens.modelo import CFOGolden


async def upsert_golden(g: CFOGolden) -> bool:
    """Inserta el golden si no existe uno con el mismo (concepto, nota). Devuelve True
    si insertó, False si ya existía. Idempotente."""
    existe = await CFOGolden.find_one(
        CFOGolden.concepto == g.concepto, CFOGolden.nota == g.nota
    )
    if existe is not None:
        return False
    await g.insert()
    return True
```

```python
# backend/app/cfo/goldens/semilla.py
"""FABS · lote semilla de goldens (origen='semilla'). Valores editables/corregibles por
el CEO. El set completo (240+60, con Fabián) llega en un incremento posterior.
IMPORTANTE: los `valor_esperado` se sustituyen por los reales calculados a mano desde
PROD antes de dar por cerrado el incremento (ver Task 11)."""

from decimal import Decimal

from app.cfo.datos.repositorios import upsert_golden
from app.cfo.goldens.modelo import CFOGolden
from app.core.time import now_bogota

# Placeholder de estructura; los valores reales de PROD se fijan en la Task 11.
SEMILLA: list[dict] = [
    {"concepto": "runway", "valor_esperado": None, "tolerancia": Decimal("0.1"),
     "unidad": "meses", "nota": "abstención: sin parámetros vigentes"},
]


async def sembrar_semilla() -> tuple[int, int]:
    now = now_bogota()
    insertados = duplicados = 0
    for c in SEMILLA:
        g = CFOGolden(
            concepto=c["concepto"], filtros=c.get("filtros", {}),
            valor_esperado=c["valor_esperado"], tolerancia=c["tolerancia"],
            unidad=c["unidad"], origen="semilla", nota=c.get("nota"), creado_at=now,
        )
        if await upsert_golden(g):
            insertados += 1
        else:
            duplicados += 1
    return insertados, duplicados
```

- [ ] **Step 4: Corre y verifica que pasa**

Run: `cd backend && PYTHONUTF8=1 python -m pytest tests/cfo/test_goldens_semilla.py -q`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/cfo/datos/ backend/app/cfo/goldens/semilla.py backend/tests/cfo/test_goldens_semilla.py
git commit -m "feat(cfo): repositorio cfo_* + semilla idempotente de goldens"
```

---

### Task 10: Prueba estática S1 (aislamiento)

**Files:**
- Test: `backend/tests/cfo/test_s1_aislamiento.py`

**Interfaces:** ninguna (test de arquitectura).

- [ ] **Step 1: Escribe el test S1**

```python
# backend/tests/cfo/test_s1_aislamiento.py
"""S1: cfo/calc y cfo/goldens NO importan modelos de dominio ajenos ni tocan el driver
de Mongo; la única subruta que persiste es cfo/datos/repositorios.py y solo cfo_*."""
import pathlib
import re

CFO = pathlib.Path(__file__).resolve().parents[2] / "app" / "cfo"

# Subrutas que NO pueden tocar Mongo directamente ni importar modelos de dominio ajenos.
LOGICA = [CFO / "calc", CFO / "goldens"]
PROHIBIDO_IMPORT = re.compile(r"from app\.domain\.(?!__init__)")  # modelos de dominio ajenos
PROHIBIDO_DRIVER = re.compile(r"get_pymongo_collection|motor|AsyncIOMotor")


def _py_files(base):
    return [p for p in base.rglob("*.py") if p.name != "__init__.py"]


def test_calc_y_goldens_no_tocan_driver_ni_dominio_ajeno():
    ofensas = []
    for base in LOGICA:
        for f in _py_files(base):
            txt = f.read_text(encoding="utf-8")
            # excepción: cfo/goldens/modelo.py define su PROPIO Document (cfo_goldens)
            if f.name == "modelo.py":
                continue
            if PROHIBIDO_DRIVER.search(txt):
                ofensas.append(f"{f}: toca el driver de Mongo")
            for m in PROHIBIDO_IMPORT.finditer(txt):
                # se permite importar tipos de lectura de dominio SOLO si el spec lo
                # documenta; para inc1 no debería hacer falta ninguno en calc/goldens.
                ofensas.append(f"{f}: importa modelo de dominio ajeno ({m.group()})")
    assert ofensas == [], "Violaciones S1:\n" + "\n".join(ofensas)


def test_solo_repositorios_persiste_cfo():
    # cfo/datos/repositorios.py solo referencia CFOGolden (colección cfo_goldens)
    repo = (CFO / "datos" / "repositorios.py").read_text(encoding="utf-8")
    assert "CFOGolden" in repo
    assert "app.domain" not in repo  # no persiste colecciones ajenas
```

- [ ] **Step 2: Corre el test**

Run: `cd backend && PYTHONUTF8=1 python -m pytest tests/cfo/test_s1_aislamiento.py -q`
Expected: PASS. Si falla, corrige el import ofensor en `cfo/` (no relajes el test).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/cfo/test_s1_aislamiento.py
git commit -m "test(cfo): salvaguarda S1 (aislamiento de cfo/ respecto al driver y al dominio ajeno)"
```

---

### Task 11: Cierre — valores reales de la semilla + verificación de aislamiento del flag

**Files:**
- Modify: `backend/app/cfo/goldens/semilla.py` (valores reales de PROD)
- Modify: `docs/COMPAS_FABS_ROADMAP.md` (registro de cambios + estado)

- [ ] **Step 1: Calcula los valores reales desde PROD (solo lectura)**

Corre los 3 conceptos contra PROD (URI de `docs/INVENTARIO-SECRETOS.xlsx` por env var `MONGODB_URI_COMPAS`, `PYTHONUTF8=1`, NUNCA por argv) con un script efímero en el scratchpad que hace `init_beanie_for(compas)` y llama `caja_hoy()`, `runway()`, `iva_cuatrimestre()`. Anota los valores y fechas de corte.

- [ ] **Step 2: Fija la semilla con esos valores** (reemplaza el placeholder de la Task 9 por casos reales, p. ej. runway al 2026-08, IVA de C2-2026, y el caso de abstención). Cada caso con su `nota` fechada.

- [ ] **Step 3: Corre la suite completa de COMPAS con `cfo/` presente y flag apagado**

Run: `cd backend && PYTHONUTF8=1 python -m pytest tests/ -q`
Expected: toda la suite verde (los tests de COMPAS idénticos; los nuevos de `cfo/` verdes). Confirma que NINGÚN test de COMPAS cambió de resultado (flag apagado = idéntico).

- [ ] **Step 4: Actualiza el roadmap** (marca el incremento 1 como ✅, agrega fila fechada en el Registro de cambios con el hash del último commit).

- [ ] **Step 5: Commit + preparar paquete de gate Kimi**

```bash
git add backend/app/cfo/goldens/semilla.py docs/COMPAS_FABS_ROADMAP.md
git commit -m "chore(cfo): semilla real de goldens + cierre del incremento 1 (roadmap actualizado)"
```

Prepara la solicitud de auditoría Kimi (lee cifras de plata): `planning/phases/fabs-inc1/auditorias/PR1-I/` con SOLICITUD + EVIDENCIA (diff + salidas de tests). No mergear a `main` sin nota ≥ 9.0 o gate-waiver del CEO.

---

## Self-Review (cobertura del spec)

- §2 arquitectura (módulo, flag, S1) → Tasks 1, 2, 7, 9, 10.
- §3 contrato de evidencia → Task 1.
- §4 los 3 conceptos → Tasks 3, 4, 6 (con el refactor DRY de la Task 5).
- §5 arnés de goldens (modelo, runner, semilla) → Tasks 7, 8, 9.
- §8 pruebas (por concepto, runner, S1, flag-off idéntico) → Tasks 3/4/6, 8, 10, 11.
- §10 DoD → Task 11.
- Constraint "motor cero diffs" → ninguna task toca `motor.py`; la única modificación de COMPAS es el refactor DRY de facturas (Task 5, comportamiento idéntico, suite verde) y el registro Beanie (Task 7, aditivo).
- Tipos consistentes: `ResultadoCFO`/`Evidencia` (Task 1) usados por Tasks 3/4/6/8; `CFOGolden` (Task 7) usado por Tasks 8/9; `liquidacion_iva()` (Task 5) consumido por Task 6.
