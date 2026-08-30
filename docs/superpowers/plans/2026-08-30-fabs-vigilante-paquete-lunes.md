# FABS · Vigilante — Paquete del lunes · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cada lunes 7:00, FABS genera un paquete semanal (reusando `consultar` + las tools existentes), lo entrega al revisor por Telegram como borrador, y cuando el revisor responde "publicar" lo difunde al comité — proactivo, auditado, con el contrato anti-alucinación intacto.

**Architecture:** Orquestación sobre piezas existentes. Un módulo nuevo `cfo/vigilante/` (modelo `PaqueteVigilante` + generador `paquete.py`), 2 eventos de auditoría nuevos (declarados en events.py = el CR), una config env del revisor, el PRIMER job del `scheduler.py` (hoy vacío), y un router de comando "publicar" en el webhook. El digest lo genera `servicio.consultar` (verifica + sustituye); solo se difunde el texto ya verificado.

**Tech Stack:** Python 3.12, FastAPI, Beanie/Motor + APScheduler, MongoDB (tests: mongomock, seed via `.insert()`), Pydantic strict, `decimal.Decimal`, pytest.

**Spec:** `docs/superpowers/specs/2026-08-30-fabs-vigilante-paquete-lunes-design.md`

## Global Constraints

- **El modelo NUNCA inventa cifras:** el digest pasa por `consultar` (cita `[[token]]`, verifica, sustituye). El vigilante NO computa cifras. Solo se difunde `paquete.texto` (ya sustituido/verificado en la generación); publicar NO re-llama al LLM.
- **`motor.py` cero diffs.** El vigilante es orquestación, no toca el motor.
- **Eventos de auditoría declarados** (regla 11): `vigilante.paquete.generado`/`.publicado` se agregan al catálogo cerrado en `events.py` (este plan = la construcción del CR que el spec declara). `emit_audit` valida contra el catálogo.
- **Idempotencia (regla 6):** un `PaqueteVigilante` por `semana` (índice único). `RUN_SCHEDULER` solo en `compas-jobs` (ya garantizado por `ensure_worker_context`; no se toca).
- **Flag `CFO_ENABLED`:** con el flag off, el job es no-op y el comando "publicar" cae al Q&A (también gated). Cero efecto.
- **El Q&A de Telegram existente sigue igual:** el router "publicar" es aditivo y PREVIO al path de Q&A; una pregunta que no sea exactamente "publicar" no se afecta.
- **S1:** `cfo/vigilante/` es ORQUESTACIÓN (no `cfo/calc/`) — puede importar servicios/modelos/telegram/audit. `test_s1_aislamiento.py` barre `cfo/calc/`, NO `cfo/vigilante/` (confirmar). No escribir la subcadena "motor" si algún archivo cayera bajo el barrido — pero no aplica aquí.
- **`ruff` limpio.** Gate = **gate-waiver + GO CEO** (NADA de Kimi; NUNCA simular).
- **Branch guard:** `git branch --show-current` == `feat/fabs-vigilante-paquete-lunes` antes de cada commit. Rama desde `main`.

### Firmas reales verificadas (reusar)
- `cfo.agente.servicio.consultar(pregunta: str, *, actor_id: str, cliente=None, historial=None) -> RespuestaCFO`. `RespuestaCFO`: `.texto`(sustituido), `.texto_crudo`(tokens), `.abstuvo`, `.motivo`, `.conceptos_usados: list[str]`, `.cifras: list[CifraPublicada]`. Nunca lanza (backstop). `cfo.agente.cliente.crear_cliente()` → `ClienteLLM | None`.
- `cfo.telegram.cliente.ClienteTelegram.enviar(chat_id: int, texto: str) -> None`; `crear_cliente_telegram() -> ClienteTelegramProto | None`.
- `cfo.telegram.repositorio.listar_vinculos() -> list[VinculoTelegram]` (`.telegram_id: int`, `.user_id: str`). `cfo.telegram.vinculos.resolver(telegram_id) -> str | None`.
- `cfo.telegram.webhook.procesar_update(update, *, cliente_telegram, cliente_llm=None)` — hoy: `_extraer` → `(update_id, telegram_id, chat_id, texto)`; `user_id = await vinculos.resolver(telegram_id)`; dedup; `resp = await servicio.consultar(texto, actor_id=user_id, ...)`; `enviar`. `from app.cfo import config` ya importado.
- `app.jobs.scheduler.build_scheduler()` → `AsyncIOScheduler(timezone="America/Bogota")` VACÍO (un `TODO` donde va el `add_job`). `ensure_worker_context(settings)` exige `settings.run_scheduler`.
- `audit.service.emit_audit(evento, entidad, entidad_id=None, actor_id=None, metadata=None) -> AuditLog`. `audit.events.AuditEvento` (StrEnum, hoy 66); `CATALOGO_EVENTOS = frozenset(e.value for e in AuditEvento)` (auto-derivado — agregar miembros al enum lo actualiza solo). Últimos: `cfo_vinculo_creado`/`cfo_vinculo_eliminado`.
- `cfo.config`: getters env (`cfo_enabled()`, `cfo_api_key()`, `telegram_bot_token()`). `core.time.now_bogota()`.
- Registro Beanie: `app/db/mongo.py::DOCUMENT_MODELS` (lista usada por `init_beanie_for`). `VinculoTelegram`/`HiloCFO` (colecciones `cfo_*`) son el molde del nuevo Document.

