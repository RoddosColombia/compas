# FABS · Provisión de IVA como tesorería (inc6 · #1) · Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** hacer accionable el fondo de provisión de IVA como tesorería — advisory de FABS + la "cerca" en el disponible + un 4º job proactivo del vigilante.

**Architecture:** un calc puro `iva_tesoreria` (5 conceptos) + su tool en FABS (advisory); un endpoint `GET /caja/disponible` que descompone bruto/reserva/neto + la barra que lo muestra (la cerca); un evaluador+job del vigilante que avisa cerca de la DIAN o si el disponible no cubre (proactivo). Objetivo de reserva = `FondoMes.saldo` del mes actual (computado del plan). CERO cambios de modelo/motor.

**Tech Stack:** Backend FastAPI + Beanie/Motor + Pydantic strict. Frontend React 19 + TS + Tailwind. Tests: pytest + mongomock (backend), Vitest + RTL (frontend).

**Spec:** `docs/superpowers/specs/2026-08-31-fabs-iva-tesoreria-design.md` (léelo junto a este plan).

## Global Constraints

- **Dinero = `Decimal`** backend, string en la API; formateo es-CO; sin float; el front NUNCA hace `Number` sobre montos (regla 1).
- **TZ** `now_bogota()`/`today_bogota()`; `dias` a la DIAN vía `proximo_pago`.
- **`app/proyeccion/motor.py` y `presupuesto/motor.py`: 0 diffs** (solo se LEE el fondo/liquidación).
- **S1:** calc puro en `cfo/calc` (NO importa motor/domain); evaluador/orquestación en `cfo/vigilante`. `test_s1_aislamiento` verde.
- **Catálogo de auditoría cerrado** (regla 11): +2 (`vigilante.iva.generado/publicado`), 72 → **74**.
- **Scheduler solo en el worker** (regla 6); job idempotente; no-op si `CFO_ENABLED` off o `ALERTA_IVA_ACTIVA` off.
- **RBAC por dependencia**; sin permiso nuevo. **Anti-alucinación:** cifras por token; el proactivo es determinista (token+verificador); publicar no recomputa.
- **CERO cambios de modelo:** `AvisoVigilante(tipo)` ya es genérico (`tipo='iva_tesoreria'`).

---

### Task 1: Config (2 claves + resolvers) + 2 eventos de auditoría (72→74)

**Files:**
- Modify: `backend/app/domain/configuracion.py` (2 claves + `_TIPO_POR_CLAVE`)
- Modify: `backend/app/configuracion/service.py` (resolvers + writers)
- Modify: `backend/app/audit/events.py` (2 eventos)
- Modify: `backend/tests/test_audit_events.py`
- Test: `backend/tests/configuracion/test_alerta_iva_config.py` (nuevo)

**Interfaces:**
- Produces: `ClaveConfig.ALERTA_IVA_ACTIVA` (`{"activa": bool}`, default False), `ClaveConfig.ALERTA_IVA_DIAS` (`{"dias": int}`, default 30); `leer_alerta_iva_activa() -> bool`, `leer_alerta_iva_dias() -> int`; `AuditEvento.vigilante_iva_generado="vigilante.iva.generado"`, `vigilante_iva_publicado="vigilante.iva.publicado"`.

- [ ] **Step 1: Tests** (config resolvers + catálogo)

```python
# backend/tests/configuracion/test_alerta_iva_config.py
import pytest
import pytest_asyncio
from app.configuracion.service import (
    escribir_alerta_iva_activa, escribir_alerta_iva_dias,
    leer_alerta_iva_activa, leer_alerta_iva_dias,
)
from app.domain import DOMAIN_DOCUMENTS
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient


@pytest_asyncio.fixture
async def db():
    client = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=client["compas_test"], document_models=DOMAIN_DOCUMENTS)
    yield client


@pytest.mark.asyncio
async def test_defaults(db):
    assert await leer_alerta_iva_activa() is False
    assert await leer_alerta_iva_dias() == 30


@pytest.mark.asyncio
async def test_escribir_y_leer(db):
    await escribir_alerta_iva_activa(activa=True, usuario_id="a")
    await escribir_alerta_iva_dias(dias=15, usuario_id="a")
    assert await leer_alerta_iva_activa() is True
    assert await leer_alerta_iva_dias() == 15
```

