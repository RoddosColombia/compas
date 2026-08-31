# FABS · Vigilante — Cierre mensual comentado · Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** cuando un mes cierra, FABS lo comenta (narrado, borrador→"publicar cierre") — un job diario detecta el último mes cerrado y genera la retrospectiva reusando `consultar()`.

**Architecture:** 3er job del scheduler (worker) → `generar_y_entregar_cierre()` (orquestación en `cfo/vigilante`, espeja `paquete.py`) → `consultar()` con un prompt de cierre (5 puntos) → `AvisoVigilante(tipo='cierre_mensual', periodo='YYYY-MM')` borrador al revisor → `publicar cierre` difunde al comité. CERO cambios de modelo.

**Tech Stack:** FastAPI + Beanie/Motor + MongoDB, Pydantic strict, APScheduler, Telegram (fakes en test). Tests: pytest + mongomock-motor.

**Spec:** `docs/superpowers/specs/2026-08-30-fabs-vigilante-cierre-mensual-design.md` (léelo junto a este plan).

## Global Constraints

- **Dinero = `Decimal`**; el generador NO hace aritmética de dinero (reusa tools de FABS). Formateo es-CO por `conceptos.formatear`. NUNCA float.
- **TZ única** `now_bogota()`; `periodo = mc.mes[:7]` (`'YYYY-MM'`). Timestamps TZ-aware.
- **`app/proyeccion/motor.py` y `app/presupuesto/motor.py`: 0 diffs** vs `origin/main` (solo se LEE).
- **S1:** el código nuevo vive en `cfo/vigilante/` (orquestación). `cfo/calc/**` NO se toca; `tests/cfo/test_s1_aislamiento.py` verde.
- **Catálogo de auditoría cerrado** (regla 11): exactamente **+2** eventos (`vigilante.cierre.generado`, `vigilante.cierre.publicado`), catálogo 70 → **72**.
- **Scheduler solo en el worker** (regla 6); job idempotente por `(tipo, periodo)`; no-op si `CFO_ENABLED` off.
- **Auditoría del vigilante = SOFT** (try/except + logger).
- **Anti-alucinación:** reusa `consultar()` (verifica antes de sustituir); se difunde solo el `texto` sustituido; publicar nunca recomputa.
- **CERO cambios de modelo:** `AvisoVigilante(tipo)` ya es genérico — solo se usa el valor `tipo='cierre_mensual'`.

---

### Task 1: 2 eventos de auditoría (catálogo 70 → 72)

**Files:**
- Modify: `backend/app/audit/events.py`
- Modify: `backend/tests/test_audit_events.py`

**Interfaces:**
- Produces: `AuditEvento.vigilante_cierre_generado = "vigilante.cierre.generado"`, `AuditEvento.vigilante_cierre_publicado = "vigilante.cierre.publicado"`.

- [ ] **Step 1: Actualizar el test del catálogo**

En `backend/tests/test_audit_events.py`: subir las dos aserciones `len(AuditEvento) == 70` → `72` y `len(CATALOGO_EVENTOS) == 70` → `72`; añadir `"vigilante.cierre.generado"` y `"vigilante.cierre.publicado"` a la lista de eventos esperados (busca dónde se enumeran los `vigilante.alerta.*` y agrégalos al lado).

- [ ] **Step 2: Correr — debe fallar** (cuenta 70 ≠ 72)

Run: `python -m pytest tests/test_audit_events.py -q`
Expected: FAIL.

- [ ] **Step 3: Añadir los 2 eventos en `events.py`**

Tras el bloque de la alerta de caja, dentro de `AuditEvento`:

```python
    # ── CR-CFO-5 (2) — FABS vigilante cierre mensual comentado (GO CEO 2026-08-30) ──
    # `vigilante.cierre.generado` = el job diario detectó un mes cerrado y armó el
    # comentario (metadata {periodo, abstuvo, conceptos_usados}); `.publicado` = el
    # revisor lo difundió al comité (metadata {periodo, n_destinatarios}). Catálogo 70 -> 72.
    vigilante_cierre_generado = "vigilante.cierre.generado"
    vigilante_cierre_publicado = "vigilante.cierre.publicado"
```