---

### Task 1: Cimiento — modelo + eventos + config

**Files:** Create `backend/app/cfo/vigilante/__init__.py`, `backend/app/cfo/vigilante/modelos.py` · Modify `backend/app/audit/events.py`, `backend/app/db/mongo.py`, `backend/app/cfo/config.py` · Test `backend/tests/cfo/vigilante/test_cimiento.py`, `backend/tests/test_audit_events.py` (si asevera conteo)

**Interfaces — Produces:**
- `PaqueteVigilante(Document)` (colección `cfo_paquetes_vigilante`): `semana: str`(único), `texto: str`, `texto_crudo: str`, `estado: str`, `generado_at: datetime`, `publicado_at: datetime | None = None`, `conceptos_usados: list[str]`.
- `AuditEvento.vigilante_paquete_generado = "vigilante.paquete.generado"`, `AuditEvento.vigilante_paquete_publicado = "vigilante.paquete.publicado"`.
- `cfo.config.vigilante_revisor_telegram_id() -> int | None`.

- [ ] **Step 1: failing test** `backend/tests/cfo/vigilante/test_cimiento.py`:

```python
import os
from datetime import datetime, timezone
import pytest
from app.audit.events import AuditEvento, CATALOGO_EVENTOS
from app.cfo import config
from app.cfo.vigilante.modelos import PaqueteVigilante

def test_eventos_vigilante_en_catalogo():
    assert AuditEvento("vigilante.paquete.generado") is AuditEvento.vigilante_paquete_generado
    assert "vigilante.paquete.publicado" in CATALOGO_EVENTOS

def test_config_revisor(monkeypatch):
    monkeypatch.delenv("VIGILANTE_REVISOR_TELEGRAM_ID", raising=False)
    assert config.vigilante_revisor_telegram_id() is None
    monkeypatch.setenv("VIGILANTE_REVISOR_TELEGRAM_ID", "12345")
    assert config.vigilante_revisor_telegram_id() == 12345

@pytest.mark.asyncio
async def test_paquete_persiste(db):   # `db` = harness Beanie (mongomock)
    pq = PaqueteVigilante(semana="2026-08-31", texto="hola", texto_crudo="[[x]]",
        estado="borrador", generado_at=datetime.now(timezone.utc), conceptos_usados=["caja_hoy"])
    await pq.insert()
    got = await PaqueteVigilante.find_one(PaqueteVigilante.semana == "2026-08-31")
    assert got is not None and got.estado == "borrador"
```

- [ ] **Step 2: Run → FAIL** — `cd backend && python -m pytest tests/cfo/vigilante/test_cimiento.py -v`.