En `backend/tests/test_audit_events.py`: subir `len(AuditEvento)`/`len(CATALOGO_EVENTOS)` de 72 a **74** y añadir los 2 eventos a la lista esperada.

- [ ] **Step 2: Correr — deben fallar**

Run: `python -m pytest tests/configuracion/test_alerta_iva_config.py tests/test_audit_events.py -q`
Expected: FAIL.

- [ ] **Step 3: Implementar**

En `configuracion.py::ClaveConfig` (+ `_TIPO_POR_CLAVE` ambas `"json"`):
```python
    ALERTA_IVA_ACTIVA = "ALERTA_IVA_ACTIVA"
    ALERTA_IVA_DIAS = "ALERTA_IVA_DIAS"
```

En `configuracion/service.py` (patrón de `leer_alerta_caja_activa`/`leer_alerta_horizonte_meses` ya existentes — cópialo):
```python
_ALERTA_IVA_DIAS_FALLBACK = 30


async def leer_alerta_iva_activa() -> bool:
    fila = (await Configuracion.find(Configuracion.clave == ClaveConfig.ALERTA_IVA_ACTIVA)
            .sort(-Configuracion.vigente_desde).first_or_none())
    if fila is None or fila.valor_json is None:
        return False
    return bool(fila.valor_json.get("activa", False))


async def leer_alerta_iva_dias() -> int:
    fila = (await Configuracion.find(Configuracion.clave == ClaveConfig.ALERTA_IVA_DIAS)
            .sort(-Configuracion.vigente_desde).first_or_none())
    if fila is None or fila.valor_json is None:
        return _ALERTA_IVA_DIAS_FALLBACK
    d = fila.valor_json.get("dias")
    return d if isinstance(d, int) and d > 0 else _ALERTA_IVA_DIAS_FALLBACK


async def escribir_alerta_iva_activa(*, activa: bool, usuario_id: str, vigente_desde=None) -> Configuracion:
    fila = Configuracion(clave=ClaveConfig.ALERTA_IVA_ACTIVA, valor_json={"activa": bool(activa)},
                         vigente_desde=(vigente_desde or today_bogota()).isoformat(), modificado_por=usuario_id)
    await fila.insert()
    return fila


async def escribir_alerta_iva_dias(*, dias: int, usuario_id: str, vigente_desde=None) -> Configuracion:
    if not isinstance(dias, int) or dias <= 0:
        raise ConfiguracionError("los días deben ser un entero > 0", 422)
    fila = Configuracion(clave=ClaveConfig.ALERTA_IVA_DIAS, valor_json={"dias": dias},
                         vigente_desde=(vigente_desde or today_bogota()).isoformat(), modificado_por=usuario_id)
    await fila.insert()
    return fila
```

En `events.py::AuditEvento` (tras el bloque del cierre mensual):
```python
    # ── CR-CFO-6 (2) — FABS IVA tesorería (GO CEO 2026-08-31). Catálogo 72 -> 74.
    vigilante_iva_generado = "vigilante.iva.generado"
    vigilante_iva_publicado = "vigilante.iva.publicado"
```

- [ ] **Step 4: Verde**

Run: `python -m pytest tests/configuracion/test_alerta_iva_config.py tests/test_audit_events.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/configuracion.py backend/app/configuracion/service.py backend/app/audit/events.py backend/tests/configuracion/test_alerta_iva_config.py backend/tests/test_audit_events.py
git commit -m "feat(cfo): config ALERTA_IVA_ACTIVA/DIAS + 2 eventos de auditoria IVA (72->74)"
```

---

### Task 2: Calc puro `iva_tesoreria` (5 conceptos)