- [ ] **Step 4: Correr — verde**

Run: `python -m pytest tests/test_audit_events.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/audit/events.py backend/tests/test_audit_events.py
git commit -m "feat(cfo): 2 eventos de auditoria del cierre mensual (catalogo 70->72)"
```

---

### Task 2: Detector + generador `generar_y_entregar_cierre`

**Files:**
- Create: `backend/app/cfo/vigilante/cierre.py`
- Test: `backend/tests/cfo/vigilante/test_cierre.py` (nuevo)

**Interfaces:**
- Consumes: `AvisoVigilante` (modelo genérico ya existente), `AuditEvento.vigilante_cierre_generado` (Task 1), `MesControl`/`EstadoMes` (`app.domain.mes_control`), `cfo.agente.servicio.consultar`, `cfo.agente.cliente.crear_cliente`, `cfo.telegram.cliente.crear_cliente_telegram`, `cfo.config.vigilante_revisor_telegram_id`.
- Produces: `async generar_y_entregar_cierre() -> AvisoVigilante | None`. Idempotente por mes; solo mira el ÚLTIMO mes cerrado (nunca backfill).

- [ ] **Step 1: Escribir el test** (fakea `consultar`; NO llama al LLM real)

```python
# backend/tests/cfo/vigilante/test_cierre.py
import pytest
import pytest_asyncio
from app.audit import service as audit_service
from app.cfo.agente.modelos import RespuestaCFO, UsoLLM
from app.cfo.vigilante import cierre as C
from app.cfo.vigilante.modelos import AvisoVigilante
from app.core.time import now_bogota
from app.domain import DOMAIN_DOCUMENTS
from app.domain.mes_control import EstadoMes, MesControl
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient


@pytest_asyncio.fixture
async def db():
    client = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=client["compas_test"], document_models=DOMAIN_DOCUMENTS)
    yield client


@pytest.fixture
def audit_col():
    client = AsyncMongoMockClient()
    audit_service.configure_audit(client, "compas_test_audit")
    yield client["compas_test_audit"]["audit_log"]
    audit_service.reset_audit()


class FakeTg:
    def __init__(self):
        self.enviados = []

    async def enviar(self, chat_id, texto):
        self.enviados.append((chat_id, texto))


async def _sembrar_mes(mes: str, estado: EstadoMes) -> None:
    # MesControl es strict/extra-forbid: `mes` debe ser 'YYYY-MM-01' y
    # `saldo_inicial_caja` (Money) es obligatorio (sin default).
    from decimal import Decimal

    await MesControl(mes=mes, estado=estado, saldo_inicial_caja=Decimal("0")).insert()


def _resp(texto="Cerró bien.", abstuvo=False):
    # cifras usa su default (lista vacía). La rama de descarte es `abstuvo and not
    # resp.cifras`: con abstuvo=False el generador PROCEDE (no mira cifras); con
    # abstuvo=True y cifras vacío, ABSTIENE. No hace falta poblar cifras (evita
    # construir objetos Cifra reales y chocar con Pydantic strict).
    return RespuestaCFO(
        texto=texto, abstuvo=abstuvo, texto_crudo=texto,
        uso=UsoLLM(modelo="m", tokens_in=1, tokens_out=1, iteraciones=1),
    )


@pytest.mark.asyncio
async def test_comenta_el_ultimo_mes_cerrado(db, audit_col, monkeypatch):
    monkeypatch.setenv("VIGILANTE_REVISOR_TELEGRAM_ID", "999")
    await _sembrar_mes("2026-06-01", EstadoMes.CERRADO)
    await _sembrar_mes("2026-07-01", EstadoMes.CERRADO)
    await _sembrar_mes("2026-08-01", EstadoMes.EN_EJECUCION)

    capturado = {}

    async def fake_consultar(prompt, *, actor_id, cliente=None, historial=None):
        capturado["prompt"] = prompt
        return _resp()

    monkeypatch.setattr(C, "consultar", fake_consultar)
    tg = FakeTg()
    monkeypatch.setattr(C, "crear_cliente_telegram", lambda: tg)

    aviso = await C.generar_y_entregar_cierre()
    assert aviso is not None
    assert aviso.tipo == "cierre_mensual" and aviso.periodo == "2026-07"  # el último CERRADO
    assert "2026-07" in capturado["prompt"]
    assert "publicar cierre" in tg.enviados[-1][1]
    doc = await audit_col.find_one({"evento": "vigilante.cierre.generado"})
    assert doc is not None and doc["metadata"]["periodo"] == "2026-07"