- [ ] **Step 3: Implement**
  - `cfo/vigilante/__init__.py` vacío. `cfo/vigilante/modelos.py`:
    ```python
    from datetime import datetime
    from beanie import Document
    from pydantic import ConfigDict, Field

    CFO_PAQUETES_COLLECTION = "cfo_paquetes_vigilante"

    class PaqueteVigilante(Document):
        model_config = ConfigDict(strict=True, extra="forbid")
        semana: str  # 'YYYY-MM-DD' del lunes (idempotencia)
        texto: str
        texto_crudo: str
        estado: str  # 'borrador' | 'publicado'
        generado_at: datetime
        publicado_at: datetime | None = None
        conceptos_usados: list[str] = Field(default_factory=list)

        class Settings:
            name = CFO_PAQUETES_COLLECTION
            indexes = [__import__("pymongo").IndexModel([("semana", 1)], name="semana_unica", unique=True)]
    ```
    (Imitar cómo `cfo/telegram/modelos.py` declara `indexes`/`IndexModel` — usar el mismo estilo de import que ese archivo en vez del `__import__` inline si allí importan `IndexModel` de pymongo directamente.)
  - `audit/events.py`: tras el bloque CR-CFO-2, agregar:
    ```python
    # ── CR-CFO-3 (2) — FABS vigilante paquete lunes (GO CEO 2026-08-30) ──
    # Proactivo: `vigilante.paquete.generado` = el job armó el borrador semanal (metadata
    # {semana, abstuvo, conceptos_usados}); `vigilante.paquete.publicado` = el revisor lo
    # difundió al comité vía "publicar" (metadata {semana, n_destinatarios}). La generación
    # también emite cfo.consulta/cfo.respuesta (reusa consultar). Catálogo 66 -> 68.
    vigilante_paquete_generado = "vigilante.paquete.generado"
    vigilante_paquete_publicado = "vigilante.paquete.publicado"
    ```
    Si `tests/test_audit_events.py` asevera un conteo fijo (p. ej. `len(...) == 66`), actualizarlo a 68.
  - `db/mongo.py`: agregar `PaqueteVigilante` a `DOCUMENT_MODELS` (import + entrada en la lista). Confirmar que `tests/conftest.py`'s `init_beanie` usa `DOCUMENT_MODELS` (si usa una lista propia, agregarlo ahí también).
  - `cfo/config.py`: `def vigilante_revisor_telegram_id() -> int | None:` lee `VIGILANTE_REVISOR_TELEGRAM_ID` (env), devuelve `int(v)` si es un entero válido, None si ausente/vacío. (Patrón de `telegram_bot_token`.)

- [ ] **Step 4: Run → PASS** + `python -m pytest tests/audit tests/cfo -q` verde. `ruff` limpio. `git diff -- app/proyeccion/motor.py` vacío.
- [ ] **Step 5: Commit** — `feat(cfo): cimiento vigilante — PaqueteVigilante + eventos + config revisor`.

---

### Task 2: Generador + entrega del borrador — `cfo/vigilante/paquete.py`

**Files:** Create `backend/app/cfo/vigilante/paquete.py` · Test `backend/tests/cfo/vigilante/test_paquete.py`

**Interfaces:**
- Consumes: `servicio.consultar`, `cliente.crear_cliente`, `telegram.cliente.crear_cliente_telegram`, `PaqueteVigilante`, `emit_audit`/`AuditEvento`, `config`, `now_bogota`.
- Produces: `async def generar_y_entregar_paquete() -> PaqueteVigilante | None`.

- [ ] **Step 1: failing test** (monkeypatch los servicios en `app.cfo.vigilante.paquete`):

