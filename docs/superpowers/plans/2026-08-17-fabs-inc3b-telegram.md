# FABS inc3 Pieza B — Canal Telegram + piloto Q&A · Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** FABS conversable por Telegram para el piloto (CEO/CGO/CFO), detrás del flag: webhook seguro + allowlist (endpoint admin) + hilos que guardan tokens (no valores) + respuesta del servicio de Pieza A por sendMessage.

**Architecture:** Módulo nuevo `app/cfo/telegram/` (cliente httpx saliente inyectable · Documents `cfo_*` vía repositorio S1 · webhook fail-closed · endpoint admin de vínculos). El servicio de Pieza A se extiende de forma ADITIVA (acepta `historial`, expone `texto_crudo`). Los hilos guardan el texto CRUDO del modelo (con `[[tokens]]`), nunca los valores sustituidos → la garantía anti-alucinación se mantiene turno a turno. Todo detrás de `CFO_ENABLED`; go-live fuera de la pieza.

**Tech Stack:** Python 3.12, FastAPI, Beanie/Motor, Pydantic strict, `httpx` (saliente, lazy), pytest. Todo con mocks (`ClienteTelegramFake` + `ClienteFake` de Anthropic) ⇒ CI verde sin tokens ni key.

**Spec:** `docs/superpowers/specs/2026-08-17-fabs-inc3b-telegram-design.md`

## Global Constraints