@pytest.mark.asyncio
async def test_idempotente_no_recomenta(db, audit_col, monkeypatch):
    await _sembrar_mes("2026-07-01", EstadoMes.CERRADO)
    await AvisoVigilante(tipo="cierre_mensual", periodo="2026-07", texto="ya",
                         texto_crudo="ya", estado="borrador",
                         generado_at=now_bogota()).insert()

    async def fake_consultar(*a, **k):
        raise AssertionError("no debe llamar a consultar si ya existe")

    monkeypatch.setattr(C, "consultar", fake_consultar)
    assert await C.generar_y_entregar_cierre() is None


@pytest.mark.asyncio
async def test_sin_mes_cerrado_es_none(db, audit_col, monkeypatch):
    await _sembrar_mes("2026-08-01", EstadoMes.EN_EJECUCION)
    assert await C.generar_y_entregar_cierre() is None


@pytest.mark.asyncio
async def test_abstencion_sin_cifras_no_guarda(db, audit_col, monkeypatch):
    await _sembrar_mes("2026-07-01", EstadoMes.CERRADO)

    async def fake_consultar(*a, **k):
        return _resp(abstuvo=True)  # cifras vacío por default → abstiene

    monkeypatch.setattr(C, "consultar", fake_consultar)
    assert await C.generar_y_entregar_cierre() is None
    assert await AvisoVigilante.find_one({}) is None
```

- [ ] **Step 2: Correr — debe fallar** (`ModuleNotFoundError`)

Run: `python -m pytest tests/cfo/vigilante/test_cierre.py -q`
Expected: FAIL.

- [ ] **Step 3: Implementar `cierre.py`**

```python
# backend/app/cfo/vigilante/cierre.py
"""FABS · vigilante — comenta el cierre de un mes. Job detector: mira el ÚLTIMO mes
CERRADO y, si no tiene comentario, FABS lo narra (reusa `consultar`, mismo contrato
anti-alucinación que el paquete del lunes). Idempotente por mes; nunca hace backfill
(solo el último cerrado). Fail-soft: un job proactivo no revienta el worker."""

import logging

from app.audit.events import AuditEvento
from app.audit.service import emit_audit
from app.cfo import config
from app.cfo.agente.cliente import crear_cliente
from app.cfo.agente.servicio import consultar
from app.cfo.telegram.cliente import crear_cliente_telegram
from app.cfo.vigilante.modelos import AvisoVigilante
from app.core.time import now_bogota
from app.domain.mes_control import EstadoMes, MesControl

logger = logging.getLogger(__name__)


def _prompt_cierre(periodo: str) -> str:
    return (
        f"Comentá el cierre del mes {periodo} de RODDOS, que acaba de cerrar. Cubrí, "
        "en orden y breve: (1) cómo cerró la caja del mes frente a cómo venía; (2) el "
        "real vs. el presupuesto — qué rubro se salió y por cuánto; (3) la composición "
        "del gasto del mes cerrado; (4) la tendencia del mes frente a los meses previos; "
        "(5) qué significa este cierre para el rumbo hacia el umbral de caja. Cita cada "
        "cifra con su token; si un dato no está disponible, omítelo con honestidad. Sé "
        "claro y conciso."
    )


async def _audit_soft(evento, entidad_id: str, metadata: dict) -> None:
    try:
        await emit_audit(evento, entidad="vigilante", entidad_id=entidad_id,
                         actor_id="vigilante", metadata=metadata)
    except Exception:  # noqa: BLE001 — job proactivo: no bloquear por auditoría
        logger.exception("fallo al auditar %s", evento)