```python
# backend/tests/cfo/vigilante/test_paquete.py
from datetime import datetime, timezone
import pytest
from app.cfo.vigilante import paquete as P
from app.cfo.vigilante.modelos import PaqueteVigilante

class _Resp:
    def __init__(self, abstuvo=False, cifras=("x",)):
        self.texto="Caja hoy $10.000.000"; self.texto_crudo="Caja hoy [[caja_hoy]]"
        self.abstuvo=abstuvo; self.motivo=None; self.conceptos_usados=["caja_hoy"]; self.cifras=list(cifras)

@pytest.mark.asyncio
async def test_genera_guarda_audita_envia(db, monkeypatch):
    monkeypatch.setenv("VIGILANTE_REVISOR_TELEGRAM_ID", "999")
    async def fake_consultar(*a, **k): return _Resp()
    monkeypatch.setattr(P, "consultar", fake_consultar)
    monkeypatch.setattr(P, "crear_cliente", lambda: object())
    enviados = []
    class FakeTg:
        async def enviar(self, chat_id, texto): enviados.append((chat_id, texto))
    monkeypatch.setattr(P, "crear_cliente_telegram", lambda: FakeTg())
    pq = await P.generar_y_entregar_paquete()
    assert pq is not None and pq.estado == "borrador"
    assert await PaqueteVigilante.find_one(PaqueteVigilante.estado == "borrador") is not None
    assert enviados and enviados[0][0] == 999 and "Caja hoy $10.000.000" in enviados[0][1]
    # evento generado emitido (consultar via AuditLog):
    from app.domain.audit_log import AuditLog  # ajustar import real
    assert await AuditLog.find_one(AuditLog.evento == "vigilante.paquete.generado") is not None

@pytest.mark.asyncio
async def test_idempotente_una_por_semana(db, monkeypatch):
    monkeypatch.setattr(P, "consultar", lambda *a, **k: _aw(_Resp()))
    monkeypatch.setattr(P, "crear_cliente", lambda: object())
    monkeypatch.setattr(P, "crear_cliente_telegram", lambda: None)
    monkeypatch.delenv("VIGILANTE_REVISOR_TELEGRAM_ID", raising=False)
    a = await P.generar_y_entregar_paquete(); b = await P.generar_y_entregar_paquete()
    assert a is not None and b is None  # segunda misma semana: no duplica

@pytest.mark.asyncio
async def test_abstiene_sin_cifras_no_guarda(db, monkeypatch):
    async def fake(*a, **k): return _Resp(abstuvo=True, cifras=())
    monkeypatch.setattr(P, "consultar", fake)
    monkeypatch.setattr(P, "crear_cliente", lambda: object())
    monkeypatch.setattr(P, "crear_cliente_telegram", lambda: None)
    assert await P.generar_y_entregar_paquete() is None
    assert await PaqueteVigilante.find_one({}) is None
```
(`_aw` = coroutine helper; el implementer ajusta el import real de `AuditLog` — probablemente `app.audit.models`/`app.domain.audit_log`, confirmar.)

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** `paquete.py`:

```python
"""FABS · vigilante — genera el paquete semanal y lo entrega al revisor como borrador.
Reusa `servicio.consultar` (verifica + sustituye + audita); solo se guarda/difunde el
texto YA verificado. Fail-soft: un job proactivo no revienta el worker."""

import logging

from app.audit.events import AuditEvento
from app.audit.service import emit_audit
from app.cfo import config
from app.cfo.agente.cliente import crear_cliente
from app.cfo.agente.servicio import consultar
from app.cfo.telegram.cliente import crear_cliente_telegram
from app.cfo.vigilante.modelos import PaqueteVigilante
from app.core.time import now_bogota

logger = logging.getLogger(__name__)

_PROMPT_PAQUETE = (
    "Compón el paquete semanal del lunes para el CEO de RODDOS: la caja disponible "
    "hoy, el rumbo de la caja hacia el umbral, el IVA del cuatrimestre que viene, y "
    "cómo viene el gasto vs el mes pasado. Cita cada cifra con su token; si un dato "
    "no está disponible, omítelo con honestidad. Sé breve y claro."
)


async def generar_y_entregar_paquete() -> PaqueteVigilante | None:
    semana = now_bogota().date().isoformat()
    if await PaqueteVigilante.find_one(PaqueteVigilante.semana == semana):
        logger.info("paquete de la semana %s ya existe; no se regenera", semana)
        return None
    resp = await consultar(_PROMPT_PAQUETE, actor_id="vigilante", cliente=crear_cliente())
    if resp.abstuvo and not resp.cifras:
        logger.info("consultar abstuvo sin cifras; no se guarda borrador vacío")
        return None
    pq = PaqueteVigilante(
        semana=semana, texto=resp.texto, texto_crudo=resp.texto_crudo,
        estado="borrador", generado_at=now_bogota(),
        conceptos_usados=list(resp.conceptos_usados),
    )
    await pq.insert()
    await emit_audit(
        AuditEvento.vigilante_paquete_generado, entidad="vigilante", entidad_id=semana,
        actor_id="vigilante",
        metadata={"semana": semana, "abstuvo": resp.abstuvo, "conceptos_usados": list(resp.conceptos_usados)},
    )
    revisor = config.vigilante_revisor_telegram_id()
    if revisor is None:
        logger.warning("VIGILANTE_REVISOR_TELEGRAM_ID sin configurar; borrador no enviado")
        return pq
    cliente_tg = crear_cliente_telegram()
    if cliente_tg is not None:
        await cliente_tg.enviar(
            revisor,
            "📋 Borrador del paquete del lunes\n\n" + resp.texto +
            "\n\nRespondé 'publicar' para difundirlo al comité.",
        )
    return pq
```

