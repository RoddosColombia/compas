# FABS · Vigilante — Alerta por umbral de caja · Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** FABS vigila la caja a diario y avisa (borrador→publicar) cuando el piso proyectado o el disponible real cruzan los umbrales editables ya existentes.

**Architecture:** 2º job del scheduler → evaluador de disparadores (orquestación en `cfo/vigilante`, lee servicios; S1 intacto) → texto DETERMINISTA (plantilla + cifras COMPAS citadas por token + verificador) → `AvisoVigilante(tipo='alerta_caja')` borrador al revisor → `publicar alerta` difunde al comité. Reusa el patrón del paquete del lunes.

**Tech Stack:** FastAPI + Beanie/Motor + MongoDB, Pydantic strict, APScheduler, Telegram (fakes en test). Tests: pytest + mongomock-motor.

**Spec:** `docs/superpowers/specs/2026-08-30-fabs-vigilante-alerta-caja-design.md` (léelo junto a este plan).

## Global Constraints

- **Dinero = `Decimal`** (COP), montos como string en la frontera; comparaciones de umbral con `Decimal`; formateo por `conceptos.formatear` (es-CO). NUNCA float sobre dinero.
- **TZ única** `America/Bogota`: `now_bogota()` / `today_bogota()`. `periodo` y timestamps TZ-aware.
- **Pydantic `strict=True, extra="forbid"`** en todo modelo nuevo.
- **`app/proyeccion/motor.py` y `app/presupuesto/motor.py`: 0 diffs** vs `origin/main` (la alerta solo LEE).
- **S1:** el código nuevo de la alerta vive en `cfo/vigilante/` (orquestación). `cfo/calc/**` NO se toca; `tests/cfo/test_s1_aislamiento.py` sigue verde.
- **Catálogo de auditoría cerrado** (regla 11): exactamente **+2** eventos declarados (`vigilante.alerta.generada`, `vigilante.alerta.publicada`), catálogo 68 → **70**.
- **Scheduler solo en el worker** (regla 6); job idempotente; no-op si `CFO_ENABLED` off.
- **Auditoría del vigilante = SOFT** (try/except + logger): un proactivo no revienta por fallo de auditoría.
- **Anti-alucinación:** solo cifras de COMPAS citadas por token; `verificar` antes de sustituir; se difunde solo el texto sustituido; publicar nunca recomputa.
- **No hay datos en producción** del vigilante (worker sin aprovisionar) → el rename del modelo es seguro.

---

### Task 1: Cimiento — generalizar `PaqueteVigilante` → `AvisoVigilante` + 2 eventos de auditoría

**Files:**
- Modify: `backend/app/cfo/vigilante/modelos.py` (rename modelo + colección + campos)
- Modify: `backend/app/audit/events.py` (2 eventos nuevos)
- Modify: `backend/app/domain/__init__.py` (registro en `DOMAIN_DOCUMENTS` + `__all__`)
- Modify: `backend/app/cfo/vigilante/paquete.py` (usar `AvisoVigilante(tipo='paquete_lunes')`)
- Modify: `backend/app/cfo/telegram/webhook.py` (query del publicar → `AvisoVigilante` con `tipo='paquete_lunes'`)
- Modify: `backend/tests/cfo/vigilante/test_cimiento.py`, `test_paquete.py`, `backend/tests/cfo/telegram/test_webhook_publicar.py`, `backend/tests/test_audit_events.py`

**Interfaces:**
- Produces: `AvisoVigilante(Document)` {`tipo:str`, `periodo:str`, `texto:str`, `texto_crudo:str`, `estado:str`, `generado_at:datetime`, `publicado_at:datetime|None`, `conceptos_usados:list[str]`}, colección `cfo_avisos_vigilante`, índice único `(tipo, periodo)` = `tipo_periodo_unico`. `estado ∈ {'borrador','publicado','superado'}`. `AuditEvento.vigilante_alerta_generada = "vigilante.alerta.generada"`, `AuditEvento.vigilante_alerta_publicada = "vigilante.alerta.publicada"`.

- [ ] **Step 1: Escribir el test del modelo generalizado**

En `backend/tests/cfo/vigilante/test_cimiento.py`, reemplazar las referencias a `PaqueteVigilante`/`semana` por el nuevo modelo y añadir la aserción de `tipo`/`periodo`/índice:

```python
import pytest
import pytest_asyncio
from app.cfo.vigilante.modelos import AvisoVigilante, CFO_AVISOS_COLLECTION
from app.core.time import now_bogota
from app.domain import DOMAIN_DOCUMENTS
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient


@pytest_asyncio.fixture
async def db():
    client = AsyncMongoMockClient(tz_aware=True)
    await init_beanie(database=client["compas_test"], document_models=DOMAIN_DOCUMENTS)
    yield client


@pytest.mark.asyncio
async def test_aviso_persiste_con_tipo_y_periodo(db):
    a = AvisoVigilante(
        tipo="alerta_caja",
        periodo="2026-08-30",
        texto="hola",
        texto_crudo="[[x]]",
        estado="borrador",
        generado_at=now_bogota(),
    )
    await a.insert()
    got = await AvisoVigilante.find_one(AvisoVigilante.periodo == "2026-08-30")
    assert got is not None and got.tipo == "alerta_caja" and got.estado == "borrador"
    assert AvisoVigilante.get_settings().name == CFO_AVISOS_COLLECTION


@pytest.mark.asyncio
async def test_indice_unico_tipo_periodo(db):
    from pymongo.errors import DuplicateKeyError

    base = dict(periodo="2026-08-31", texto="t", texto_crudo="c",
                estado="borrador", generado_at=now_bogota())
    await AvisoVigilante(tipo="alerta_caja", **base).insert()
    # mismo (tipo, periodo) colisiona; distinto tipo NO
    await AvisoVigilante(tipo="paquete_lunes", **base).insert()
    with pytest.raises(DuplicateKeyError):
        await AvisoVigilante(tipo="alerta_caja", **base).insert()
```

- [ ] **Step 2: Correr el test — debe fallar** (`ImportError: AvisoVigilante`)

Run: `python -m pytest tests/cfo/vigilante/test_cimiento.py -q`
Expected: FAIL (no existe `AvisoVigilante`).

- [ ] **Step 3: Reescribir `modelos.py`**

```python
# backend/app/cfo/vigilante/modelos.py
"""FABS · vigilante — avisos salientes (borrador→publicar). Un `AvisoVigilante` guarda
el borrador que un job proactivo arma (texto sustituido + texto_crudo con [[tokens]])
hasta que el revisor lo publica al comité. `tipo` distingue el paquete del lunes de la
alerta de caja; `(tipo, periodo)` es la clave de idempotencia (lunes / día)."""

from datetime import datetime

from beanie import Document
from pydantic import ConfigDict, Field
from pymongo import IndexModel

CFO_AVISOS_COLLECTION = "cfo_avisos_vigilante"


class AvisoVigilante(Document):
    model_config = ConfigDict(strict=True, extra="forbid")

    tipo: str  # 'paquete_lunes' | 'alerta_caja'
    periodo: str  # 'YYYY-MM-DD' (lunes para el paquete, día para la alerta)
    texto: str
    texto_crudo: str
    estado: str  # 'borrador' | 'publicado' | 'superado'
    generado_at: datetime
    publicado_at: datetime | None = None
    conceptos_usados: list[str] = Field(default_factory=list)

    class Settings:
        name = CFO_AVISOS_COLLECTION
        indexes = [
            IndexModel([("tipo", 1), ("periodo", 1)], unique=True,
                       name="tipo_periodo_unico"),
        ]
```