async def generar_y_entregar_cierre() -> AvisoVigilante | None:
    mc = await (
        MesControl.find(MesControl.estado == EstadoMes.CERRADO)
        .sort(-MesControl.mes)
        .first_or_none()
    )
    if mc is None:
        return None
    periodo = mc.mes[:7]
    if await AvisoVigilante.find_one(
        AvisoVigilante.tipo == "cierre_mensual", AvisoVigilante.periodo == periodo
    ):
        logger.info("cierre del mes %s ya comentado; no se regenera", periodo)
        return None

    resp = await consultar(
        _prompt_cierre(periodo), actor_id="vigilante", cliente=crear_cliente()
    )
    if resp.abstuvo and not resp.cifras:
        logger.info("consultar abstuvo sin cifras; no se guarda cierre vacío")
        return None

    aviso = AvisoVigilante(
        tipo="cierre_mensual", periodo=periodo, texto=resp.texto,
        texto_crudo=resp.texto_crudo, estado="borrador", generado_at=now_bogota(),
        conceptos_usados=list(resp.conceptos_usados),
    )
    await aviso.insert()

    await _audit_soft(
        AuditEvento.vigilante_cierre_generado, periodo,
        {"periodo": periodo, "abstuvo": resp.abstuvo,
         "conceptos_usados": list(resp.conceptos_usados)},
    )

    revisor = config.vigilante_revisor_telegram_id()
    if revisor is None:
        logger.warning("VIGILANTE_REVISOR_TELEGRAM_ID sin configurar; cierre no enviado")
        return aviso
    cliente_tg = crear_cliente_telegram()
    if cliente_tg is not None:
        await cliente_tg.enviar(
            revisor,
            f"📆 Borrador del cierre de {periodo}\n\n" + resp.texto
            + "\n\nRespondé 'publicar cierre' para difundirlo al comité.",
        )
    return aviso
```

- [ ] **Step 4: Correr — verde**

Run: `python -m pytest tests/cfo/vigilante/test_cierre.py tests/cfo/test_s1_aislamiento.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/cfo/vigilante/cierre.py backend/tests/cfo/vigilante/test_cierre.py
git commit -m "feat(cfo): generar_y_entregar_cierre (detecta el ultimo mes cerrado + comenta via consultar)"
```

---

### Task 3: Job diario en el scheduler

**Files:**
- Modify: `backend/app/jobs/scheduler.py`
- Test: `backend/tests/jobs/test_scheduler_cierre.py` (nuevo)

**Interfaces:**
- Consumes: `cfo.config.cfo_enabled`, `cfo.vigilante.cierre.generar_y_entregar_cierre`.
- Produces: job `vigilante_cierre_mensual` (cron diario 7:30 Bogotá) + wrapper `_job_cierre_mensual` (no-op si flag off; crash-contenido).

- [ ] **Step 1: Escribir el test**

```python
# backend/tests/jobs/test_scheduler_cierre.py
import pytest
from app.jobs import scheduler as S


def test_job_cierre_registrado():
    sch = S.build_scheduler()
    job = sch.get_job("vigilante_cierre_mensual")
    assert job is not None
    f = {x.name: str(x) for x in job.trigger.fields}
    assert f["hour"] == "7" and f["minute"] == "30"


@pytest.mark.asyncio
async def test_noop_con_flag_off(monkeypatch):
    monkeypatch.setattr("app.cfo.config.cfo_enabled", lambda: False)
    llamado = {"v": False}

    async def _no(): llamado["v"] = True
    monkeypatch.setattr("app.cfo.vigilante.cierre.generar_y_entregar_cierre", _no)
    await S._job_cierre_mensual()
    assert llamado["v"] is False


@pytest.mark.asyncio
async def test_corre_con_flag_on(monkeypatch):
    monkeypatch.setattr("app.cfo.config.cfo_enabled", lambda: True)
    llamado = {"v": False}

    async def _si(): llamado["v"] = True
    monkeypatch.setattr("app.cfo.vigilante.cierre.generar_y_entregar_cierre", _si)
    await S._job_cierre_mensual()
    assert llamado["v"] is True