- [ ] **Step 4: Run → PASS** + `python -m pytest tests/cfo -q` verde. `ruff` limpio.
- [ ] **Step 5: Commit** — `feat(cfo): generar_y_entregar_paquete (digest via consultar + borrador al revisor)`.

---

### Task 3: El job del cron (primer job del scheduler) — `app/jobs/scheduler.py`

**Files:** Modify `backend/app/jobs/scheduler.py` · Test `backend/tests/jobs/test_scheduler_vigilante.py`

**Interfaces:** `build_scheduler()` registra el job `vigilante_paquete_lunes` (cron lunes 7:00 America/Bogota). `_job_paquete_lunes` = wrapper (no-op si `CFO_ENABLED=false`).

- [ ] **Step 1: failing test**:

```python
# backend/tests/jobs/test_scheduler_vigilante.py
import pytest
from app.jobs import scheduler as S

def test_registra_job_paquete_lunes():
    sched = S.build_scheduler()
    job = sched.get_job("vigilante_paquete_lunes")
    assert job is not None
    f = {x.name: str(x) for x in job.trigger.fields}
    assert f["day_of_week"] == "mon" and f["hour"] == "7" and f["minute"] == "0"

@pytest.mark.asyncio
async def test_wrapper_noop_con_flag_off(monkeypatch):
    monkeypatch.setenv("CFO_ENABLED", "false")
    llamado = {"n": 0}
    import app.cfo.vigilante.paquete as P
    async def fake(): llamado["n"] += 1
    monkeypatch.setattr(P, "generar_y_entregar_paquete", fake)
    await S._job_paquete_lunes()
    assert llamado["n"] == 0
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** en `scheduler.py`: reemplazar el `TODO` de `build_scheduler` por el `add_job`, y agregar el wrapper:

```python
    scheduler.add_job(
        _job_paquete_lunes, "cron", day_of_week="mon", hour=7, minute=0,
        id="vigilante_paquete_lunes", coalesce=True, misfire_grace_time=3600,
        replace_existing=True,
    )
    return scheduler


async def _job_paquete_lunes() -> None:
    """Lunes 7:00 (America/Bogota). No-op si el flag está off; import perezoso para no
    acoplar el scheduler al dominio cfo en los tests del contrato del flag."""
    from app.cfo import config as cfo_config
    if not cfo_config.cfo_enabled():
        return
    from app.cfo.vigilante.paquete import generar_y_entregar_paquete
    try:
        await generar_y_entregar_paquete()
    except Exception:  # noqa: BLE001 — un job proactivo no revienta el worker
        logger.exception("fallo en el job del paquete del lunes")
```

- [ ] **Step 4: Run → PASS** + `python -m pytest tests/jobs -q` verde (`test_scheduler` existente sin romperse). `ruff` limpio.
- [ ] **Step 5: Commit** — `feat(jobs): primer job del scheduler — paquete del lunes 7:00 (vigilante)`.

---

### Task 4: Router de comando "publicar" + difusión — `cfo/telegram/webhook.py`

**Files:** Modify `backend/app/cfo/telegram/webhook.py` · Test `backend/tests/cfo/telegram/test_webhook_publicar.py`

**Interfaces:** en `procesar_update`, si `texto.strip().lower() == "publicar"` y `telegram_id == config.vigilante_revisor_telegram_id()` → difunde el último borrador a todos los vínculos, marca `publicado`, emite `vigilante.paquete.publicado`.

- [ ] **Step 1: failing test** (webhook con fakes; sembrar un borrador + vínculos):

```python
# backend/tests/cfo/telegram/test_webhook_publicar.py — imports del harness + fakes de webhook existentes
@pytest.mark.asyncio
async def test_revisor_publica_difunde_a_todos(db, monkeypatch):
    monkeypatch.setenv("VIGILANTE_REVISOR_TELEGRAM_ID", "999")
    # sembrar 2 vínculos (telegram_id 999 y 888) + un PaqueteVigilante borrador;
    # (usar el patrón de los tests de webhook existentes para vínculos + hilos)
    from app.cfo.vigilante.modelos import PaqueteVigilante
    from datetime import datetime, timezone
    await PaqueteVigilante(semana="2026-08-31", texto="EL PAQUETE", texto_crudo="[[x]]",
        estado="borrador", generado_at=datetime.now(timezone.utc), conceptos_usados=[]).insert()
    enviados = []
    class FakeTg:
        async def enviar(self, chat_id, texto): enviados.append((chat_id, texto))
    from app.cfo.telegram import webhook
    await webhook.procesar_update({"update_id":1,"message":{"from":{"id":999},"chat":{"id":999},"text":"publicar"}},
        cliente_telegram=FakeTg())
    destinos = {c for c,_ in enviados if _ == "EL PAQUETE"}
    assert destinos == {999, 888}          # difundido a todo el comité
    got = await PaqueteVigilante.find_one(PaqueteVigilante.semana=="2026-08-31")
    assert got.estado == "publicado"
    from app.domain.audit_log import AuditLog  # ajustar import real
    assert await AuditLog.find_one(AuditLog.evento=="vigilante.paquete.publicado") is not None