**Files:**
- Create: `backend/app/cfo/calc/iva_tesoreria.py`
- Test: `backend/tests/cfo/calc/test_iva_tesoreria.py` (nuevo)

**Interfaces:**
- Produces: `armar_conceptos(*, reserva_objetivo: Decimal | None, reserva_mes: Decimal | None, proximo_monto: Decimal | None, proximo_fecha: str | None, disponible: Decimal | None) -> list[ResultadoCFO]`. Cada insumo `None` ⇒ el/los concepto(s) que dependen salen `disponible=False` (abstención). Conceptos: `ivates_reserva_objetivo`, `ivates_reserva_mes`, `ivates_proximo_pago` (con `fecha_corte`), `ivates_disponible_neto`, `ivates_faltante`.

- [ ] **Step 1: Test**

```python
# backend/tests/cfo/calc/test_iva_tesoreria.py
from decimal import Decimal
from app.cfo.calc.iva_tesoreria import armar_conceptos


def _by(cs):
    return {c.concepto: c for c in cs}


def test_conceptos_completos_y_cobertura_cubierta():
    cs = _by(armar_conceptos(
        reserva_objetivo=Decimal("1000"), reserva_mes=Decimal("250"),
        proximo_monto=Decimal("3000"), proximo_fecha="2027-01-14",
        disponible=Decimal("1500")))
    assert cs["ivates_reserva_objetivo"].valor == Decimal("1000")
    assert cs["ivates_disponible_neto"].valor == Decimal("500")   # 1500 - 1000
    assert cs["ivates_faltante"].valor == Decimal("0")            # cubierto
    assert cs["ivates_proximo_pago"].evidencia.fecha_corte == "2027-01-14"


def test_descubierto_faltante_positivo_y_neto_negativo():
    cs = _by(armar_conceptos(
        reserva_objetivo=Decimal("1000"), reserva_mes=Decimal("250"),
        proximo_monto=Decimal("3000"), proximo_fecha="2027-01-14",
        disponible=Decimal("600")))
    assert cs["ivates_disponible_neto"].valor == Decimal("-400")
    assert cs["ivates_faltante"].valor == Decimal("400")


def test_sin_disponible_abstiene_neto_y_faltante():
    cs = _by(armar_conceptos(
        reserva_objetivo=Decimal("1000"), reserva_mes=Decimal("250"),
        proximo_monto=Decimal("3000"), proximo_fecha="2027-01-14", disponible=None))
    assert cs["ivates_disponible_neto"].disponible is False
    assert cs["ivates_faltante"].disponible is False
    assert cs["ivates_reserva_objetivo"].disponible is True  # este no depende del disponible
```

- [ ] **Step 2: Correr — falla**

Run: `python -m pytest tests/cfo/calc/test_iva_tesoreria.py -q`
Expected: FAIL.

- [ ] **Step 3: Implementar `iva_tesoreria.py`**

```python
# backend/app/cfo/calc/iva_tesoreria.py
"""FABS · calc PURO de la tesorería del IVA (S1: no importa motor/domain — recibe
números, arma ResultadoCFO). El objetivo de reserva es el saldo acumulado del fondo
del mes actual (computado del plan). Cada insumo ausente ⇒ abstención de lo que depende."""

from decimal import Decimal

from app.cfo.calc.evidencia import Evidencia, ResultadoCFO

_UNIDAD = "COP"
_FUENTE = "iva.liquidacion.plan_fondo_provision+conciliacion"


def _res(concepto: str, valor: Decimal | None, ref: str, fecha: str | None = None) -> ResultadoCFO:
    return ResultadoCFO(
        concepto=concepto, valor=valor, unidad=_UNIDAD, disponible=valor is not None,
        evidencia=Evidencia(fuente=_FUENTE, fecha_corte=fecha, ref=ref),
    )


def armar_conceptos(
    *, reserva_objetivo: Decimal | None, reserva_mes: Decimal | None,
    proximo_monto: Decimal | None, proximo_fecha: str | None, disponible: Decimal | None,
) -> list[ResultadoCFO]:
    neto = (disponible - reserva_objetivo) if (disponible is not None and reserva_objetivo is not None) else None
    faltante = (max(Decimal("0"), reserva_objetivo - disponible)
                if (disponible is not None and reserva_objetivo is not None) else None)
    return [
        _res("ivates_reserva_objetivo", reserva_objetivo, "objetivo:acumulado"),
        _res("ivates_reserva_mes", reserva_mes, "aporte:mes"),
        _res("ivates_proximo_pago", proximo_monto, "proximo:pago", fecha=proximo_fecha),
        _res("ivates_disponible_neto", neto, "neto:iva"),
        _res("ivates_faltante", faltante, "cobertura"),
    ]
```