```

> Nota: la aserción del trigger (`job.trigger.fields`) espeja `test_scheduler_alerta.py`. Si la forma exacta difiere en la versión instalada de APScheduler, ajústala para que siga probando `hour=7, minute=30` de forma significativa.

- [ ] **Step 2: Correr — debe fallar**

Run: `python -m pytest tests/jobs/test_scheduler_cierre.py -q`
Expected: FAIL.

- [ ] **Step 3: Registrar el job + wrapper en `scheduler.py`**

En `build_scheduler`, tras el job de la alerta:

```python
    scheduler.add_job(
        _job_cierre_mensual, "cron", hour=7, minute=30,
        id="vigilante_cierre_mensual", coalesce=True, misfire_grace_time=3600,
        replace_existing=True,
    )
```

Nuevo wrapper (junto a `_job_alerta_caja`):

```python
async def _job_cierre_mensual() -> None:
    """Diario 7:30 (America/Bogota). Comenta el último mes cerrado si aún no tiene
    comentario. No-op si CFO_ENABLED off. Import perezoso para no acoplar el
    scheduler al dominio cfo."""
    from app.cfo import config as cfo_config

    if not cfo_config.cfo_enabled():
        return
    from app.cfo.vigilante.cierre import generar_y_entregar_cierre

    try:
        await generar_y_entregar_cierre()
    except Exception:  # noqa: BLE001 — un job proactivo no revienta el worker
        logger.exception("fallo en el job del cierre mensual")
```

Actualizar el docstring del módulo para nombrar los TRES jobs (paquete del lunes + alerta de caja + cierre mensual).

- [ ] **Step 4: Correr — verde**

Run: `python -m pytest tests/jobs/ -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/jobs/scheduler.py backend/tests/jobs/test_scheduler_cierre.py
git commit -m "feat(jobs): job diario del cierre mensual (7:30, no-op si off)"
```

---

### Task 4: Publicar — comando `publicar cierre` (mapa de comandos)

**Files:**
- Modify: `backend/app/cfo/telegram/webhook.py`
- Test: `backend/tests/cfo/telegram/test_webhook_publicar_cierre.py` (nuevo)

**Interfaces:**
- Consumes: `AvisoVigilante`, `AuditEvento.vigilante_cierre_publicado` (Task 1).
- Produces: comando exacto `'publicar cierre'` (solo revisor) → difunde el último borrador `tipo='cierre_mensual'`; `publicar`/`publicar alerta` siguen igual.

- [ ] **Step 1: Escribir el test**

```python
# backend/tests/cfo/telegram/test_webhook_publicar_cierre.py
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from app.audit import service as audit_service
from app.cfo.telegram import webhook
from app.cfo.telegram.modelos import VinculoTelegram
from app.cfo.vigilante.modelos import AvisoVigilante
from app.core.time import now_utc
from app.domain import DOMAIN_DOCUMENTS
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient


@pytest_asyncio.fixture
async def db():
    client = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=client["compas_test"], document_models=DOMAIN_DOCUMENTS)
    yield client


@pytest.fixture
def audit_col():
    client = AsyncMongoMockClient()
    audit_service.configure_audit(client, "compas_test_audit")
    yield client["compas_test_audit"]["audit_log"]
    audit_service.reset_audit()


class FakeTg:
    def __init__(self):
        self.enviados = []

    async def enviar(self, chat_id, texto):
        self.enviados.append((chat_id, texto))


async def _vinc(tid, uid):
    await VinculoTelegram(telegram_id=tid, user_id=uid, creado_por="a",
                          creado_at=now_utc()).insert()