@pytest.mark.asyncio
async def test_publicar_sin_borrador_avisa(db, monkeypatch):
    monkeypatch.setenv("VIGILANTE_REVISOR_TELEGRAM_ID","999")
    # sembrar el vínculo 999; sin borradores
    enviados=[]
    class FakeTg:
        async def enviar(self, c, t): enviados.append((c,t))
    from app.cfo.telegram import webhook
    await webhook.procesar_update({"update_id":2,"message":{"from":{"id":999},"chat":{"id":999},"text":"publicar"}},
        cliente_telegram=FakeTg())
    assert any("no hay" in t.lower() for _,t in enviados)

@pytest.mark.asyncio
async def test_publicar_de_no_revisor_cae_al_qa(db, monkeypatch):
    monkeypatch.setenv("VIGILANTE_REVISOR_TELEGRAM_ID","999")
    # sembrar vínculo 888 (no revisor); patch servicio.consultar para detectar el Q&A
    ...  # assert que consultar fue llamado (cae al path normal), no la difusión
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** en `webhook.py`: importar `PaqueteVigilante`, `emit_audit`/`AuditEvento`, `now_bogota`. En `procesar_update`, tras el bloque de autorización (`if user_id is None: ... return`) y ANTES de `hilo = await repositorio.obtener_hilo(...)`:

```python
    if texto.strip().lower() == "publicar" and telegram_id == config.vigilante_revisor_telegram_id():
        await _publicar_paquete(chat_id, cliente_telegram)
        return
```
y el helper:
```python
async def _publicar_paquete(chat_id: int, cliente_telegram: ClienteTelegramProto) -> None:
    borradores = await (
        PaqueteVigilante.find(PaqueteVigilante.estado == "borrador")
        .sort(-PaqueteVigilante.generado_at).limit(1).to_list()
    )
    pq = borradores[0] if borradores else None
    if pq is None:
        await cliente_telegram.enviar(chat_id, "No hay un paquete pendiente para publicar.")
        return
    vinculos_all = await repositorio.listar_vinculos()
    for v in vinculos_all:
        await cliente_telegram.enviar(v.telegram_id, pq.texto)
    pq.estado = "publicado"
    pq.publicado_at = now_bogota()
    await pq.save()
    await emit_audit(
        AuditEvento.vigilante_paquete_publicado, entidad="vigilante", entidad_id=pq.semana,
        actor_id="vigilante", metadata={"semana": pq.semana, "n_destinatarios": len(vinculos_all)},
    )
    await cliente_telegram.enviar(chat_id, f"✅ Paquete publicado al comité ({len(vinculos_all)} destinatarios).")
```
(Se marca `publicado` DESPUÉS de difundir; `enviar` traga sus errores → el loop no revienta. Un mensaje que solo contiene "publicar" dentro de una frase NO matchea, por la comparación exacta del texto completo.)

- [ ] **Step 4: Run → PASS** + `python -m pytest tests/cfo -q` verde (el Q&A existente intacto). `ruff` limpio.
- [ ] **Step 5: Commit** — `feat(cfo): comando "publicar" en el webhook — difunde el paquete al comité + audita`.