- [ ] **Step 4: Registrar en `domain/__init__.py`**

Reemplazar `PaqueteVigilante` por `AvisoVigilante` en el import, en `DOMAIN_DOCUMENTS` y en `__all__`.

- [ ] **Step 5: Añadir los 2 eventos en `events.py`**

Tras el bloque del paquete del lunes, dentro de `AuditEvento`:

```python
    # ── CR-CFO-4 (2) — FABS vigilante alerta de caja (GO CEO 2026-08-30) ──
    # `vigilante.alerta.generada` = el job diario armó el borrador de alerta
    # (metadata {periodo, disparadores, severidad, conceptos_usados});
    # `vigilante.alerta.publicada` = el revisor la difundió al comité
    # (metadata {periodo, n_destinatarios}). Catálogo 68 -> 70.
    vigilante_alerta_generada = "vigilante.alerta.generada"
    vigilante_alerta_publicada = "vigilante.alerta.publicada"
```

- [ ] **Step 6: Portar `paquete.py` al modelo nuevo**

Sustituir en `generar_y_entregar_paquete`: `PaqueteVigilante` → `AvisoVigilante`; `semana` → variable local `periodo`; el guard `find_one(tipo=='paquete_lunes', periodo==periodo)`; el constructor con `tipo="paquete_lunes", periodo=periodo`; y la metadata de auditoría `{"periodo": periodo, "tipo": "paquete_lunes", "abstuvo":…, "conceptos_usados":…}`.

```python
from app.cfo.vigilante.modelos import AvisoVigilante
# ...
async def generar_y_entregar_paquete() -> AvisoVigilante | None:
    periodo = now_bogota().date().isoformat()
    if await AvisoVigilante.find_one(
        AvisoVigilante.tipo == "paquete_lunes", AvisoVigilante.periodo == periodo
    ):
        logger.info("paquete del %s ya existe; no se regenera", periodo)
        return None
    resp = await consultar(_PROMPT_PAQUETE, actor_id="vigilante", cliente=crear_cliente())
    if resp.abstuvo and not resp.cifras:
        logger.info("consultar abstuvo sin cifras; no se guarda borrador vacío")
        return None
    pq = AvisoVigilante(
        tipo="paquete_lunes", periodo=periodo, texto=resp.texto,
        texto_crudo=resp.texto_crudo, estado="borrador", generado_at=now_bogota(),
        conceptos_usados=list(resp.conceptos_usados),
    )
    await pq.insert()
    await _audit_soft(
        AuditEvento.vigilante_paquete_generado, periodo,
        {"periodo": periodo, "tipo": "paquete_lunes", "abstuvo": resp.abstuvo,
         "conceptos_usados": list(resp.conceptos_usados)},
    )
    revisor = config.vigilante_revisor_telegram_id()
    if revisor is None:
        logger.warning("VIGILANTE_REVISOR_TELEGRAM_ID sin configurar; borrador no enviado")
        return pq
    cliente_tg = crear_cliente_telegram()
    if cliente_tg is not None:
        await cliente_tg.enviar(
            revisor,
            "📋 Borrador del paquete del lunes\n\n" + resp.texto
            + "\n\nRespondé 'publicar' para difundirlo al comité.",
        )
    return pq
```

- [ ] **Step 7: Portar el query del publicar en `webhook.py`**

En `_publicar_paquete`, cambiar el import y el query al modelo nuevo, filtrando por tipo:

```python
from app.cfo.vigilante.modelos import AvisoVigilante
# ...
    borradores = await (
        AvisoVigilante.find(
            AvisoVigilante.tipo == "paquete_lunes",
            AvisoVigilante.estado == "borrador",
        )
        .sort(-AvisoVigilante.generado_at)
        .limit(1)
        .to_list()
    )
```

(La generalización por `tipo` y el comando `publicar alerta` llegan en la Task 7; aquí solo se mantiene verde el paquete.)

- [ ] **Step 8: Actualizar los tests existentes + el conteo del catálogo**

En `test_paquete.py` y `test_webhook_publicar.py`: `PaqueteVigilante`→`AvisoVigilante`, `semana=`→`tipo="paquete_lunes", periodo=`, y las aserciones de metadata `["semana"]`→`["periodo"]`. En `test_audit_events.py`: subir `len(AuditEvento) == 68`→`70` y `len(CATALOGO_EVENTOS) == 68`→`70`, y agregar los 2 eventos nuevos a la lista esperada.

- [ ] **Step 9: Correr toda la suite del vigilante + telegram + audit — verde**