- [ ] **Step 4: Verde** — `python -m pytest tests/cfo/calc/test_iva_tesoreria.py tests/cfo/test_s1_aislamiento.py -q`

- [ ] **Step 5: Commit**

```bash
git add backend/app/cfo/calc/iva_tesoreria.py backend/tests/cfo/calc/test_iva_tesoreria.py
git commit -m "feat(cfo): calc puro iva_tesoreria (5 conceptos, abstencion por insumo faltante)"
```

---

### Task 3: Tool `iva_tesoreria` (advisory) — wrapper + registro + formatear

**Files:**
- Modify: `backend/app/cfo/agente/tools.py` (wrapper + registro)
- Modify: `backend/app/cfo/agente/conceptos.py` (rama de `formatear` para `ivates_proximo_pago`)
- Modify: `backend/app/cfo/agente/prompt.py` (registrar los conceptos citables si el prompt los enumera)
- Test: `backend/tests/cfo/agente/test_tool_iva_tesoreria.py` (nuevo)

**Interfaces:**
- Consumes: Task 2 (`armar_conceptos`), `proyeccion.service.proyectar_vigente` (→ `fondo_provision`), `cfo.calc.iva.iva_cuatrimestre` (monto+fecha del próximo pago), `cierre.service.conciliacion` (disponible), `MesControl`/`EstadoMes`.
- Produces: tool `iva_tesoreria` en el registry de FABS.

- [ ] **Step 1: Test** (fakes de los servicios; verifica que arma los conceptos y que un `%`/cifra cruda NO aparece)

```python
# backend/tests/cfo/agente/test_tool_iva_tesoreria.py
from decimal import Decimal
import pytest
from app.cfo.agente import tools


@pytest.mark.asyncio
async def test_wrapper_arma_conceptos(monkeypatch):
    async def fake_proy(**k):
        return {"fondo_provision": [
            {"mes": "2026-08", "reserva": "250", "pago": "0", "saldo": "1000"},
        ]}
    monkeypatch.setattr(tools.proy_service, "proyectar_vigente", fake_proy)

    async def fake_iva():
        from app.cfo.calc.evidencia import Evidencia, ResultadoCFO
        return ResultadoCFO(concepto="iva_cuatrimestre", valor=Decimal("3000"), unidad="COP",
                            disponible=True, evidencia=Evidencia(fuente="f", fecha_corte="2027-01-14", ref="x"))
    monkeypatch.setattr(tools.iva, "iva_cuatrimestre", fake_iva)

    async def fake_disp():
        return Decimal("600")
    monkeypatch.setattr(tools, "_disponible_hoy", fake_disp)  # helper del wrapper
    # el mes actual lo fija el wrapper con now_bogota; fake_proy trae 2026-08 → alinéalo en el test si hace falta

    res = await tools._iva_tesoreria({})
    by = {r.concepto: r for r in res}
    assert "ivates_reserva_objetivo" in by and "ivates_faltante" in by
```

(Ajusta el fake del mes al `now_bogota()` real o inyecta el mes; el implementador resuelve el detalle de alineación mes↔fondo.)

- [ ] **Step 2: Correr — falla**