@pytest.mark.asyncio
async def test_publicar_cierre_difunde_al_comite(db, audit_col, monkeypatch):
    monkeypatch.setenv("VIGILANTE_REVISOR_TELEGRAM_ID", "999")
    await _vinc(999, "rev")
    await _vinc(888, "com")
    await AvisoVigilante(tipo="cierre_mensual", periodo="2026-07", texto="EL CIERRE",
                         texto_crudo="c", estado="borrador",
                         generado_at=datetime.now(UTC)).insert()
    tg = FakeTg()
    upd = {"update_id": 1,
           "message": {"from": {"id": 999}, "chat": {"id": 999}, "text": "publicar cierre"}}
    await webhook.procesar_update(upd, cliente_telegram=tg)
    assert {c for c, t in tg.enviados if t == "EL CIERRE"} == {999, 888}
    got = await AvisoVigilante.find_one(AvisoVigilante.periodo == "2026-07")
    assert got.estado == "publicado"
    assert await audit_col.find_one({"evento": "vigilante.cierre.publicado"}) is not None


@pytest.mark.asyncio
async def test_publicar_cierre_no_toca_otros_tipos(db, audit_col, monkeypatch):
    monkeypatch.setenv("VIGILANTE_REVISOR_TELEGRAM_ID", "999")
    await _vinc(999, "rev")
    await AvisoVigilante(tipo="paquete_lunes", periodo="2026-08-31", texto="EL PAQUETE",
                         texto_crudo="c", estado="borrador",
                         generado_at=datetime.now(UTC)).insert()
    tg = FakeTg()
    upd = {"update_id": 2,
           "message": {"from": {"id": 999}, "chat": {"id": 999}, "text": "publicar cierre"}}
    await webhook.procesar_update(upd, cliente_telegram=tg)
    assert any("no hay" in t.lower() for _, t in tg.enviados)  # sin borrador de cierre
    pq = await AvisoVigilante.find_one(AvisoVigilante.tipo == "paquete_lunes")
    assert pq.estado == "borrador"  # el paquete intacto
```

- [ ] **Step 2: Correr — debe fallar**

Run: `python -m pytest tests/cfo/telegram/test_webhook_publicar_cierre.py -q`
Expected: FAIL.

- [ ] **Step 3: Generalizar el routing con un mapa de comandos**

En `webhook.py`, arriba de `procesar_update` (nivel de módulo), añadir el mapa (importa `AuditEvento` ya está):

```python
_COMANDOS_PUBLICAR = {
    "publicar": ("paquete_lunes", AuditEvento.vigilante_paquete_publicado),
    "publicar alerta": ("alerta_caja", AuditEvento.vigilante_alerta_publicada),
    "publicar cierre": ("cierre_mensual", AuditEvento.vigilante_cierre_publicado),
}
```

Reemplazar el bloque `if es_revisor and comando in ("publicar", "publicar alerta"): … if/else …` por:

```python
    comando = texto.strip().lower()
    es_revisor = telegram_id == config.vigilante_revisor_telegram_id()
    if es_revisor and comando in _COMANDOS_PUBLICAR:
        # los comandos de publicar NO llaman al LLM: registrar SOLO el dedup (sin tocar
        # los turnos que se re-alimentan al modelo) para que un reintento reenvíe la
        # confirmación en vez de re-difundir.
        tipo, evento = _COMANDOS_PUBLICAR[comando]
        envio = await _publicar_aviso(chat_id, cliente_telegram, tipo=tipo, evento=evento)
        await hilos.registrar_dedup(user_id, update_id, envio)
        return