- **Dinero = Decimal, nunca float** (regla 1); montos como string; cero `float`.
- **Secretos solo por env** (regla 12): `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `ANTHROPIC_API_KEY` — jamás en repo ni en tests (los tests usan mocks/monkeypatch).
- **Aislamiento S1:** `app/cfo/telegram/**` escribe SOLO colecciones `cfo_*` (vía `repositorio.py`) e importa SOLO capa de servicios (`app.cfo.agente.servicio`, `app.audit.*`, `app.auth.*`, `app.core.*`) + `httpx`/`beanie`/`pydantic` — NUNCA `app.domain.*` ni el driver de Mongo directo. Se extiende el test S1 para escanear `cfo/telegram/`.
- **El núcleo de Pieza A NO cambia** (verificador/sustituidor/prompt intactos); el servicio se extiende ADITIVAMENTE (default `historial=None` ⇒ inc2 idéntico).
- **Los hilos guardan el texto CRUDO del modelo (con tokens), NUNCA los valores sustituidos** — invariante de seguridad.
- **Dedup por `update_id`** (B-1), no por texto; reintento → reenvía `ultimo_envio` (no silencioso, B-2).
- **Vínculo uno-a-uno** (único en `telegram_id` y en `user_id`, B-3).
- **Flag `CFO_ENABLED` apagado ⇒ COMPAS byte-idéntico** (router telegram ausente de `create_app`). `motor.py` cero diffs. `ruff` limpio.
- **Catálogo de auditoría cerrado** (regla 11): solo +2 (`cfo.vinculo_creado`/`cfo.vinculo_eliminado`), 64→66, con comentario-CR.
- **Branch guard (contención):** verificar `git branch --show-current` == `feat/fabs-inc3b-telegram` antes de cada commit; si no, STOP + BLOCKED.
- Rama base `main` (`f4d651b`+). Nombres de concepto de Pieza A: `caja_hoy`/`runway`/`iva_cuatrimestre`.

---

### Task 1: Config del canal + extensión aditiva del servicio (historial + texto_crudo)

**Files:**
- Modify: `backend/app/cfo/config.py`
- Modify: `backend/app/cfo/agente/modelos.py` (`RespuestaCFO` + `texto_crudo`)
- Modify: `backend/app/cfo/agente/servicio.py` (`consultar` acepta `historial`; expone `texto_crudo`)
- Test: `backend/tests/cfo/test_config.py`, `backend/tests/cfo/agente/test_servicio.py`

**Interfaces:**
- Produces: `config.telegram_bot_token() -> str|None`, `config.telegram_webhook_secret() -> str|None`, `config.cfo_hilo_ventana() -> int` (default 8). `RespuestaCFO.texto_crudo: str|None`. `consultar(pregunta, *, actor_id, cliente=None, historial: list[dict]|None=None) -> RespuestaCFO` — `historial` se antepone a los mensajes; `RespuestaCFO.texto_crudo` = el texto del modelo ANTES de sustituir (para guardar en el hilo).

- [ ] **Step 1: Write the failing tests**

```python
# en backend/tests/cfo/test_config.py — añadir
def test_telegram_config(monkeypatch):
    from app.cfo import config as c
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert c.telegram_bot_token() is None
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "botX")
    assert c.telegram_bot_token() == "botX"
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "sek")
    assert c.telegram_webhook_secret() == "sek"
    monkeypatch.delenv("CFO_HILO_VENTANA", raising=False)
    assert c.cfo_hilo_ventana() == 8
    monkeypatch.setenv("CFO_HILO_VENTANA", "4")
    assert c.cfo_hilo_ventana() == 4
```
```python
# en backend/tests/cfo/agente/test_servicio.py — añadir (reusar ClienteFake + _audit + fake_tool del archivo)
@pytest.mark.asyncio
async def test_consultar_usa_historial_y_expone_texto_crudo(monkeypatch, _audit):
    async def fake_tool(nombre):
        return _caja()  # helper existente/nuevo: ResultadoCFO caja_hoy disponible
    monkeypatch.setattr("app.cfo.agente.loop.ejecutar_tool", fake_tool)
    guiones = [
        RespuestaLLM("tool_use", [BloqueToolUse(id="t1", nombre="caja_disponible_hoy", input={})], 1, 1),
        RespuestaLLM("end_turn", [BloqueTexto(texto="Tu caja es [[caja_hoy]].")], 1, 1),
    ]
    fake = ClienteFake(guiones)
    historial = [{"role": "user", "content": "hola"}, {"role": "assistant", "content": "¿en qué te ayudo?"}]
    r = await srv.consultar("¿caja?", actor_id="u1", cliente=fake, historial=historial)
    # el historial se antepuso (el primer mensaje que vio el cliente lo incluye)
    assert fake.llamadas[0]["messages"][0]["content"] == "hola"
    # texto publicado = sustituido; texto_crudo = con token (para guardar en el hilo)
    assert "[[caja_hoy]]" not in r.texto and "$704.722.003" in r.texto
    assert r.texto_crudo == "Tu caja es [[caja_hoy]]."
```

- [ ] **Step 2: Run tests to verify they fail** — `cd backend && python -m pytest tests/cfo/test_config.py tests/cfo/agente/test_servicio.py -k "telegram or historial" -v` → FAIL.

- [ ] **Step 3: Implement**

En `config.py` (junto a los otros helpers):
```python
def telegram_bot_token() -> str | None:
    v = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    return v or None


def telegram_webhook_secret() -> str | None:
    v = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "").strip()
    return v or None


def cfo_hilo_ventana() -> int:
    return int(os.environ.get("CFO_HILO_VENTANA", "8"))
```
En `agente/modelos.py`, añadir a `RespuestaCFO` (tras `motivo`):
```python
    texto_crudo: str | None = None  # texto del modelo ANTES de sustituir (para el hilo)
```
En `agente/servicio.py`:
- Firma: `async def consultar(pregunta, *, actor_id, cliente=None, historial=None):`
- La construcción de mensajes de la 1ª conversación: `[*(historial or []), {"role": "user", "content": pregunta}]`.
- La construcción de mensajes del reintento: `[*(historial or []), {"role": "user", "content": pregunta}, {"role": "assistant", "content": res.texto}, {"role": "user", "content": correccion}]`.
- Antes de sustituir, capturar el crudo: `texto_crudo = texto_final` y luego `texto_final = sustituir_tokens(texto_final, res.resultados)`. En el `RespuestaCFO(...)` de éxito, pasar `texto_crudo=texto_crudo`.
- En `_abstencion(...)`, pasar `texto_crudo=_ABSTENCION` (o el texto de abstención) al construir `RespuestaCFO`.

- [ ] **Step 4: Run tests** → PASS. Confirmar que los tests EXISTENTES de servicio (sin historial) siguen verdes (default None ⇒ comportamiento idéntico). `python -m ruff check --fix` + format.

- [ ] **Step 5: Commit**
```bash
cd backend && git add app/cfo/config.py app/cfo/agente/modelos.py app/cfo/agente/servicio.py tests/cfo/test_config.py tests/cfo/agente/test_servicio.py
git commit -m "feat(cfo): config del canal + servicio acepta historial y expone texto_crudo (aditivo)"
```

---

### Task 2: CR-CFO-2 — eventos `cfo.vinculo_creado` / `cfo.vinculo_eliminado`

**Files:**
- Modify: `backend/app/audit/events.py`
- Create: `planning/phases/fabs/CR-CFO-2.md`
- Test: `backend/tests/test_audit_events.py`

**Interfaces:**
- Produces: `AuditEvento.cfo_vinculo_creado = "cfo.vinculo_creado"`, `AuditEvento.cfo_vinculo_eliminado = "cfo.vinculo_eliminado"`. Catálogo 64→66.

- [ ] **Step 1: Ajustar el test de completitud** — en `backend/tests/test_audit_events.py`, cambiar `== 64` (líneas ~23-24, DOS aserciones) a `== 66`, renombrar `test_catalogo_tiene_exactamente_64_eventos` → `..._66_eventos`, y añadir:
```python
    assert "cfo.vinculo_creado" in CATALOGO_EVENTOS
    assert "cfo.vinculo_eliminado" in CATALOGO_EVENTOS
```

- [ ] **Step 2: Run test** → FAIL (66≠64).

- [ ] **Step 3: Añadir los eventos** — al final de `class AuditEvento` en `events.py`, tras el bloque CR-CFO-1:
```python
    # ── CR-CFO-2 (2) — FABS inc3 Pieza B (canal Telegram, GO CEO 2026-08-17) ──
    # Alta/baja del vínculo telegram_id↔user_id (allowlist, solo admin). El Q&A por
    # Telegram REUSA cfo.consulta/cfo.respuesta con metadata.canal="telegram" — sin
    # eventos nuevos para eso. Catálogo 64 -> 66.
    cfo_vinculo_creado = "cfo.vinculo_creado"
    cfo_vinculo_eliminado = "cfo.vinculo_eliminado"
```
Escribir `planning/phases/fabs/CR-CFO-2.md` (los 2 eventos, metadata, por qué gate).

- [ ] **Step 4: Run tests + otros conteos** — `cd backend && grep -rn "== 64\|len(AuditEvento)" tests/` — si hay otro test con el conteo, actualizarlo. `python -m pytest tests/test_audit_events.py tests/test_audit_emit.py -v` → PASS.

- [ ] **Step 5: Commit**
```bash
cd backend && python -m ruff check --fix app/audit/events.py tests/test_audit_events.py
git add app/audit/events.py tests/test_audit_events.py ../planning/phases/fabs/CR-CFO-2.md
git commit -m "feat(cfo): CR-CFO-2 eventos cfo.vinculo_creado/eliminado (catalogo 64->66)"
```

---

### Task 3: Documents `cfo_*` (VinculoTelegram + HiloCFO) + registro + repositorio (write gate S1)

**Files:**
- Create: `backend/app/cfo/telegram/__init__.py` (vacío), `backend/app/cfo/telegram/modelos.py`, `backend/app/cfo/telegram/repositorio.py`
- Modify: `backend/app/domain/__init__.py` (registrar los 2 Documents)
- Test: `backend/tests/cfo/telegram/__init__.py` (vacío) + `backend/tests/cfo/telegram/test_repositorio.py`

**Interfaces:**
- Produces:
  - `VinculoTelegram(Document)` col `cfo_vinculos_telegram`: `telegram_id:int` (único), `user_id:str` (único), `creado_por:str`, `creado_at:datetime`.
  - `HiloCFO(Document)` col `cfo_hilos`: `user_id:str` (único), `turnos:list[dict]`, `ultimo_update_id:int|None`, `ultimo_envio:str|None`, `actualizado_at:datetime`.
  - `repositorio.py`: `async crear_vinculo(v)`, `async eliminar_vinculo(telegram_id)->bool`, `async resolver_usuario(telegram_id)->str|None`, `async listar_vinculos()->list[VinculoTelegram]`, `async obtener_hilo(user_id)->HiloCFO|None`, `async guardar_hilo(h)`. **Única puerta de escritura (S1).**

- [ ] **Step 1: Write the failing test** (usa Mongo real — marcar `requires_real_mongo`; la unicidad no la soporta mongomock)

```python
# backend/tests/cfo/telegram/test_repositorio.py
from datetime import datetime, timezone

import pytest

from app.cfo.telegram.modelos import HiloCFO, VinculoTelegram
from app.cfo.telegram import repositorio as repo


@pytest.mark.requires_real_mongo
@pytest.mark.asyncio
async def test_vinculo_unico_y_resolver(mongo_real):  # fixture del repo que inicia Beanie
    v = VinculoTelegram(telegram_id=111, user_id="u1", creado_por="admin",
                        creado_at=datetime.now(timezone.utc))
    await repo.crear_vinculo(v)
    assert await repo.resolver_usuario(111) == "u1"
    assert await repo.resolver_usuario(999) is None
    # unicidad: otro vínculo con el mismo telegram_id o user_id falla
    with pytest.raises(Exception):
        await repo.crear_vinculo(VinculoTelegram(telegram_id=111, user_id="u2",
            creado_por="admin", creado_at=datetime.now(timezone.utc)))


@pytest.mark.requires_real_mongo
@pytest.mark.asyncio
async def test_hilo_upsert(mongo_real):
    h = HiloCFO(user_id="u1", turnos=[{"rol": "user", "contenido": "q"}],
                ultimo_update_id=5, ultimo_envio="r", actualizado_at=datetime.now(timezone.utc))
    await repo.guardar_hilo(h)
    got = await repo.obtener_hilo("u1")
    assert got.ultimo_update_id == 5 and got.turnos[0]["contenido"] == "q"
```
(Seguir el patrón de fixture de Mongo real del repo — buscar `requires_real_mongo` en `tests/` y reusar cómo inicializan Beanie con `DOMAIN_DOCUMENTS`.)

- [ ] **Step 2: Run test** → FAIL (módulos inexistentes).

- [ ] **Step 3: Implement**

```python
# backend/app/cfo/telegram/modelos.py
"""FABS · Documents del canal Telegram. Colecciones cfo_* (S1). Vínculo uno-a-uno
(único en telegram_id y user_id, B-3). El hilo guarda el texto CRUDO del modelo
(con [[tokens]], NUNCA valores) para preservar la garantía de Pieza A entre turnos."""

from datetime import datetime

import pymongo
from beanie import Document
from pydantic import ConfigDict, Field

CFO_VINCULOS_COLLECTION = "cfo_vinculos_telegram"
CFO_HILOS_COLLECTION = "cfo_hilos"


class VinculoTelegram(Document):
    model_config = ConfigDict(strict=True, extra="forbid")

    telegram_id: int
    user_id: str
    creado_por: str
    creado_at: datetime

    class Settings:
        name = CFO_VINCULOS_COLLECTION
        indexes = [
            pymongo.IndexModel([("telegram_id", 1)], unique=True, name="telegram_id_unico"),
            pymongo.IndexModel([("user_id", 1)], unique=True, name="user_id_unico"),
        ]


class HiloCFO(Document):
    model_config = ConfigDict(strict=True, extra="forbid")

    user_id: str
    turnos: list[dict] = Field(default_factory=list)
    ultimo_update_id: int | None = None
    ultimo_envio: str | None = None
    actualizado_at: datetime

    class Settings:
        name = CFO_HILOS_COLLECTION
        indexes = [
            pymongo.IndexModel([("user_id", 1)], unique=True, name="user_id_unico"),
        ]
```
(Si el repo ya tiene un patrón distinto para índices únicos en Beanie — p.ej. aplicarlos en el init de Mongo como `AUTH_INDEXES` — SEGUIRLO en vez de `Settings.indexes`; lo que importa es que el test de unicidad pase contra Mongo real.)

```python
# backend/app/cfo/telegram/repositorio.py
"""FABS · única puerta de escritura/lectura del canal Telegram. SOLO colecciones
cfo_* (S1: ninguna otra subruta de cfo/telegram toca el driver de Mongo)."""

from app.cfo.telegram.modelos import HiloCFO, VinculoTelegram


async def crear_vinculo(v: VinculoTelegram) -> None:
    await v.insert()  # lanza DuplicateKeyError si telegram_id o user_id ya existen


async def eliminar_vinculo(telegram_id: int) -> bool:
    v = await VinculoTelegram.find_one(VinculoTelegram.telegram_id == telegram_id)
    if v is None:
        return False
    await v.delete()
    return True


async def resolver_usuario(telegram_id: int) -> str | None:
    v = await VinculoTelegram.find_one(VinculoTelegram.telegram_id == telegram_id)
    return v.user_id if v is not None else None


async def listar_vinculos() -> list[VinculoTelegram]:
    return await VinculoTelegram.find_all().to_list()


async def obtener_hilo(user_id: str) -> HiloCFO | None:
    return await HiloCFO.find_one(HiloCFO.user_id == user_id)


async def guardar_hilo(h: HiloCFO) -> None:
    existe = await HiloCFO.find_one(HiloCFO.user_id == h.user_id)
    if existe is None:
        await h.insert()
    else:
        existe.turnos = h.turnos
        existe.ultimo_update_id = h.ultimo_update_id
        existe.ultimo_envio = h.ultimo_envio
        existe.actualizado_at = h.actualizado_at
        await existe.save()
```
En `backend/app/domain/__init__.py`: importar `VinculoTelegram, HiloCFO` y añadirlos a `DOMAIN_DOCUMENTS` + `__all__`. Si hay un test que fija `len(DOMAIN_DOCUMENTS)`, actualizarlo (+2).

- [ ] **Step 4: Run tests** — `cd backend && python -m pytest tests/cfo/telegram/test_repositorio.py -m requires_real_mongo -v` (requiere `COMPAS_TEST_MONGO_URI`; ver `docs`/memoria del repo). Si no hay Mongo real disponible en el entorno, correr al menos la importación + `python -m pytest tests/ -k domain` para el registro. `ruff` limpio.

- [ ] **Step 5: Commit**
```bash
cd backend && git add app/cfo/telegram/__init__.py app/cfo/telegram/modelos.py app/cfo/telegram/repositorio.py app/domain/__init__.py tests/cfo/telegram/
git commit -m "feat(cfo): Documents cfo_vinculos_telegram + cfo_hilos + repositorio (write gate S1)"
```

---

### Task 4: Cliente Telegram (httpx saliente, lazy, inyectable) + fake

**Files:**
- Create: `backend/app/cfo/telegram/cliente.py`
- Create: `backend/tests/cfo/telegram/fakes.py`
- Test: `backend/tests/cfo/telegram/test_cliente.py`

**Interfaces:**
- Produces: `class ClienteTelegram` (import perezoso de `httpx`; `async def enviar(self, chat_id:int, texto:str) -> None`); `class ClienteTelegramProto(Protocol)`; `def crear_cliente_telegram() -> ClienteTelegramProto | None` (None sin `TELEGRAM_BOT_TOKEN`). En `fakes.py`: `class ClienteTelegramFake` con `enviados: list[tuple[int,str]]`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/cfo/telegram/test_cliente.py
from app.cfo.telegram import cliente as cli


def test_crear_cliente_none_sin_token(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert cli.crear_cliente_telegram() is None


def test_crear_cliente_instancia_con_token(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "botX")
    assert isinstance(cli.crear_cliente_telegram(), cli.ClienteTelegram)
```
```python
# backend/tests/cfo/telegram/fakes.py
class ClienteTelegramFake:
    def __init__(self):
        self.enviados: list[tuple[int, str]] = []

    async def enviar(self, chat_id: int, texto: str) -> None:
        self.enviados.append((chat_id, texto))
```

- [ ] **Step 2: Run test** → FAIL.

- [ ] **Step 3: Implement**

```python
# backend/app/cfo/telegram/cliente.py
"""FABS · cliente Telegram SALIENTE (sendMessage). httpx con import PEREZOSO; sin
TELEGRAM_BOT_TOKEN ⇒ crear_cliente_telegram()=None. Los errores se loguean, no
revientan el webhook (una respuesta que no sale no debe tumbar el 200 a Telegram)."""

import logging
from typing import Protocol

from app.cfo import config

logger = logging.getLogger(__name__)

_API = "https://api.telegram.org/bot{token}/sendMessage"


class ClienteTelegramProto(Protocol):
    async def enviar(self, chat_id: int, texto: str) -> None: ...


class ClienteTelegram:
    def __init__(self, token: str, timeout_s: float = 10.0):
        self._token = token
        self._timeout = timeout_s

    async def enviar(self, chat_id: int, texto: str) -> None:
        import httpx  # import perezoso

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as c:
                r = await c.post(
                    _API.format(token=self._token),
                    json={"chat_id": chat_id, "text": texto},
                )
                r.raise_for_status()
        except Exception:  # noqa: BLE001 — no reventar el webhook
            logger.exception("fallo al enviar a Telegram chat=%s", chat_id)


def crear_cliente_telegram() -> ClienteTelegramProto | None:
    token = config.telegram_bot_token()
    return ClienteTelegram(token) if token else None
```

- [ ] **Step 4: Run test** → PASS. `ruff` limpio.

- [ ] **Step 5: Commit**
```bash
cd backend && git add app/cfo/telegram/cliente.py tests/cfo/telegram/test_cliente.py tests/cfo/telegram/fakes.py
git commit -m "feat(cfo): cliente Telegram saliente (httpx lazy) + fake"
```

---

### Task 5: Lógica de vínculos + hilos (resolver/alta/baja; cargar historial/guardar turno/dedup update_id)

**Files:**
- Create: `backend/app/cfo/telegram/vinculos.py`, `backend/app/cfo/telegram/hilos.py`
- Test: `backend/tests/cfo/telegram/test_vinculos.py`, `backend/tests/cfo/telegram/test_hilos.py`

**Interfaces:**
- Consumes: `repositorio` (Task 3), `config.cfo_hilo_ventana` (Task 1).
- Produces:
  - `vinculos.py`: `async vincular(telegram_id, user_id, admin_id) -> None` (valida + crea + audita `cfo.vinculo_creado`); `async desvincular(telegram_id, admin_id) -> bool` (audita `cfo.vinculo_eliminado`); `async resolver(telegram_id) -> str|None`.
  - `hilos.py`: `def historial_para_loop(hilo: HiloCFO|None, ventana:int) -> list[dict]` (últimos `ventana` turnos como mensajes `{role, content}`); `async registrar_turno(user_id, pregunta, texto_crudo, update_id, envio)` (append + trim + guarda `ultimo_update_id`/`ultimo_envio`); `def es_reintento(hilo, update_id) -> bool`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/cfo/telegram/test_hilos.py
from datetime import datetime, timezone

from app.cfo.telegram import hilos
from app.cfo.telegram.modelos import HiloCFO


def _hilo(turnos, uid=None):
    return HiloCFO(user_id="u1", turnos=turnos, ultimo_update_id=uid,
                   ultimo_envio="prev", actualizado_at=datetime.now(timezone.utc))


def test_historial_toma_ultimos_n():
    turnos = [{"rol": "user", "contenido": f"q{i}"} for i in range(20)]
    msgs = hilos.historial_para_loop(_hilo(turnos), ventana=4)
    assert len(msgs) == 4
    assert msgs[-1] == {"role": "user", "content": "q19"}
    # 'rol' -> 'role', 'contenido' -> 'content'
    assert set(msgs[0].keys()) == {"role", "content"}


def test_historial_none_es_vacio():
    assert hilos.historial_para_loop(None, ventana=8) == []


def test_es_reintento_por_update_id():
    assert hilos.es_reintento(_hilo([], uid=42), 42) is True
    assert hilos.es_reintento(_hilo([], uid=42), 43) is False
    assert hilos.es_reintento(None, 42) is False
```
```python
# backend/tests/cfo/telegram/test_vinculos.py
import pytest
from app.cfo.telegram import vinculos


@pytest.mark.asyncio
async def test_vincular_audita(monkeypatch):
    creados = []
    async def fake_crear(v): creados.append(v)
    eventos = []
    async def fake_emit(evento, entidad, entidad_id=None, actor_id=None, metadata=None):
        eventos.append((str(evento), metadata))
    monkeypatch.setattr("app.cfo.telegram.vinculos.repositorio.crear_vinculo", fake_crear)
    monkeypatch.setattr("app.cfo.telegram.vinculos.emit_audit", fake_emit)
    await vinculos.vincular(111, "u1", admin_id="admin")
    assert creados[0].telegram_id == 111 and creados[0].user_id == "u1"
    assert eventos[0][0] == "cfo.vinculo_creado"
```

- [ ] **Step 2: Run tests** → FAIL.

- [ ] **Step 3: Implement**

```python
# backend/app/cfo/telegram/hilos.py
"""FABS · lógica de hilos. El historial que se re-alimenta al modelo son los turnos
CRUDOS (con [[tokens]]), NUNCA valores — así la garantía de Pieza A se mantiene entre
turnos. Ventana acotada (costo); el hilo persiste (sin TTL naïve)."""

from datetime import datetime

from app.cfo.telegram.modelos import HiloCFO
from app.cfo.telegram import repositorio
from app.core.time import now_utc

_MAX_TURNOS = 40  # se persiste hasta esto; se re-alimenta solo la ventana


def historial_para_loop(hilo: HiloCFO | None, ventana: int) -> list[dict]:
    if hilo is None or not hilo.turnos:
        return []
    ult = hilo.turnos[-ventana:]
    return [{"role": t["rol"], "content": t["contenido"]} for t in ult]


def es_reintento(hilo: HiloCFO | None, update_id: int) -> bool:
    return hilo is not None and hilo.ultimo_update_id == update_id


async def registrar_turno(
    user_id: str, pregunta: str, texto_crudo: str, update_id: int, envio: str
) -> None:
    hilo = await repositorio.obtener_hilo(user_id)
    turnos = (hilo.turnos if hilo else []) + [
        {"rol": "user", "contenido": pregunta},
        {"rol": "assistant", "contenido": texto_crudo},
    ]
    turnos = turnos[-_MAX_TURNOS:]
    nuevo = HiloCFO(
        user_id=user_id, turnos=turnos, ultimo_update_id=update_id,
        ultimo_envio=envio, actualizado_at=now_utc(),
    )
    await repositorio.guardar_hilo(nuevo)
```
```python
# backend/app/cfo/telegram/vinculos.py
"""FABS · lógica de la allowlist (alta/baja/resolución) con auditoría CR-CFO-2."""

from app.audit.events import AuditEvento
from app.audit.service import emit_audit
from app.cfo.telegram import repositorio
from app.cfo.telegram.modelos import VinculoTelegram
from app.core.time import now_utc


async def vincular(telegram_id: int, user_id: str, admin_id: str) -> None:
    v = VinculoTelegram(
        telegram_id=telegram_id, user_id=user_id, creado_por=admin_id, creado_at=now_utc()
    )
    await repositorio.crear_vinculo(v)  # DuplicateKeyError si ya existe (uno-a-uno)
    await emit_audit(
        AuditEvento.cfo_vinculo_creado, entidad="cfo", actor_id=admin_id,
        metadata={"telegram_id": telegram_id, "user_id": user_id},
    )


async def desvincular(telegram_id: int, admin_id: str) -> bool:
    ok = await repositorio.eliminar_vinculo(telegram_id)
    if ok:
        await emit_audit(
            AuditEvento.cfo_vinculo_eliminado, entidad="cfo", actor_id=admin_id,
            metadata={"telegram_id": telegram_id},
        )
    return ok


async def resolver(telegram_id: int) -> str | None:
    return await repositorio.resolver_usuario(telegram_id)
```
(`vincular` no envuelve `emit_audit` en fail-soft: el alta de vínculo es una operación de estado admin, no una lectura — si la auditoría falla debe propagar, como el resto de operaciones de estado del ciclo. El Q&A sí es fail-soft, en el servicio.)

- [ ] **Step 4: Run tests** → PASS. `ruff` limpio.

- [ ] **Step 5: Commit**
```bash
cd backend && git add app/cfo/telegram/vinculos.py app/cfo/telegram/hilos.py tests/cfo/telegram/test_vinculos.py tests/cfo/telegram/test_hilos.py
git commit -m "feat(cfo): logica de vinculos (audit) + hilos (historial crudo, dedup update_id)"
```

---

### Task 6: Webhook + router (admin de vínculos + webhook) + registro en main (doble barrera)

**Files:**
- Create: `backend/app/cfo/telegram/webhook.py`, `backend/app/cfo/telegram/router.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/cfo/telegram/test_webhook.py`, `backend/tests/cfo/telegram/test_router.py`

**Interfaces:**
- Consumes: `vinculos`/`hilos` (Task 5), `cliente` (Task 4), `servicio.consultar` (Task 1), `config.telegram_webhook_secret`/`cfo_hilo_ventana`/`cfo_enabled`, `require_role(Role.admin)`.
- Produces: `webhook.py`: `async procesar_update(update: dict, *, cliente_telegram, cliente_llm=None) -> None` (la lógica pura, testeable con fakes). `router.py`: `router` con `POST /api/v1/cfo/telegram/webhook`, `POST/GET/DELETE /api/v1/cfo/telegram/vinculos`. Montado en `create_app` solo si `cfo_enabled()`.

- [ ] **Step 1: Write the failing test** (webhook con fakes)

```python
# backend/tests/cfo/telegram/test_webhook.py
import pytest

from app.cfo.telegram import webhook
from app.cfo.telegram.fakes import ClienteTelegramFake


@pytest.mark.asyncio
async def test_no_vinculado_rehusa_sin_llamar_servicio(monkeypatch):
    async def fake_resolver(tid): return None
    monkeypatch.setattr("app.cfo.telegram.webhook.vinculos.resolver", fake_resolver)
    llamado = False
    async def fake_consultar(*a, **k):
        nonlocal llamado; llamado = True
    monkeypatch.setattr("app.cfo.telegram.webhook.servicio.consultar", fake_consultar)
    tg = ClienteTelegramFake()
    update = {"update_id": 1, "message": {"from": {"id": 111}, "chat": {"id": 111}, "text": "hola"}}
    await webhook.procesar_update(update, cliente_telegram=tg)
    assert llamado is False
    assert "111" in tg.enviados[0][1]  # le dice su telegram_id


@pytest.mark.asyncio
async def test_vinculado_responde_y_guarda_hilo_crudo(monkeypatch):
    async def fake_resolver(tid): return "u1"
    monkeypatch.setattr("app.cfo.telegram.webhook.vinculos.resolver", fake_resolver)
    async def fake_obtener_hilo(uid): return None
    monkeypatch.setattr("app.cfo.telegram.webhook.repositorio.obtener_hilo", fake_obtener_hilo)
    from app.cfo.agente.modelos import RespuestaCFO, UsoLLM
    async def fake_consultar(pregunta, *, actor_id, cliente=None, historial=None):
        return RespuestaCFO(texto="Tu caja es $704.722.003.", abstuvo=False,
            texto_crudo="Tu caja es [[caja_hoy]].", uso=UsoLLM(modelo="m", tokens_in=1, tokens_out=1, iteraciones=1))
    monkeypatch.setattr("app.cfo.telegram.webhook.servicio.consultar", fake_consultar)
    turnos_guardados = {}
    async def fake_registrar(user_id, pregunta, texto_crudo, update_id, envio):
        turnos_guardados.update(texto_crudo=texto_crudo, envio=envio)
    monkeypatch.setattr("app.cfo.telegram.webhook.hilos.registrar_turno", fake_registrar)
    tg = ClienteTelegramFake()
    update = {"update_id": 7, "message": {"from": {"id": 111}, "chat": {"id": 111}, "text": "¿caja?"}}
    await webhook.procesar_update(update, cliente_telegram=tg)
    assert "$704.722.003" in tg.enviados[0][1]        # el usuario ve el valor
    assert turnos_guardados["texto_crudo"] == "Tu caja es [[caja_hoy]]."  # el hilo guarda el token
```

- [ ] **Step 2: Run test** → FAIL.

- [ ] **Step 3: Implement**

```python
# backend/app/cfo/telegram/webhook.py
"""FABS · lógica del webhook (pura, testeable con fakes). Reactivo: responde a quien
escribe. No-vinculado ⇒ rehúsa sin llamar al servicio. Dedup por update_id (reenvía la
respuesta previa). El hilo guarda el texto CRUDO (tokens), lo que ve el usuario es el
sustituido."""

import logging

from app.cfo import config
from app.cfo.agente import servicio
from app.cfo.agente.cliente import crear_cliente as crear_cliente_llm
from app.cfo.telegram import hilos, repositorio, vinculos
from app.cfo.telegram.cliente import ClienteTelegramProto

logger = logging.getLogger(__name__)


def _formatear(resp) -> str:
    if resp.abstuvo or not resp.cifras:
        return resp.texto
    lineas = "\n".join(
        f"• {c.valor} {c.unidad} — {c.evidencia.fuente} ({c.evidencia.ref})"
        for c in resp.cifras
    )
    return f"{resp.texto}\n\nCifras (con su fuente):\n{lineas}"


async def procesar_update(
    update: dict, *, cliente_telegram: ClienteTelegramProto, cliente_llm=None
) -> None:
    msg = update.get("message")
    if not msg or not msg.get("text"):
        return  # updates no-texto se ignoran
    update_id = update["update_id"]
    telegram_id = msg["from"]["id"]
    chat_id = msg["chat"]["id"]
    texto = msg["text"]

    user_id = await vinculos.resolver(telegram_id)
    if user_id is None:
        await cliente_telegram.enviar(
            chat_id,
            f"No estás autorizado para usar FABS. Tu ID de Telegram es {telegram_id} — "
            "pídele al administrador que te vincule.",
        )
        return

    hilo = await repositorio.obtener_hilo(user_id)
    if hilos.es_reintento(hilo, update_id):
        # reintento de Telegram: reenvía la respuesta previa (B-1/B-2, no silencioso)
        if hilo.ultimo_envio:
            await cliente_telegram.enviar(chat_id, hilo.ultimo_envio)
        return

    historial = hilos.historial_para_loop(hilo, config.cfo_hilo_ventana())
    resp = await servicio.consultar(
        texto, actor_id=user_id, cliente=cliente_llm or crear_cliente_llm(),
        historial=historial,
    )
    envio = _formatear(resp)
    await hilos.registrar_turno(user_id, texto, resp.texto_crudo or resp.texto, update_id, envio)
    await cliente_telegram.enviar(chat_id, envio)
```
```python
# backend/app/cfo/telegram/router.py
"""FABS · rutas del canal Telegram (inc3 Pieza B). Doble barrera: montadas solo si
CFO_ENABLED (main) + guard 404. Webhook verifica el secret token. Vínculos = admin."""

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from app.auth.deps import require_role
from app.auth.models import User
from app.auth.roles import Role
from app.cfo.config import cfo_enabled, telegram_webhook_secret
from app.cfo.telegram import repositorio, vinculos, webhook
from app.cfo.telegram.cliente import crear_cliente_telegram

router = APIRouter(prefix="/api/v1/cfo/telegram", tags=["cfo-telegram"])


class VinculoBody(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    telegram_id: int
    user_id: str


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    if not cfo_enabled():
        raise HTTPException(404, "No encontrado.")
    secret = telegram_webhook_secret()
    if not secret or x_telegram_bot_api_secret_token != secret:
        raise HTTPException(403, "Prohibido.")
    cli = crear_cliente_telegram()
    if cli is None:
        raise HTTPException(503, "Canal no configurado.")
    update = await request.json()
    await webhook.procesar_update(update, cliente_telegram=cli)
    return {"ok": True}


@router.post("/vinculos")
async def crear(body: VinculoBody, admin: User = Depends(require_role(Role.admin))):
    if not cfo_enabled():
        raise HTTPException(404, "No encontrado.")
    try:
        await vinculos.vincular(body.telegram_id, body.user_id, admin_id=str(admin.id))
    except Exception as e:  # noqa: BLE001 — duplicado (uno-a-uno)
        raise HTTPException(409, "telegram_id o user_id ya vinculado.") from e
    return {"ok": True}


@router.get("/vinculos")
async def listar(admin: User = Depends(require_role(Role.admin))):
    if not cfo_enabled():
        raise HTTPException(404, "No encontrado.")
    vs = await repositorio.listar_vinculos()
    return [{"telegram_id": v.telegram_id, "user_id": v.user_id} for v in vs]


@router.delete("/vinculos/{telegram_id}")
async def borrar(telegram_id: int, admin: User = Depends(require_role(Role.admin))):
    if not cfo_enabled():
        raise HTTPException(404, "No encontrado.")
    ok = await vinculos.desvincular(telegram_id, admin_id=str(admin.id))
    if not ok:
        raise HTTPException(404, "Vínculo no encontrado.")
    return {"ok": True}
```
En `main.py`, dentro del bloque `if cfo_enabled():` (junto al `cfo_router`):
```python
        from app.cfo.telegram.router import router as cfo_telegram_router
        app.include_router(cfo_telegram_router)
```

- [ ] **Step 4: Router test (flag on, fakes)** — seguir el patrón real de tests de router del repo (auth override) para: secret inválido → 403; flag-off → ruta ausente; admin crea vínculo. Correr `cd backend && python -m pytest tests/cfo/telegram/ -v`. `ruff` limpio.

- [ ] **Step 5: Commit**
```bash
cd backend && git add app/cfo/telegram/webhook.py app/cfo/telegram/router.py app/main.py tests/cfo/telegram/test_webhook.py tests/cfo/telegram/test_router.py
git commit -m "feat(cfo): webhook Telegram (fail-closed, dedup update_id) + endpoint admin de vinculos + registro tras flag"
```

---

### Task 7: Cierre — flag-off idéntico + S1 cubre telegram/ + regresión

**Files:**
- Modify: `backend/tests/cfo/test_s1_aislamiento.py` (añadir `cfo/telegram`)
- Verificación/regresión.

- [ ] **Step 1: S1 cubre `cfo/telegram/`** — añadir `CFO / "telegram"` a `LOGICA` en `test_s1_aislamiento.py`; correr `cd backend && python -m pytest tests/cfo/test_s1_aislamiento.py -v`. Las importaciones de `telegram/` (servicio, audit, auth, core, httpx, beanie) NO son `app.domain.*` ni driver → verde. Si algo importa prohibido, corregir el import (no el test). OJO `pymongo.IndexModel` en `modelos.py`: `pymongo` NO es el driver async (`motor`/`AsyncIOMotor`) — pero el regex `PROHIBIDO_DRIVER` incluye el substring `motor`; confirmar que no aparezca "motor" en telegram/; si `modelos.py` dispara un falso positivo por algún string, exceptuar `modelos.py` como se hace con `goldens/modelo.py`.

- [ ] **Step 2: Flag-off = router ausente** — test: `create_app()` con `CFO_ENABLED` ausente ⇒ `"/api/v1/cfo/telegram/webhook"` NO en las rutas.

- [ ] **Step 3: motor 0 diffs + cero float** —
```bash
cd backend && git diff <MERGE_BASE>..HEAD -- app/proyeccion/motor.py   # vacío
cd backend && grep -rn "float(" app/cfo/telegram/ || echo "sin float: OK"
```

- [ ] **Step 4: Regresión + ruff** — `cd backend && python -m ruff check app/cfo/` y `python -m pytest -q` (los `requires_real_mongo` del repositorio se saltan sin Mongo real; el resto verde). Reportar la línea exacta pass/skip/fail.

- [ ] **Step 5: Commit (si hubo fixes) + roadmap** — actualizar `docs/COMPAS_FABS_ROADMAP.md` (cierre de Pieza B). El paquete Kimi `INC3B-I` (con el diff COMPLETO embebido en EVIDENCIA) lo arma el controlador post-SDD.

---

## Self-Review (autor del plan)

**1. Cobertura del spec:** §3.1 cliente→T4 · §3.2 allowlist+admin→T3+T6 · §3.3 hilos (tokens, dedup, ventana)→T3+T5 · §3.4 servicio aditivo→T1 · §3.5 webhook→T6 · §4 config→T1 · §5 CR-CFO-2→T2 · §6 seguridad→T6 (secret/allowlist) · §7 flag/tests→T7 · DoD B-1/B-2/B-3→T5/T6/T3.

**2. Placeholders:** los tests traen código real; los puntos "seguir patrón del repo" (índices únicos Beanie, fixture de Mongo real, auth override de router) son específicos del harness — documentados, con el test verificando el comportamiento, no lógica pendiente.

**3. Consistencia de tipos:** `consultar(...historial=)`/`RespuestaCFO.texto_crudo` (T1) usados en webhook (T6); `VinculoTelegram`/`HiloCFO`/`repositorio.*` (T3) en vinculos/hilos (T5) y webhook (T6); `ClienteTelegramProto`/`crear_cliente_telegram` (T4) en webhook/router (T6); `AuditEvento.cfo_vinculo_*` (T2) en vinculos (T5).

---
*Pieza B de inc3. Ejecutar por SDD. B NO mergea hasta A-retro ≥9 + B-código ≥9 (decisión CEO/gobernanza Kimi). Go-live (§8 del spec) tras el gate de código + decisión del CEO. Ante conflicto de alcance mandan `COMPAS_NORTE.md`, `CLAUDE.md`, el roadmap de FABS y el spec de Pieza B.*