- [ ] **Step 3: Implementar** el wrapper `_iva_tesoreria(entrada)` en `tools.py`: lee `proyectar_vigente` (abstención total ante `ProyeccionError`), toma el `fondo_provision` del **mes actual** (`now_bogota()` → `YYYY-MM`); `reserva_objetivo=Decimal(saldo)`, `reserva_mes=Decimal(reserva)`; llama `iva.iva_cuatrimestre()` para `proximo_monto`/`proximo_fecha` (de su `valor`/`evidencia.fecha_corte`, `None` si abstuvo); `disponible` = un helper `_disponible_hoy()` que busca el mes `EN_EJECUCION` y devuelve `Decimal(conciliacion["consolidado_reportado"])` o `None` si `CierreError`/`sin_dato`. Pasa todo a `armar_conceptos`. Registrar la tool en el dict de dispatch + la lista de schemas (mismo patrón que `iva_del_cuatrimestre`), con una `description` clara ("estado de la reserva de IVA como tesorería: objetivo, próximo pago, cobertura").

En `conceptos.py::formatear`, extender la rama del IVA para que `ivates_proximo_pago` también renderice "vence el {fecha}, en {dias} días":
```python
    if r.concepto in ("iva_cuatrimestre", "ivates_proximo_pago"):
```
(Solo display, post-verificación; no toca el verificador.)

Si `prompt.py` enumera los conceptos citables, añadir los `ivates_*`.

- [ ] **Step 4: Verde** — `python -m pytest tests/cfo/agente/test_tool_iva_tesoreria.py tests/cfo -q`

- [ ] **Step 5: Commit** — `feat(cfo): tool iva_tesoreria (advisory del fondo de IVA como tesoreria)`

---

### Task 4: Endpoint `GET /api/v1/caja/disponible` (la cerca, backend)

**Files:**
- Modify: `backend/app/caja/router.py`
- Test: `backend/tests/caja/test_disponible.py` (nuevo)

**Interfaces:**
- Produces: `GET /api/v1/caja/disponible -> DisponibleTesoreria {bruto, reserva_iva, neto, fecha_corte, sin_dato}`. Reusa el RBAC con que hoy se lee el saldo (mira las otras rutas de `caja/router.py`; NO permiso nuevo).

- [ ] **Step 1: Test** (fakea conciliacion + proyectar_vigente)

Cubrir: bruto = `consolidado_reportado`; `reserva_iva` = saldo del fondo del mes; `neto = bruto − reserva`; sin fondo/`ProyeccionError` → `reserva_iva="0"`, `neto==bruto`; `sin_dato` propagado. RBAC (403 sin permiso), 401 sin token.

- [ ] **Step 2–3: Implementar** el handler: busca el mes `EN_EJECUCION`, `conciliacion(mes)` → `bruto`+`sin_dato`; `proyectar_vigente` → `fondo_provision[mes_actual].saldo` como `reserva_iva` (o `"0"` si `ProyeccionError`/sin entrada); `neto = money_str(Decimal(bruto) - Decimal(reserva_iva))`. Todo money como string. `DisponibleTesoreria(BaseModel, strict, extra=forbid)`.

- [ ] **Step 4: Verde** — `python -m pytest tests/caja -q`

- [ ] **Step 5: Commit** — `feat(caja): GET /caja/disponible con bruto/reserva_iva/neto (cerca de tesoreria)`

---

### Task 5: Frontend — la barra muestra bruto + neto de IVA

**Files:**
- Modify: el componente de la barra de saldo en vivo (localiza el que consume el disponible — `src/components/caja/ReporteCajaCard.tsx` o `src/components/layout/MesStatusBar.tsx`; grep `consolidado`/`disponible`)
- Modify/Create: `src/lib/caja.ts` (o donde viva el fetch del saldo) — tipo + fetch de `/caja/disponible`
- Test: el `.test.tsx` del componente

**Interfaces:**
- Consumes: `GET /caja/disponible` (Task 4).
- Produces: la barra muestra el **bruto** y una línea "de eso, $X apartado para IVA → disponible real $Y" (los tres strings tal cual del backend).