Run: `python -m pytest tests/cfo/vigilante tests/cfo/telegram tests/test_audit_events.py -q`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add backend/app/cfo/vigilante/modelos.py backend/app/audit/events.py backend/app/domain/__init__.py backend/app/cfo/vigilante/paquete.py backend/app/cfo/telegram/webhook.py backend/tests/cfo backend/tests/test_audit_events.py
git commit -m "feat(cfo): cimiento alerta de caja — AvisoVigilante(tipo) + 2 eventos de auditoria"
```

---

### Task 2: Config editable de la alerta (claves + resolvers + writers)

**Files:**
- Modify: `backend/app/domain/configuracion.py` (2 claves en `ClaveConfig` + `_TIPO_POR_CLAVE`)
- Modify: `backend/app/configuracion/service.py` (resolvers + writers)
- Test: `backend/tests/configuracion/test_alerta_config.py` (nuevo)

**Interfaces:**
- Produces: `ClaveConfig.ALERTA_CAJA_ACTIVA`, `ClaveConfig.ALERTA_CAJA_HORIZONTE_MESES` (tipo `"json"`). `leer_alerta_caja_activa() -> bool` (default `False`), `leer_alerta_horizonte_meses() -> int` (default `6`). `escribir_alerta_caja_activa(*, activa, usuario_id, vigente_desde=None)`, `escribir_alerta_horizonte_meses(*, meses, usuario_id, vigente_desde=None)`.

- [ ] **Step 1: Escribir el test**

```python
# backend/tests/configuracion/test_alerta_config.py
import pytest
import pytest_asyncio
from app.configuracion.service import (
    escribir_alerta_caja_activa,
    escribir_alerta_horizonte_meses,
    leer_alerta_caja_activa,
    leer_alerta_horizonte_meses,
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
async def test_defaults_sin_config(db):
    assert await leer_alerta_caja_activa() is False
    assert await leer_alerta_horizonte_meses() == 6


@pytest.mark.asyncio
async def test_escribir_y_leer_vigencia(db):
    await escribir_alerta_caja_activa(activa=True, usuario_id="andres")
    await escribir_alerta_horizonte_meses(meses=9, usuario_id="andres")
    assert await leer_alerta_caja_activa() is True
    assert await leer_alerta_horizonte_meses() == 9


@pytest.mark.asyncio
async def test_horizonte_invalido_cae_al_default(db):
    await escribir_alerta_horizonte_meses(meses=9, usuario_id="andres")
    # una fila posterior con dato malo no debe romper: el resolver valida > 0 int
    from app.domain.configuracion import ClaveConfig, Configuracion
    await Configuracion(clave=ClaveConfig.ALERTA_CAJA_HORIZONTE_MESES,
                        valor_json={"meses": 0}, vigente_desde="2999-01-01").insert()
    assert await leer_alerta_horizonte_meses() == 6
```

- [ ] **Step 2: Correr — debe fallar** (`ImportError`)

Run: `python -m pytest tests/configuracion/test_alerta_config.py -q`
Expected: FAIL.

- [ ] **Step 3: Añadir las claves en `configuracion.py`**

En `ClaveConfig`:

```python
    # FABS vigilante · alerta de caja (2026-08-30). Editable por dato (no hardcode).
    # ALERTA_CAJA_ACTIVA {"activa": bool} — on/off (ausente → False). HORIZONTE_MESES
    # {"meses": int} — cuántos meses adelante mira el disparador proyectado (ausente → 6).
    ALERTA_CAJA_ACTIVA = "ALERTA_CAJA_ACTIVA"
    ALERTA_CAJA_HORIZONTE_MESES = "ALERTA_CAJA_HORIZONTE_MESES"
```

En `_TIPO_POR_CLAVE` añadir ambas con `"json"`.

- [ ] **Step 4: Resolvers + writers en `configuracion/service.py`**

```python
_ALERTA_HORIZONTE_FALLBACK = 6


async def leer_alerta_caja_activa() -> bool:
    """On/off del vigilante de caja. Ausente/incoherente → False (apagada)."""
    fila = (
        await Configuracion.find(Configuracion.clave == ClaveConfig.ALERTA_CAJA_ACTIVA)
        .sort(-Configuracion.vigente_desde)
        .first_or_none()
    )
    if fila is None or fila.valor_json is None:
        return False
    return bool(fila.valor_json.get("activa", False))


async def leer_alerta_horizonte_meses() -> int:
    """Meses hacia adelante del disparador proyectado. Ausente/incoherente → 6."""
    fila = (
        await Configuracion.find(
            Configuracion.clave == ClaveConfig.ALERTA_CAJA_HORIZONTE_MESES
        )
        .sort(-Configuracion.vigente_desde)
        .first_or_none()
    )
    if fila is None or fila.valor_json is None:
        return _ALERTA_HORIZONTE_FALLBACK
    m = fila.valor_json.get("meses")
    return m if isinstance(m, int) and m > 0 else _ALERTA_HORIZONTE_FALLBACK


async def escribir_alerta_caja_activa(
    *, activa: bool, usuario_id: str, vigente_desde: date | None = None
) -> Configuracion:
    fila = Configuracion(
        clave=ClaveConfig.ALERTA_CAJA_ACTIVA,
        valor_json={"activa": bool(activa)},
        vigente_desde=(vigente_desde or today_bogota()).isoformat(),
        modificado_por=usuario_id,
    )
    await fila.insert()
    return fila


async def escribir_alerta_horizonte_meses(
    *, meses: int, usuario_id: str, vigente_desde: date | None = None
) -> Configuracion:
    if not isinstance(meses, int) or meses <= 0:
        raise ConfiguracionError("el horizonte debe ser un entero de meses > 0", 422)
    fila = Configuracion(
        clave=ClaveConfig.ALERTA_CAJA_HORIZONTE_MESES,
        valor_json={"meses": meses},
        vigente_desde=(vigente_desde or today_bogota()).isoformat(),
        modificado_por=usuario_id,
    )
    await fila.insert()
    return fila
```

- [ ] **Step 5: Correr — verde**

Run: `python -m pytest tests/configuracion/test_alerta_config.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/domain/configuracion.py backend/app/configuracion/service.py backend/tests/configuracion/test_alerta_config.py
git commit -m "feat(config): claves editables ALERTA_CAJA_ACTIVA/HORIZONTE + resolvers/writers"
```

---

### Task 3: Evaluador de disparadores

**Files:**
- Create: `backend/app/cfo/vigilante/disparadores.py`
- Test: `backend/tests/cfo/vigilante/test_disparadores.py` (nuevo)

**Interfaces:**
- Consumes: `proyeccion.service.proyectar_vigente` (dict con `caja_minima`, `caja_atencion`, `piso_caja`, `meses[].estado`), `cierre.service.conciliacion` (dict con `consolidado_reportado`, `sin_dato`), `MesControl`/`EstadoMes`, `configuracion.service.leer_alerta_horizonte_meses`, `cfo.calc.evidencia.ResultadoCFO/Evidencia`.
- Produces: `Disparo(tipo:str, severidad:str)`, `ResultadoAlerta(disparos:list[Disparo], resultados:list[ResultadoCFO])` con `severidad` derivada (`'rojo'` si algún disparo es rojo, si no `'ambar'`). `async evaluar_disparadores() -> ResultadoAlerta | None`.

- [ ] **Step 1: Escribir el test** (con fakes de los dos servicios vía monkeypatch)

```python
# backend/tests/cfo/vigilante/test_disparadores.py
from decimal import Decimal

import pytest
from app.cfo.vigilante import disparadores as D


def _proy(meses, piso, minima="1000", atencion="3000"):
    return {
        "caja_minima": minima, "caja_atencion": atencion, "piso_caja": piso,
        "meses": meses,
    }


@pytest.mark.asyncio
async def test_proyectado_ambar_por_quiebre_en_atencion(monkeypatch):
    async def fake_proy(**k):
        return _proy([{"mes": "2026-09", "estado": "ok"},
                      {"mes": "2026-10", "estado": "atencion"}], piso="2500")
    monkeypatch.setattr(D.proy_service, "proyectar_vigente", fake_proy)
    monkeypatch.setattr(D, "_disparador_real", _sin_real)  # aísla el proyectado
    res = await D.evaluar_disparadores()
    assert res is not None
    d = next(x for x in res.disparos if x.tipo == "proyectado")
    assert d.severidad == "ambar"
    piso = next(r for r in res.resultados if r.concepto == "alerta_piso")
    assert piso.evidencia.ref == "quiebre:2026-10"


@pytest.mark.asyncio
async def test_proyectado_rojo_por_critico(monkeypatch):
    async def fake_proy(**k):
        return _proy([{"mes": "2026-09", "estado": "critico"}], piso="500")
    monkeypatch.setattr(D.proy_service, "proyectar_vigente", fake_proy)
    monkeypatch.setattr(D, "_disparador_real", _sin_real)
    res = await D.evaluar_disparadores()
    assert res.severidad == "rojo"


@pytest.mark.asyncio
async def test_sin_quiebre_y_sin_real_es_none(monkeypatch):
    async def fake_proy(**k):
        return _proy([{"mes": "2026-09", "estado": "ok"}], piso="9000")
    monkeypatch.setattr(D.proy_service, "proyectar_vigente", fake_proy)
    monkeypatch.setattr(D, "_disparador_real", _sin_real)
    assert await D.evaluar_disparadores() is None


@pytest.mark.asyncio
async def test_sin_config_proyeccion_abstiene(monkeypatch):
    from app.proyeccion.service import ProyeccionError

    async def fake_proy(**k):
        raise ProyeccionError("sin params", 409)
    monkeypatch.setattr(D.proy_service, "proyectar_vigente", fake_proy)
    assert await D.evaluar_disparadores() is None


async def _sin_real(*a, **k):  # helper: el disparador real no dispara
    return None, []
```

(El disparador real se prueba con su propio caso: mes en ejecución + conciliación bajo umbral; y la abstención por `sin_dato`/`CierreError`. Añadir esos dos tests con un fake de `cierre.service.conciliacion` y un `MesControl` sembrado.)

- [ ] **Step 2: Correr — debe fallar** (`ModuleNotFoundError`)

Run: `python -m pytest tests/cfo/vigilante/test_disparadores.py -q`
Expected: FAIL.

- [ ] **Step 3: Implementar `disparadores.py`**

```python
# backend/app/cfo/vigilante/disparadores.py
"""FABS · vigilante — evalúa los disparadores de la alerta de caja. Orquestación
(lee servicios de COMPAS; S1: NO vive en cfo/calc). Las cifras SIEMPRE las computa
COMPAS (proyeccion/cierre); aquí solo se compara contra los umbrales vigentes y se
arma la evidencia. Dato incompleto/ambiguo ⇒ abstención (regla 7), nunca adivinar."""

import logging
from dataclasses import dataclass
from decimal import Decimal

from app.cfo.calc.evidencia import Evidencia, ResultadoCFO
from app.cierre.service import CierreError, conciliacion
from app.configuracion.service import leer_alerta_horizonte_meses
from app.core.time import now_bogota, today_bogota
from app.domain.mes_control import EstadoMes, MesControl
from app.proyeccion import service as proy_service
from app.proyeccion.service import ProyeccionError

logger = logging.getLogger(__name__)

_UNIDAD = "COP"
_FUENTE_PROY = "proyeccion.service.proyectar_vigente"
_FUENTE_REAL = "cierre.service.conciliacion"


@dataclass(frozen=True)
class Disparo:
    tipo: str  # 'proyectado' | 'real'
    severidad: str  # 'ambar' | 'rojo'


@dataclass(frozen=True)
class ResultadoAlerta:
    disparos: list[Disparo]
    resultados: list[ResultadoCFO]

    @property
    def severidad(self) -> str:
        return "rojo" if any(d.severidad == "rojo" for d in self.disparos) else "ambar"


def _umbral_res(concepto: str, valor: Decimal, ref: str) -> ResultadoCFO:
    return ResultadoCFO(
        concepto=concepto, valor=valor, unidad=_UNIDAD, disponible=True,
        evidencia=Evidencia(fuente=_FUENTE_PROY, fecha_corte=None, ref=ref),
    )


def _disparador_proyectado(proy: dict) -> tuple[Disparo | None, list[ResultadoCFO]]:
    minima = Decimal(proy["caja_minima"])
    atencion = Decimal(proy["caja_atencion"]) if proy["caja_atencion"] else None
    quiebre = next((m for m in proy["meses"] if m["estado"] != "ok"), None)
    if quiebre is None:
        return None, []
    severidad = "ambar" if quiebre["estado"] == "atencion" else "rojo"
    res = [
        ResultadoCFO(
            concepto="alerta_piso", valor=Decimal(proy["piso_caja"]), unidad=_UNIDAD,
            disponible=True,
            evidencia=Evidencia(fuente=_FUENTE_PROY, fecha_corte=None,
                                ref=f"quiebre:{quiebre['mes']}"),
        ),
        _umbral_res("alerta_umbral_critico", minima, "umbral:critico"),
    ]
    if atencion is not None:
        res.append(_umbral_res("alerta_umbral_atencion", atencion, "umbral:atencion"))
    return Disparo("proyectado", severidad), res


async def _disparador_real(
    minima: Decimal, atencion: Decimal | None
) -> tuple[Disparo | None, list[ResultadoCFO]]:
    mc = await MesControl.find_one(MesControl.estado == EstadoMes.EN_EJECUCION)
    if mc is None:
        return None, []
    try:
        con = await conciliacion(mc.mes)
    except CierreError:
        return None, []
    if con["sin_dato"]:  # dato incompleto: no falsa alarma
        logger.info("alerta real: bancos sin reportar %s; se abstiene", con["sin_dato"])
        return None, []
    disponible = Decimal(con["consolidado_reportado"])
    if disponible <= minima:
        severidad = "rojo"
    elif atencion is not None and disponible <= atencion:
        severidad = "ambar"
    else:
        return None, []
    hoy = today_bogota().isoformat()
    res = [
        ResultadoCFO(
            concepto="alerta_disponible_hoy", valor=disponible, unidad=_UNIDAD,
            disponible=True,
            evidencia=Evidencia(fuente=_FUENTE_REAL, fecha_corte=hoy,
                                ref="disponible:hoy"),
        ),
        _umbral_res("alerta_umbral_critico", minima, "umbral:critico"),
    ]
    if atencion is not None:
        res.append(_umbral_res("alerta_umbral_atencion", atencion, "umbral:atencion"))
    return Disparo("real", severidad), res


async def evaluar_disparadores() -> ResultadoAlerta | None:
    ahora = now_bogota()
    try:
        proy = await proy_service.proyectar_vigente(
            escenario="base",
            mes_inicio=(ahora.year, ahora.month),
            horizonte_meses=await leer_alerta_horizonte_meses(),
        )
    except ProyeccionError:
        return None  # sin config no hay umbral que comparar: abstención total

    minima = Decimal(proy["caja_minima"])
    atencion = Decimal(proy["caja_atencion"]) if proy["caja_atencion"] else None

    disparos: list[Disparo] = []
    resultados: list[ResultadoCFO] = []
    d_proy, r_proy = _disparador_proyectado(proy)
    if d_proy is not None:
        disparos.append(d_proy)
        resultados.extend(r_proy)
    d_real, r_real = await _disparador_real(minima, atencion)
    if d_real is not None:
        disparos.append(d_real)
        resultados.extend(r_real)

    if not disparos:
        return None
    # dedup de conceptos repetidos (umbrales aparecen en ambos disparos)
    vistos: dict[str, ResultadoCFO] = {}
    for r in resultados:
        vistos.setdefault(r.concepto, r)
    return ResultadoAlerta(disparos=disparos, resultados=list(vistos.values()))
```

- [ ] **Step 4: Añadir los tests del disparador real** (mes en ejecución + conciliación) y correr todo — verde

Run: `python -m pytest tests/cfo/vigilante/test_disparadores.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/cfo/vigilante/disparadores.py backend/tests/cfo/vigilante/test_disparadores.py
git commit -m "feat(cfo): evaluador de disparadores de la alerta de caja (proyectado + real)"
```

---

### Task 4: Texto determinista de la alerta

**Files:**
- Create: `backend/app/cfo/vigilante/alerta_texto.py`
- Test: `backend/tests/cfo/vigilante/test_alerta_texto.py` (nuevo)

**Interfaces:**
- Consumes: `ResultadoAlerta`/`Disparo` (Task 3), `verificador.verificar`, `conceptos.sustituir_tokens`.
- Produces: `construir_texto(res: ResultadoAlerta) -> tuple[str, str]` → `(texto_crudo, texto)`. Lanza `AlertaTextoError` si `verificar` no pasa (defensa; no debería ocurrir).

- [ ] **Step 1: Escribir el test**

```python
# backend/tests/cfo/vigilante/test_alerta_texto.py
from decimal import Decimal

import pytest
from app.cfo.calc.evidencia import Evidencia, ResultadoCFO
from app.cfo.vigilante.alerta_texto import construir_texto
from app.cfo.vigilante.disparadores import Disparo, ResultadoAlerta


def _piso(mes):
    return ResultadoCFO(concepto="alerta_piso", valor=Decimal("2500"), unidad="COP",
                        disponible=True,
                        evidencia=Evidencia(fuente="f", fecha_corte=None, ref=f"quiebre:{mes}"))


def _umbral(concepto, val, ref):
    return ResultadoCFO(concepto=concepto, valor=Decimal(val), unidad="COP",
                        disponible=True,
                        evidencia=Evidencia(fuente="f", fecha_corte=None, ref=ref))


def test_proyectado_ambar_sustituye_y_menciona_mes():
    res = ResultadoAlerta(
        disparos=[Disparo("proyectado", "ambar")],
        resultados=[_piso("2026-10"), _umbral("alerta_umbral_atencion", "3000", "umbral:atencion")],
    )
    crudo, texto = construir_texto(res)
    assert "[[alerta_piso]]" in crudo  # el crudo lleva tokens
    assert "[[" not in texto  # el sustituido no
    assert "cruzas el umbral en 2026-10" in texto
    assert "$3.000" in texto


def test_real_rojo_sustituye_disponible_y_critico():
    res = ResultadoAlerta(
        disparos=[Disparo("real", "rojo")],
        resultados=[
            ResultadoCFO(concepto="alerta_disponible_hoy", valor=Decimal("500"),
                         unidad="COP", disponible=True,
                         evidencia=Evidencia(fuente="f", fecha_corte="2026-08-30",
                                             ref="disponible:hoy")),
            _umbral("alerta_umbral_critico", "1000", "umbral:critico"),
        ],
    )
    crudo, texto = construir_texto(res)
    assert "$500 (al 2026-08-30)" in texto
    assert "$1.000" in texto
    assert "[[" not in texto
```

- [ ] **Step 2: Correr — debe fallar**

Run: `python -m pytest tests/cfo/vigilante/test_alerta_texto.py -q`
Expected: FAIL.

- [ ] **Step 3: Implementar `alerta_texto.py`**

```python
# backend/app/cfo/vigilante/alerta_texto.py
"""FABS · vigilante — arma el texto DETERMINISTA de la alerta de caja. Sin LLM: cada
cifra es un [[token]] respaldado por un ResultadoCFO de COMPAS. Pasa por el verificador
(defensa en profundidad; pasa trivial porque no hay cifras crudas) y luego se
sustituyen los tokens. Mismo contrato anti-alucinación que el resto de FABS."""

from app.cfo.agente.conceptos import sustituir_tokens
from app.cfo.agente.verificador import verificar
from app.cfo.vigilante.disparadores import ResultadoAlerta


class AlertaTextoError(RuntimeError):
    """El verificador rechazó el texto de la alerta (no debería ocurrir: es
    determinista y sin cifras crudas). Fail-loud para no difundir algo sin verificar."""


_ENCABEZADO = "🚨 Alerta de caja — FABS"

# Ninguna plantilla contiene un dígito crudo (chocaría con el verificador).
_LINEAS: dict[tuple[str, str], str] = {
    ("proyectado", "ambar"): (
        "⚠️ La caja proyectada entra en zona de atención: el piso baja a "
        "[[alerta_piso]], por debajo del umbral de atención [[alerta_umbral_atencion]]."
    ),
    ("proyectado", "rojo"): (
        "🔴 La caja proyectada cae bajo el mínimo: el piso [[alerta_piso]] cruza el "
        "crítico [[alerta_umbral_critico]]."
    ),
    ("real", "ambar"): (
        "⚠️ El disponible real de hoy [[alerta_disponible_hoy]] está en zona de "
        "atención, bajo el umbral [[alerta_umbral_atencion]]."
    ),
    ("real", "rojo"): (
        "🔴 El disponible real de hoy [[alerta_disponible_hoy]] está bajo el mínimo "
        "[[alerta_umbral_critico]]."
    ),
}


def construir_texto(res: ResultadoAlerta) -> tuple[str, str]:
    cuerpo = "\n".join(_LINEAS[(d.tipo, d.severidad)] for d in res.disparos)
    crudo = f"{_ENCABEZADO}\n\n{cuerpo}"
    ver = verificar(crudo, res.resultados)
    if not ver.ok:
        raise AlertaTextoError(
            f"alerta rechazada por el verificador: cifras={ver.cifras_sin_evidencia} "
            f"tokens_invalidos={ver.tokens_invalidos}"
        )
    return crudo, sustituir_tokens(crudo, res.resultados)
```

- [ ] **Step 4: Correr — verde**

Run: `python -m pytest tests/cfo/vigilante/test_alerta_texto.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/cfo/vigilante/alerta_texto.py backend/tests/cfo/vigilante/test_alerta_texto.py
git commit -m "feat(cfo): texto determinista de la alerta (plantilla + token + verificador)"
```

---

### Task 5: Orquestación `generar_y_entregar_alerta` (supersede / retirar / audit / enviar)

**Files:**
- Create: `backend/app/cfo/vigilante/alerta.py`
- Test: `backend/tests/cfo/vigilante/test_alerta.py` (nuevo)

**Interfaces:**
- Consumes: `evaluar_disparadores` (Task 3), `construir_texto` (Task 4), `AvisoVigilante` (Task 1), `AuditEvento.vigilante_alerta_generada`, `config.vigilante_revisor_telegram_id`, `crear_cliente_telegram`.
- Produces: `async generar_y_entregar_alerta() -> AvisoVigilante | None`. Garantiza ≤1 borrador de alerta pendiente (supersede los de días previos; retira el de hoy si no dispara).

- [ ] **Step 1: Escribir el test**

```python
# backend/tests/cfo/vigilante/test_alerta.py
from decimal import Decimal

import pytest
import pytest_asyncio
from app.audit import service as audit_service
from app.cfo.calc.evidencia import Evidencia, ResultadoCFO
from app.cfo.vigilante import alerta as A
from app.cfo.vigilante.disparadores import Disparo, ResultadoAlerta
from app.cfo.vigilante.modelos import AvisoVigilante
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


def _res_rojo():
    return ResultadoAlerta(
        disparos=[Disparo("real", "rojo")],
        resultados=[
            ResultadoCFO(concepto="alerta_disponible_hoy", valor=Decimal("500"),
                         unidad="COP", disponible=True,
                         evidencia=Evidencia(fuente="f", fecha_corte="2026-08-30",
                                             ref="disponible:hoy")),
            ResultadoCFO(concepto="alerta_umbral_critico", valor=Decimal("1000"),
                         unidad="COP", disponible=True,
                         evidencia=Evidencia(fuente="f", fecha_corte=None,
                                             ref="umbral:critico")),
        ],
    )


class FakeTg:
    def __init__(self):
        self.enviados = []

    async def enviar(self, chat_id, texto):
        self.enviados.append((chat_id, texto))


@pytest.mark.asyncio
async def test_dispara_guarda_borrador_audita_y_envia(db, audit_col, monkeypatch):
    monkeypatch.setenv("VIGILANTE_REVISOR_TELEGRAM_ID", "999")
    monkeypatch.setattr(A, "evaluar_disparadores", lambda: _async(_res_rojo()))
    tg = FakeTg()
    monkeypatch.setattr(A, "crear_cliente_telegram", lambda: tg)

    pq = await A.generar_y_entregar_alerta()
    assert pq is not None and pq.tipo == "alerta_caja" and pq.estado == "borrador"
    assert "publicar alerta" in tg.enviados[-1][1]
    assert "$500" in pq.texto
    doc = await audit_col.find_one({"evento": "vigilante.alerta.generada"})
    assert doc is not None and doc["metadata"]["severidad"] == "rojo"


@pytest.mark.asyncio
async def test_no_dispara_retira_borrador_pendiente(db, audit_col, monkeypatch):
    # había un borrador de ayer
    await AvisoVigilante(tipo="alerta_caja", periodo="2026-08-29", texto="viejo",
                         texto_crudo="c", estado="borrador",
                         generado_at=__import__("app.core.time", fromlist=["now_bogota"]).now_bogota()).insert()
    monkeypatch.setattr(A, "evaluar_disparadores", lambda: _async(None))
    out = await A.generar_y_entregar_alerta()
    assert out is None
    viejo = await AvisoVigilante.find_one(AvisoVigilante.periodo == "2026-08-29")
    assert viejo.estado == "superado"


def _async(v):
    async def _f():
        return v
    return _f()
```

- [ ] **Step 2: Correr — debe fallar**

Run: `python -m pytest tests/cfo/vigilante/test_alerta.py -q`
Expected: FAIL.

- [ ] **Step 3: Implementar `alerta.py`**

```python
# backend/app/cfo/vigilante/alerta.py
"""FABS · vigilante — genera la alerta de caja diaria y la entrega al revisor como
borrador. Espeja `paquete.py`: soft-audit, solo texto verificado. Garantiza ≤1 borrador
de alerta pendiente: supersede los de días previos y retira el de hoy si no dispara."""

import logging

from app.audit.events import AuditEvento
from app.audit.service import emit_audit
from app.cfo import config
from app.cfo.telegram.cliente import crear_cliente_telegram
from app.cfo.vigilante.alerta_texto import construir_texto
from app.cfo.vigilante.disparadores import evaluar_disparadores
from app.cfo.vigilante.modelos import AvisoVigilante
from app.core.time import now_bogota

logger = logging.getLogger(__name__)


async def _audit_soft(evento, entidad_id: str, metadata: dict) -> None:
    try:
        await emit_audit(evento, entidad="vigilante", entidad_id=entidad_id,
                         actor_id="vigilante", metadata=metadata)
    except Exception:  # noqa: BLE001 — job proactivo: no reventar por auditoría
        logger.exception("fallo al auditar %s", evento)


async def _superar_borradores_alerta(excepto: str | None) -> None:
    """Marca 'superado' todo borrador de alerta pendiente cuyo periodo != `excepto`."""
    pendientes = await AvisoVigilante.find(
        AvisoVigilante.tipo == "alerta_caja", AvisoVigilante.estado == "borrador"
    ).to_list()
    for a in pendientes:
        if excepto is None or a.periodo != excepto:
            a.estado = "superado"
            await a.save()


async def generar_y_entregar_alerta() -> AvisoVigilante | None:
    hoy = now_bogota().date().isoformat()
    res = await evaluar_disparadores()
    if res is None:
        await _superar_borradores_alerta(excepto=None)  # retira todo pendiente
        logger.info("alerta de caja: ningún disparador; nada que enviar")
        return None

    await _superar_borradores_alerta(excepto=hoy)  # deja solo el de hoy
    crudo, texto = construir_texto(res)
    conceptos = [r.concepto for r in res.resultados]

    aviso = await AvisoVigilante.find_one(
        AvisoVigilante.tipo == "alerta_caja", AvisoVigilante.periodo == hoy
    )
    if aviso is None:
        aviso = AvisoVigilante(
            tipo="alerta_caja", periodo=hoy, texto=texto, texto_crudo=crudo,
            estado="borrador", generado_at=now_bogota(), conceptos_usados=conceptos,
        )
        await aviso.insert()
    else:  # refresca el de hoy (idempotencia diaria)
        aviso.texto, aviso.texto_crudo = texto, crudo
        aviso.estado, aviso.generado_at = "borrador", now_bogota()
        aviso.conceptos_usados = conceptos
        await aviso.save()

    await _audit_soft(
        AuditEvento.vigilante_alerta_generada, hoy,
        {"periodo": hoy, "disparadores": [d.tipo for d in res.disparos],
         "severidad": res.severidad, "conceptos_usados": conceptos},
    )

    revisor = config.vigilante_revisor_telegram_id()
    if revisor is None:
        logger.warning("VIGILANTE_REVISOR_TELEGRAM_ID sin configurar; alerta no enviada")
        return aviso
    cliente_tg = crear_cliente_telegram()
    if cliente_tg is not None:
        await cliente_tg.enviar(
            revisor, aviso.texto + "\n\nRespondé 'publicar alerta' para difundirla al comité."
        )
    return aviso
```

- [ ] **Step 4: Correr — verde**

Run: `python -m pytest tests/cfo/vigilante/test_alerta.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/cfo/vigilante/alerta.py backend/tests/cfo/vigilante/test_alerta.py
git commit -m "feat(cfo): generar_y_entregar_alerta (supersede diario + soft-audit + envio)"
```

---

### Task 6: Job diario en el scheduler

**Files:**
- Modify: `backend/app/jobs/scheduler.py` (nuevo job + wrapper + docstring)
- Test: `backend/tests/jobs/test_scheduler_alerta.py` (nuevo)

**Interfaces:**
- Consumes: `cfo.config.cfo_enabled`, `configuracion.service.leer_alerta_caja_activa`, `cfo.vigilante.alerta.generar_y_entregar_alerta`.
- Produces: job `vigilante_alerta_caja` (cron diario 8:00 Bogotá) + wrapper `_job_alerta_caja` (no-op si flag off o alerta off; crash-contenido).

- [ ] **Step 1: Escribir el test**

```python
# backend/tests/jobs/test_scheduler_alerta.py
import pytest
from app.jobs import scheduler as S


def test_job_alerta_registrado():
    sch = S.build_scheduler()
    job = sch.get_job("vigilante_alerta_caja")
    assert job is not None
    assert str(job.trigger.fields[job.trigger.FIELD_NAMES.index("hour")]) == "8"


@pytest.mark.asyncio
async def test_noop_con_flag_cfo_off(monkeypatch):
    monkeypatch.setattr("app.cfo.config.cfo_enabled", lambda: False)
    llamado = {"v": False}

    async def _no(): llamado["v"] = True
    monkeypatch.setattr("app.cfo.vigilante.alerta.generar_y_entregar_alerta", _no)
    await S._job_alerta_caja()
    assert llamado["v"] is False


@pytest.mark.asyncio
async def test_noop_con_alerta_off(monkeypatch):
    monkeypatch.setattr("app.cfo.config.cfo_enabled", lambda: True)

    async def _off(): return False
    monkeypatch.setattr("app.configuracion.service.leer_alerta_caja_activa", _off)
    llamado = {"v": False}

    async def _no(): llamado["v"] = True
    monkeypatch.setattr("app.cfo.vigilante.alerta.generar_y_entregar_alerta", _no)
    await S._job_alerta_caja()
    assert llamado["v"] is False


@pytest.mark.asyncio
async def test_corre_cuando_todo_encendido(monkeypatch):
    monkeypatch.setattr("app.cfo.config.cfo_enabled", lambda: True)

    async def _on(): return True
    monkeypatch.setattr("app.configuracion.service.leer_alerta_caja_activa", _on)
    llamado = {"v": False}

    async def _si(): llamado["v"] = True
    monkeypatch.setattr("app.cfo.vigilante.alerta.generar_y_entregar_alerta", _si)
    await S._job_alerta_caja()
    assert llamado["v"] is True
```

- [ ] **Step 2: Correr — debe fallar**

Run: `python -m pytest tests/jobs/test_scheduler_alerta.py -q`
Expected: FAIL.

- [ ] **Step 3: Añadir el job en `build_scheduler` + el wrapper**

En `build_scheduler`, tras el job del paquete:

```python
    scheduler.add_job(
        _job_alerta_caja, "cron", hour=8, minute=0,
        id="vigilante_alerta_caja", coalesce=True, misfire_grace_time=3600,
        replace_existing=True,
    )
```

Nuevo wrapper (junto a `_job_paquete_lunes`):

```python
async def _job_alerta_caja() -> None:
    """Diario 8:00 (America/Bogota). No-op si CFO_ENABLED off o la alerta está
    apagada por config. Import perezoso para no acoplar el scheduler al dominio cfo."""
    from app.cfo import config as cfo_config

    if not cfo_config.cfo_enabled():
        return
    from app.configuracion.service import leer_alerta_caja_activa

    if not await leer_alerta_caja_activa():
        return
    from app.cfo.vigilante.alerta import generar_y_entregar_alerta

    try:
        await generar_y_entregar_alerta()
    except Exception:  # noqa: BLE001 — un job proactivo no revienta el worker
        logger.exception("fallo en el job de la alerta de caja")
```

Actualizar el docstring del módulo para nombrar los DOS jobs (paquete del lunes + alerta de caja).

- [ ] **Step 4: Correr — verde**

Run: `python -m pytest tests/jobs/ -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/jobs/scheduler.py backend/tests/jobs/test_scheduler_alerta.py
git commit -m "feat(jobs): job diario de la alerta de caja (8:00, no-op si off)"
```

---

### Task 7: Publicar — comando `publicar alerta` (generalizar por tipo)

**Files:**
- Modify: `backend/app/cfo/telegram/webhook.py` (`_publicar_paquete` → `_publicar_aviso(tipo)` + ruta del comando)
- Test: `backend/tests/cfo/telegram/test_webhook_publicar_alerta.py` (nuevo)

**Interfaces:**
- Consumes: `AvisoVigilante` (Task 1), `AuditEvento.vigilante_alerta_publicada`.
- Produces: comando exacto `'publicar alerta'` (solo revisor) → difunde el último borrador `tipo='alerta_caja'`; `'publicar'` sigue difundiendo `tipo='paquete_lunes'`. Ambos por `_publicar_aviso(chat_id, cliente, *, tipo, evento)`.

- [ ] **Step 1: Escribir el test**

```python
# backend/tests/cfo/telegram/test_webhook_publicar_alerta.py
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
async def test_publicar_alerta_difunde_al_comite(db, audit_col, monkeypatch):
    monkeypatch.setenv("VIGILANTE_REVISOR_TELEGRAM_ID", "999")
    await _vinc(999, "rev")
    await _vinc(888, "com")
    await AvisoVigilante(tipo="alerta_caja", periodo="2026-08-30", texto="LA ALERTA",
                         texto_crudo="c", estado="borrador",
                         generado_at=datetime.now(UTC)).insert()
    tg = FakeTg()
    upd = {"update_id": 1,
           "message": {"from": {"id": 999}, "chat": {"id": 999}, "text": "publicar alerta"}}
    await webhook.procesar_update(upd, cliente_telegram=tg)
    assert {c for c, t in tg.enviados if t == "LA ALERTA"} == {999, 888}
    got = await AvisoVigilante.find_one(AvisoVigilante.periodo == "2026-08-30")
    assert got.estado == "publicado"
    assert await audit_col.find_one({"evento": "vigilante.alerta.publicada"}) is not None


@pytest.mark.asyncio
async def test_publicar_alerta_no_toca_el_paquete(db, audit_col, monkeypatch):
    monkeypatch.setenv("VIGILANTE_REVISOR_TELEGRAM_ID", "999")
    await _vinc(999, "rev")
    await AvisoVigilante(tipo="paquete_lunes", periodo="2026-08-31", texto="EL PAQUETE",
                         texto_crudo="c", estado="borrador",
                         generado_at=datetime.now(UTC)).insert()
    tg = FakeTg()
    upd = {"update_id": 2,
           "message": {"from": {"id": 999}, "chat": {"id": 999}, "text": "publicar alerta"}}
    await webhook.procesar_update(upd, cliente_telegram=tg)
    assert any("no hay" in t.lower() for _, t in tg.enviados)  # no había borrador de alerta
    pq = await AvisoVigilante.find_one(AvisoVigilante.tipo == "paquete_lunes")
    assert pq.estado == "borrador"  # el paquete intacto
```

- [ ] **Step 2: Correr — debe fallar**

Run: `python -m pytest tests/cfo/telegram/test_webhook_publicar_alerta.py -q`
Expected: FAIL.

- [ ] **Step 3: Generalizar el publicar en `webhook.py`**

Renombrar `_publicar_paquete` a `_publicar_aviso` con parámetros `tipo` y `evento`, y textos parametrizados:

```python
async def _publicar_aviso(
    chat_id: int, cliente_telegram: ClienteTelegramProto, *, tipo: str, evento
) -> str:
    borradores = await (
        AvisoVigilante.find(
            AvisoVigilante.tipo == tipo, AvisoVigilante.estado == "borrador"
        )
        .sort(-AvisoVigilante.generado_at)
        .limit(1)
        .to_list()
    )
    pq = borradores[0] if borradores else None
    if pq is None:
        msg = "No hay un paquete pendiente para publicar." if tipo == "paquete_lunes" \
            else "No hay una alerta pendiente para publicar."
        await cliente_telegram.enviar(chat_id, msg)
        return msg
    vinculos_all = await repositorio.listar_vinculos()
    for v in vinculos_all:
        await cliente_telegram.enviar(v.telegram_id, pq.texto)
    pq.estado = "publicado"
    pq.publicado_at = now_bogota()
    await pq.save()
    await _audit_soft(evento, pq.periodo,
                      {"periodo": pq.periodo, "n_destinatarios": len(vinculos_all)})
    etiqueta = "Paquete" if tipo == "paquete_lunes" else "Alerta"
    msg = f"✅ {etiqueta} {'publicado' if tipo == 'paquete_lunes' else 'publicada'} al comité ({len(vinculos_all)} destinatarios)."
    await cliente_telegram.enviar(chat_id, msg)
    return msg
```

En `procesar_update`, tras el dedup y antes del Q&A, enrutar por comando exacto (el comando más largo primero):

```python
    comando = texto.strip().lower()
    es_revisor = telegram_id == config.vigilante_revisor_telegram_id()
    if es_revisor and comando in ("publicar", "publicar alerta"):
        if comando == "publicar alerta":
            envio = await _publicar_aviso(
                chat_id, cliente_telegram, tipo="alerta_caja",
                evento=AuditEvento.vigilante_alerta_publicada)
        else:
            envio = await _publicar_aviso(
                chat_id, cliente_telegram, tipo="paquete_lunes",
                evento=AuditEvento.vigilante_paquete_publicado)
        await hilos.registrar_dedup(user_id, update_id, envio)
        return
```

(Reemplaza el bloque `es_comando_publicar` actual. El Q&A queda byte-idéntico; una frase que MENCIONE "publicar"/"publicar alerta" no hace match exacto y cae al Q&A. El dedup por update_id ya corre ANTES, cubriendo ambos comandos.)

- [ ] **Step 4: Correr los tests del publicar (paquete + alerta) — verde**

Run: `python -m pytest tests/cfo/telegram/ -q`
Expected: PASS (los del paquete siguen verdes; los de alerta pasan).

- [ ] **Step 5: Commit**

```bash
git add backend/app/cfo/telegram/webhook.py backend/tests/cfo/telegram/test_webhook_publicar_alerta.py
git commit -m "feat(cfo): comando 'publicar alerta' — difunde la alerta al comite (por tipo)"
```

---

### Task 8: Cierre — go-live doc + roadmap + guardas de rama

**Files:**
- Modify: `planning/phases/fabs/GO-LIVE-VIGILANTE.md` (sección de la alerta: encender `ALERTA_CAJA_ACTIVA`, horizonte, umbrales)
- Modify: `docs/COMPAS_FABS_ROADMAP.md` (entrada 2026-08-30 alerta de caja)

- [ ] **Step 1: Guardas de rama**

Run:
```bash
git fetch origin -q
git diff --quiet origin/main..HEAD -- backend/app/proyeccion/motor.py backend/app/presupuesto/motor.py && echo "motor 0 diffs OK"
python -m pytest backend/tests/cfo backend/tests/jobs backend/tests/configuracion backend/tests/test_audit_events.py -q
python -m ruff check backend/app/cfo backend/app/jobs backend/app/configuracion backend/app/domain
python -m pytest backend/tests/cfo/test_s1_aislamiento.py -q
```
Expected: motor 0 diffs; suite verde; ruff limpio; S1 verde; catálogo 70.

- [ ] **Step 2: Actualizar `GO-LIVE-VIGILANTE.md`**

Añadir una sección "Alerta de caja" al runbook: el mismo worker `compas-jobs` la corre (2º job, 8:00); para encenderla: `ALERTA_CAJA_ACTIVA={"activa": true}` vía config; opcional `ALERTA_CAJA_HORIZONTE_MESES`; recordar que los umbrales (crítico/atención) se editan en Supuestos y que la alerta real depende de reportar saldos diarios. El revisor responde `publicar alerta` para difundir.

- [ ] **Step 3: Actualizar el roadmap**

Añadir la entrada fechada 2026-08-30 de la alerta de caja (2ª pieza del vigilante; gate-waiver + GO CEO; determinista; 2 disparadores).

- [ ] **Step 4: Commit**

```bash
git add planning/phases/fabs/GO-LIVE-VIGILANTE.md docs/COMPAS_FABS_ROADMAP.md
git commit -m "docs(fabs): cierre alerta de caja — go-live + roadmap"
```

---

## Self-Review

**1. Spec coverage:** §5.1 modelo→Task 1; §5.2 config→Task 2; §5.3 disparadores→Task 3; §5.4 texto→Task 4; §5.5 orquestación+job→Task 5+6; §5.6 publicar→Task 7; §5.7 auditoría→Task 1 (declara) + Task 5/7 (emiten); §6 anti-alucinación→Task 4 (verificar) + Task 7 (no recomputa); §7 reglas→Global Constraints + Task 8 guardas; §8 casos borde→Tasks 3/5/7; §9 testing→cada task; §10 fuera de alcance→respetado (UI/LLM/cierre mensual no se tocan). Cubierto.

**2. Placeholder scan:** cada step de código trae el código real; los tests del disparador real (Step 4 Task 3) y la sección de docs (Task 8) describen contenido concreto sin "TBD".

**3. Type consistency:** `AvisoVigilante(tipo, periodo, texto, texto_crudo, estado, generado_at, publicado_at, conceptos_usados)` idéntico en Tasks 1/5/7. `evaluar_disparadores()->ResultadoAlerta|None`, `ResultadoAlerta(disparos, resultados)` con `.severidad`, `Disparo(tipo, severidad)` idénticos en Tasks 3/4/5. `construir_texto(res)->(crudo, texto)` en Tasks 4/5. `_publicar_aviso(chat_id, cliente, *, tipo, evento)->str` en Task 7. Resolvers `leer_alerta_caja_activa()->bool` / `leer_alerta_horizonte_meses()->int` en Tasks 2/3/6. Consistente.