---

### Task 5: Cierre — regresión, guardas, roadmap, pasos de ops

**Files:** Modify `docs/COMPAS_FABS_ROADMAP.md`, `planning/phases/fabs/GO-LIVE-VIGILANTE.md` (nuevo) · (verificación) toda la suite

- [ ] **Step 1: Regresión + guardas** (reportar salidas verbatim):
  - `cd backend && python -m pytest tests/cfo tests/jobs tests/audit -q`.
  - `python -m pytest tests/cfo/test_s1_aislamiento.py -q` verde (confirmar que su barrido NO cubre `cfo/vigilante/`, o que igual pasa).
  - `ruff check app/cfo/ app/jobs/scheduler.py app/audit/events.py app/db/mongo.py` + `ruff format --check` limpios.
  - `git diff <MERGE_BASE=origin/main>..HEAD -- backend/app/proyeccion/motor.py backend/app/presupuesto/motor.py` VACÍO.
  - **Guarda de catálogo:** `python -c "from app.audit.events import CATALOGO_EVENTOS; print(len(CATALOGO_EVENTOS))"` = 68; `AuditEvento('vigilante.paquete.generado')` y `.publicado` válidos.
  - **Guarda del contrato:** confirmar que el paquete se difunde SOLO desde `paquete.texto` (sustituido) y que el comando "publicar" NO llama a `consultar` (grep en el helper).
- [ ] **Step 2: Pasos de ops** — `planning/phases/fabs/GO-LIVE-VIGILANTE.md`: guía para el CEO (worker `compas-jobs` corriendo con `RUN_SCHEDULER=true`, y las env `CFO_ENABLED=true`, `ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN`, `VIGILANTE_REVISOR_TELEGRAM_ID`=telegram_id del CEO). Formato de pasos guiados (como el go-live de Telegram).
- [ ] **Step 3: Cierre roadmap** — `docs/COMPAS_FABS_ROADMAP.md`: vigilante pieza 1 (paquete del lunes) construida (registro fechado; job proactivo + draft→publicar; 2 eventos nuevos; gate-waiver + GO CEO; NADA de Kimi). NO tocar el `.xlsx` (lo hace el controlador post-SDD, cuidando el clobber). Commit: `feat(cfo): cierre vigilante paquete del lunes (A+B+C, gate-waiver GO CEO)`.

---

## Self-Review (autor del plan)

**1. Cobertura del spec:** §5.1 config→T1 · §5.2 modelo→T1 · §5.3 eventos→T1 · §5.4 generador→T2 · §5.5 job→T3 · §5.6 router publicar→T4 · §6 contrato→T1/T2 · §7 idempotencia→T2 (semana única) · §8 trampas (no difundir no-verificado→T4 grep; borrador vacío→T2; revisor no config→T2; comparación exacta→T4; job no revienta→T3; flag off→T3; catálogo→T1)→cubiertas · §9 abstención→T2 · §10 pruebas→cada task · §11 innegociables→Global+T5 · §12 ops→T5 · §13 sub-rebanadas→T1-2 / T3 / T4.

**2. Placeholders:** los `# ajustar import real de AuditLog` y "confirmar conftest DOCUMENT_MODELS" son verificaciones puntuales contra el repo (nombran el archivo), no lógica pendiente; el resto trae código real.

**3. Consistencia de tipos:** `PaqueteVigilante(semana,texto,texto_crudo,estado,generado_at,publicado_at,conceptos_usados)` (T1) usado idéntico en T2 (crea borrador) y T4 (publica). `generar_y_entregar_paquete() -> PaqueteVigilante|None` (T2) llamado por `_job_paquete_lunes` (T3). Eventos `vigilante.paquete.generado` (T2) / `.publicado` (T4) declarados en T1. `config.vigilante_revisor_telegram_id()` (T1) usado en T2 (envío) y T4 (autorización del comando).

---
*Vigilante pieza 1. Ejecutar por SDD. Gate-waiver + GO CEO (NADA de Kimi, NUNCA simular). `motor.py` intocable. Alerta por umbral y cierre mensual → piezas siguientes. Depende de ops (compas-jobs + env) para correr en vivo, no para mergear.*