- [ ] **Step 1: Test** — mockea el fetch; la barra pinta el bruto y la línea de neto-de-IVA; NUNCA `Number` sobre montos.
- [ ] **Step 2–3: Implementar** el fetch tipado (`{bruto, reserva_iva, neto, fecha_corte, sin_dato}`) + la línea en la barra (Tailwind mínimo; Cowork pule). Si `reserva_iva === "0"`/`"$0"`, ocultar la línea (la cerca no aplica sin fondo).
- [ ] **Step 4: Verde** — `npx vitest run <el test>` y `npm run build`.
- [ ] **Step 5: Commit** — `feat(frontend): la barra de saldo muestra el neto de IVA (cerca de tesoreria)`

---

### Task 6: Vigilante — evaluador + `generar_y_entregar_iva` (proactivo)

**Files:**
- Create: `backend/app/cfo/vigilante/iva.py`
- Test: `backend/tests/cfo/vigilante/test_iva.py` (nuevo)

**Interfaces:**
- Consumes: Task 2 (`armar_conceptos`), Task 3 (`_disponible_hoy` o replica la lectura), `proyeccion.service`, `iva.iva_cuatrimestre`, `configuracion.leer_alerta_iva_dias`, `AvisoVigilante`, `AuditEvento.vigilante_iva_generado`, `alerta_texto`-style construcción, `config.vigilante_revisor_telegram_id`, `crear_cliente_telegram`.
- Produces: `async generar_y_entregar_iva() -> AvisoVigilante | None`. Espeja `cfo/vigilante/alerta.py` (LÉELO — mismo supersede diario/soft-audit/envío), con estos deltas:
  - **Disparo** (evaluar): calcula `reserva_objetivo` (fondo mes actual) + `proximo_pago` (`{fecha,dias}` vía `iva.liquidacion.proximo_pago`) + `disponible`. Dispara si **`dias <= leer_alerta_iva_dias()`** (cerca DIAN) **o** **`disponible < reserva_objetivo`** (descubierto). Si no dispara → retira borrador pendiente, None. Frescura: `sin_dato`/sin config → el disparador que dependa se abstiene (el de "cerca DIAN" no depende del disponible).
  - **Texto DETERMINISTA** (plantilla + tokens `ivates_*` + `verificar` + `sustituir_tokens`, como `alerta_texto.py`): línea "cerca DIAN" (📅 con `[[ivates_proximo_pago]]` + `[[ivates_reserva_objetivo]]`) y/o línea "descubierto" (🔴 con `[[ivates_faltante]]` + `[[ivates_reserva_objetivo]]`).
  - Guarda `AvisoVigilante(tipo='iva_tesoreria', periodo=<YYYY-MM>)`, soft-audit `vigilante.iva.generado`, envía al revisor con "Respondé 'publicar iva'".

- [ ] Steps TDD (rojo→verde), mirroring `test_alerta.py`: dispara por dias<=umbral; dispara por descubierto; no dispara (cubierto y lejos) → None + retira; abstención sin config. Commit: `feat(cfo): generar_y_entregar_iva (proactivo tesoreria IVA, determinista)`.

---

### Task 7: Vigilante — job diario + comando `publicar iva`

**Files:**
- Modify: `backend/app/jobs/scheduler.py` (4º job)
- Modify: `backend/app/cfo/telegram/webhook.py` (`_COMANDOS_PUBLICAR` + `_ETIQUETAS_AVISO`)
- Test: `backend/tests/jobs/test_scheduler_iva.py`, `backend/tests/cfo/telegram/test_webhook_publicar_iva.py`

**Interfaces:**
- Produces: job `vigilante_iva_tesoreria` (diario 7:45 Bogotá), no-op si `CFO_ENABLED` off o `not leer_alerta_iva_activa()`; comando `'publicar iva'` → `_publicar_aviso(tipo='iva_tesoreria', evento=AuditEvento.vigilante_iva_publicado)`.