```

En `_publicar_aviso`, reemplazar los condicionales binarios de "no hay"/etiqueta por un mapa que cubra los tres tipos:

```python
_ETIQUETAS_AVISO = {
    "paquete_lunes": ("un paquete", "Paquete", "publicado"),
    "alerta_caja": ("una alerta", "Alerta", "publicada"),
    "cierre_mensual": ("un cierre", "Cierre", "publicado"),
}
```

y usarlo: `sustantivo, etiqueta, participio = _ETIQUETAS_AVISO[tipo]`; el "no hay" pasa a `f"No hay {sustantivo} pendiente para publicar."`; la confirmación a `f"✅ {etiqueta} {participio} al comité ({len(vinculos_all)} destinatarios)."`. Actualizar el docstring de `_publicar_aviso` para nombrar los tres tipos.

- [ ] **Step 4: Correr los tests del publicar (los 3 tipos) — verde**

Run: `python -m pytest tests/cfo/telegram/ -q`
Expected: PASS (paquete + alerta siguen verdes; cierre pasa).

- [ ] **Step 5: Commit**

```bash
git add backend/app/cfo/telegram/webhook.py backend/tests/cfo/telegram/test_webhook_publicar_cierre.py
git commit -m "feat(cfo): comando 'publicar cierre' + mapa de comandos de publicar (3 tipos)"
```

---

### Task 5: Cierre — go-live doc + roadmap + guardas de rama

**Files:**
- Modify: `planning/phases/fabs/GO-LIVE-VIGILANTE.md`
- Modify: `docs/COMPAS_FABS_ROADMAP.md`

- [ ] **Step 1: Guardas de rama**

Run (desde `backend/`):
```bash
git fetch origin -q
git diff --stat origin/main..HEAD -- backend/app/proyeccion/motor.py backend/app/presupuesto/motor.py && echo "motor 0 diffs OK"
python -m pytest tests/cfo tests/jobs tests/test_audit_events.py -q
python -m ruff check app/cfo app/jobs
python -m pytest tests/cfo/test_s1_aislamiento.py -q
python -c "from app.audit.events import CATALOGO_EVENTOS; print(len(CATALOGO_EVENTOS))"
```
Expected: motor 0 diffs; suite verde; ruff limpio; S1 verde; catálogo **72**.

- [ ] **Step 2: `GO-LIVE-VIGILANTE.md`** — añadir sección "Cierre mensual comentado": el mismo worker `compas-jobs` lo corre (3er job, diario 7:30); se gobierna solo por `CFO_ENABLED` (no tiene interruptor propio como la alerta); comenta el último mes cerrado una sola vez; el revisor lo difunde con `publicar cierre`.

- [ ] **Step 3: `docs/COMPAS_FABS_ROADMAP.md`** — entrada fechada 2026-08-30 del cierre mensual: 3ª y última pieza del vigilante; narrado (reusa `consultar`); disparo por mes cerrado detectado; 5 puntos; gate = gate-waiver + GO CEO (NO afirmar que Kimi aprobó). Con esto el **vigilante queda completo (3 piezas)**.

- [ ] **Step 4: Commit**

```bash
git add planning/phases/fabs/GO-LIVE-VIGILANTE.md docs/COMPAS_FABS_ROADMAP.md
git commit -m "docs(fabs): cierre del vigilante — cierre mensual (go-live + roadmap)"
```

---

## Self-Review

**1. Spec coverage:** §5.1 sin cambios de modelo (usado en Tasks 2/4); §5.2 detector+generador→Task 2; §5.3 prompt 5 puntos→Task 2; §5.4 job→Task 3; §5.5 publicar→Task 4; §5.6 auditoría→Task 1 (declara) + Task 2/4 (emiten); §6 anti-alucinación→Task 2 (consultar) + Task 4 (no recomputa); §7 reglas→Global Constraints + Task 5 guardas; §8 casos borde→Task 2 (idempotente/sin-cerrado/abstención) + Task 4; §9 testing→cada task; §10 fuera de alcance→respetado. Cubierto.

**2. Placeholder scan:** cada step trae el código real; el prompt de cierre y las plantillas de mensaje son concretos; la sección de docs (Task 5) describe contenido concreto.

**3. Type consistency:** `generar_y_entregar_cierre()->AvisoVigilante|None` (Tasks 2/3). `AvisoVigilante(tipo='cierre_mensual', periodo=YYYY-MM, …)` idéntico en Tasks 2/4. `_publicar_aviso(chat_id, cliente, *, tipo, evento)->str` reusado (Task 4 solo extiende sus mapas). `AuditEvento.vigilante_cierre_generado/publicado` (Task 1) usados en Tasks 2/4. Mapa `_COMANDOS_PUBLICAR`/`_ETIQUETAS_AVISO` por tipo. Consistente.