- [ ] **Scheduler** (espeja `_job_alerta_caja`, con el gate extra `leer_alerta_iva_activa`): registra `vigilante_iva_tesoreria` (cron `hour=7, minute=45`, coalesce, misfire 3600); wrapper no-op si flag off o alerta IVA off; try/except+logger; docstring nombra los 4 jobs. Test: registrado (hora 7:45), no-op flag off, no-op alerta off, corre con ambos on.
- [ ] **Webhook**: en `_COMANDOS_PUBLICAR` añadir `"publicar iva": ("iva_tesoreria", AuditEvento.vigilante_iva_publicado)`; en `_ETIQUETAS_AVISO` añadir `"iva_tesoreria": ("un aviso de IVA", "Aviso de IVA", "publicado")`. Test: `publicar iva` difunde el borrador tipo iva_tesoreria + marca publicado + audita; no toca otros tipos; match exacto; dedup.
- [ ] Verde: `python -m pytest tests/jobs tests/cfo/telegram -q`. Commit: `feat(cfo): 4o job vigilante (IVA tesoreria 7:45) + comando 'publicar iva'`.

---

### Task 8: Cierre — guardas + roadmap

**Files:**
- Modify: `docs/COMPAS_FABS_ROADMAP.md`

- [ ] **Step 1: Guardas.** Run:
```bash
git fetch origin -q
git diff --stat origin/main..HEAD -- backend/app/proyeccion/motor.py backend/app/presupuesto/motor.py && echo "motor 0 diffs OK"
cd backend && python -m pytest tests/cfo tests/jobs tests/configuracion tests/caja tests/test_audit_events.py -q && python -m ruff check app/cfo app/jobs app/caja app/configuracion && python -m pytest tests/cfo/test_s1_aislamiento.py -q && python -c "from app.audit.events import CATALOGO_EVENTOS; print(len(CATALOGO_EVENTOS))" && cd ..
cd frontend && npm run build && cd ..
```
Expected: motor 0 diffs; suites verdes; ruff limpio; S1 verde; catálogo **74**; build front verde.
- [ ] **Step 2: Roadmap** — entrada fechada 2026-08-31 de la provisión de IVA como tesorería (inc6 #1): advisory (tool `iva_tesoreria`), la cerca (`/caja/disponible` bruto/neto), proactivo (4º job vigilante `publicar iva`), objetivo computado del plan; 2 eventos (72→74); gate = gate-waiver + GO CEO (NO afirmar que Kimi aprobó). Nombrar las 2 piezas de inc6 que faltan.
- [ ] **Step 3: Commit** — `docs(fabs): provision de IVA como tesoreria — roadmap`.

---

## Self-Review

**1. Spec coverage:** §5.1 advisory→Tasks 2+3; §5.2 cerca→Tasks 4+5; §5.3 proactivo→Tasks 6+7; config/eventos→Task 1; §6 anti-alucinación→Tasks 2/3 (token) + 6 (determinista+verificador); §7 reglas→Global Constraints + Task 8; §8 casos borde→Tasks 2/4/6; §9 testing→cada task; §10 fuera de alcance→respetado. Cubierto.

**2. Placeholder scan:** los tasks novel (1–5) traen código real; los del vigilante (6–7) dan los deltas concretos sobre `alerta.py`/`_job_alerta_caja`/`_COMANDOS_PUBLICAR` (código MERGEADO que el implementador lee) — triggers, plantillas, tipo, eventos y horas están explícitos.

**3. Type consistency:** conceptos `ivates_*` idénticos en calc (T2), tool (T3), evaluador (T6). `armar_conceptos(...)` firma única (T2) consumida por T3 y T6. `DisponibleTesoreria{bruto,reserva_iva,neto,fecha_corte,sin_dato}` (T4) ↔ el tipo del front (T5). `AvisoVigilante(tipo='iva_tesoreria')` + `AuditEvento.vigilante_iva_generado/publicado` (T1) usados en T6/T7. `_COMANDOS_PUBLICAR["publicar iva"]`/`_ETIQUETAS_AVISO["iva_tesoreria"]` (T7). `leer_alerta_iva_activa/dias` (T1) en T6/T7. Consistente.
