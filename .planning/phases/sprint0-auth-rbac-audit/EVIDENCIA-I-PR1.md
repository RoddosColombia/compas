# EVIDENCIA — I-PR1 (audit base): código y salidas reales

Paquete solicitado por Kimi §5. Cada archivo va íntegro. Al final, las salidas de pytest (normal y -m requires_real_mongo) y ruff.


## archivo: backend/app/audit/events.py

```
# backend/app/audit/events.py
"""Catálogo CERRADO de eventos de auditoría (regla 11 / Spec §1.11 / CR-001).

29 del Spec §1.11 (10 v1.0 + 12 v1.1 + 7 v1.1.1) + `extracto.cargado` (CR-001) = 30.
NO se inventan eventos sin CR. El nombre del miembro usa `_`; el valor usa
`<dominio>.<acción>`."""

from enum import StrEnum


class AuditEvento(StrEnum):
    # ── v1.0 (10) ──
    presupuesto_acotado = "presupuesto.acotado"
    presupuesto_definido = "presupuesto.definido"
    mes_cerrado = "mes.cerrado"
    mes_reabierto = "mes.reabierto"
    transaccion_clasificada = "transaccion.clasificada"
    carga_completada = "carga.completada"
    factura_creada = "factura.creada"
    iva_declarado = "iva.declarado"
    rubro_desactivado = "rubro.desactivado"
    user_login = "user.login"

    # ── v1.1 (12) ──
    mes_creado = "mes.creado"
    user_login_fallido = "user.login_fallido"
    user_bloqueado = "user.bloqueado"
    user_creado = "user.creado"
    user_rol_cambiado = "user.rol_cambiado"
    user_desactivado = "user.desactivado"
    exportacion_realizada = "exportacion.realizada"
    archivo_descargado = "archivo.descargado"
    config_actualizada = "config.actualizada"
    parametros_ingreso_modificado = "parametros_ingreso.modificado"
    saldo_inicial_editado = "saldo_inicial.editado"
    carga_fallida = "carga.fallida"

    # ── v1.1.1 (7) ──
    presupuesto_crec_modificado = "presupuesto.crec_modificado"
    presupuesto_crec_global_aplicado = "presupuesto.crec_global_aplicado"
    iva_generado_override = "iva_generado.override"
    transaccion_tardia = "transaccion.tardia"
    factura_emitida_creada = "factura_emitida.creada"
    factura_emitida_editada = "factura_emitida.editada"
    factura_emitida_anulada = "factura_emitida.anulada"

    # ── CR-001 (1) → total 30 ──
    extracto_cargado = "extracto.cargado"


# Conjunto de los 30 valores canónicos (para validación/tests de completitud).
CATALOGO_EVENTOS: frozenset[str] = frozenset(e.value for e in AuditEvento)
```


## archivo: backend/app/audit/models.py

```
# backend/app/audit/models.py
"""Esquema AuditLog (append-only). Spec §1.11 / §2.3.

Es un Pydantic BaseModel plano (strict): valida y serializa el registro que
`emit_audit` inserta por la conexión DEDICADA de auditoría. NO es un Beanie
Document: las escrituras no pasan por el ODM general (van por `compas_audit`), y
las lecturas (query service) llegan en un PR posterior. La inmutabilidad la impone
los PRIVILEGIOS de BD; `$jsonSchema` (Sprint 0b) es defensa en profundidad."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.audit.events import AuditEvento
from app.core.time import now_utc

AUDIT_COLLECTION = "audit_log"

# Índice forense (Spec §2.3). Lo crea la migración/init (Sprint 0b), no este módulo.
AUDIT_INDEXES = [
    {
        "keys": [("entidad", 1), ("entidad_id", 1), ("timestamp", 1)],
        "name": "forense_entidad_ts",
    },
]


class AuditLog(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")  # regla 3

    evento: AuditEvento
    entidad: str
    # entidad_id / actor_id: str (forma canónica en texto del id referenciado) para
    # consultas forenses consistentes con el índice (entidad, entidad_id, timestamp).
    # Kimi O2: decisión explícita str (no ObjectId); el _id del audit lo pone Mongo.
    entidad_id: str | None = None
    actor_id: str | None = None
    metadata: dict = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=now_utc)  # UTC aware (regla A-04)
```


## archivo: backend/app/audit/service.py

```
# backend/app/audit/service.py
"""emit_audit — escritura append-only por la conexión DEDICADA de auditoría.

Regla 4 / DoD #6: la inmutabilidad se impone por privilegios de BD. Las escrituras
van por `compas_audit` (rol `audit_writer` = insert+find), una SEGUNDA cadena de
conexión (`MONGODB_URI_AUDIT`) a la MISMA database `compas` — NO una db separada
(dejaría audit_log fuera del dump/restore/archivado). El usuario general de la app
no tiene update/remove sobre `audit_log`.

En la app real, `configure_audit` se llama en el lifespan con el cliente de auditoría;
en tests se inyecta un cliente mongomock."""

from typing import Any

from app.audit.events import AuditEvento
from app.audit.models import AuditLog
from app.core.time import now_utc

_audit_collection: Any = None


def configure_audit(client: Any, db_name: str = "compas") -> None:
    """Fija la colección `audit_log` sobre la conexión dedicada de auditoría."""
    global _audit_collection
    _audit_collection = client[db_name]["audit_log"]


def reset_audit() -> None:
    """Resetea la configuración (para tests)."""
    global _audit_collection
    _audit_collection = None


async def emit_audit(
    evento: AuditEvento | str,
    entidad: str,
    entidad_id: str | None = None,
    actor_id: str | None = None,
    metadata: dict | None = None,
) -> AuditLog:
    """Inserta un evento en `audit_log`. Valida contra el catálogo cerrado (30);
    `AuditEvento(evento)` lanza ValueError si el evento no existe (regla 11).

    Política de fallo ante error de BD (Kimi O1) — `emit_audit` **propaga** la
    excepción (fail-closed por defecto):
      • Operaciones de estado del ciclo (aprobar/cerrar/reabrir/config): el llamador
        NO debe continuar sin audit — sin auditoría no hay operación (principio del
        sistema). Dejar propagar dentro de la transacción multi-documento → rollback.
      • Eventos no críticos (p. ej. lecturas/exportaciones): el llamador envuelve en
        try/except + logger.error + Sentry y continúa.
    `entidad_id` (Kimi O2) se persiste como **str** (forma canónica del id
    referenciado), consistente con el índice forense de audit_log (Spec §2.3)."""
    if _audit_collection is None:
        raise RuntimeError(
            "audit no configurado: llamar configure_audit(client) primero"
        )
    evento = AuditEvento(evento)  # ValueError si no está en el catálogo
    doc = AuditLog(
        evento=evento,
        entidad=entidad,
        entidad_id=entidad_id,
        actor_id=actor_id,
        metadata=metadata or {},
        timestamp=now_utc(),
    )
    payload = doc.model_dump(mode="python", exclude={"id"})
    payload["evento"] = doc.evento.value  # str para BSON, no el enum de Python
    await _audit_collection.insert_one(payload)
    return doc
```


## archivo: backend/app/core/time.py

```
# backend/app/core/time.py
"""Tiempo y zona horaria — regla 2 de CLAUDE.md.

Zona horaria única: América/Bogotá. Toda marca de tiempo del dominio se
genera con `now_bogota()`. Fechas de negocio en `YYYY-MM-DD`; los meses se
normalizan al día 1 con `month_start()`.
"""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

BOGOTA = ZoneInfo("America/Bogota")


def now_bogota() -> datetime:
    """Ahora, con offset -05:00 explícito (América/Bogotá). SOLO presentación."""
    return datetime.now(BOGOTA)


def now_utc() -> datetime:
    """Ahora en UTC aware. Convención de la fase (Kimi A-04): TODA marca temporal
    de persistencia / TTL de Mongo / claims JWT es UTC aware — un datetime naive
    Bogotá se leería como UTC (−5 h) y desfasaría TTL y `exp`. Prohibido naive."""
    return datetime.now(UTC)


def today_bogota() -> date:
    """Fecha de hoy en América/Bogotá."""
    return now_bogota().date()


def month_start(d: date) -> date:
    """Normaliza una fecha al primer día de su mes (llave de MesControl)."""
    return d.replace(day=1)
```


## archivo: backend/app/main.py

```
# backend/app/main.py
"""Punto de entrada del servicio web FastAPI (compas-api).

Regla 6 de CLAUDE.md: el servicio web NUNCA arranca el scheduler. El lifespan
falla en duro si detecta RUN_SCHEDULER=true (defensa contra un despliegue mal
configurado)."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api.v1 import api_router
from app.audit import service as audit_service
from app.config import get_settings
from app.db import mongo

logger = logging.getLogger("compas")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    # Regla 6: el web jamás corre el scheduler.
    if settings.run_scheduler:
        raise RuntimeError(
            "RUN_SCHEDULER=true en el servicio web: prohibido (regla 6). "
            "Los jobs viven solo en el worker compas-jobs."
        )

    # Cliente Motor perezoso (no conecta hasta el primer comando) → el web
    # arranca aunque Mongo esté caído; la liveness no depende de la BD.
    client = mongo.create_client(settings.mongodb_uri_compas)
    app.state.mongo_client = client
    app.state.settings = settings
    # NOTA (Sprint 0b): cuando existan document models, llamar aquí
    #   await mongo.init_beanie_for(client, settings.mongodb_db)

    # Conexión DEDICADA de auditoría (DoD #6). MONGODB_URI_AUDIT usa el usuario
    # `compas_audit` (audit_writer). FAIL-FAST fuera de dev (Kimi C-01): un warning
    # no es un control — degradar el canal de auditoría en prod es degradación
    # silenciosa de un requisito de primera clase. Solo dev cae a la conexión general.
    if settings.mongodb_uri_audit:
        audit_client = mongo.create_client(settings.mongodb_uri_audit)
    elif settings.app_env == "development":
        audit_client = client  # fallback SOLO en dev (sin separación de privilegios)
        logger.warning(
            "audit por conexión general (dev): sin separación de privilegios."
        )
    else:
        raise RuntimeError(
            "MONGODB_URI_AUDIT requerido fuera de dev: el canal de auditoría no "
            "puede degradarse silenciosamente (DoD #6, Kimi C-01)."
        )
    app.state.audit_client = audit_client
    audit_service.configure_audit(audit_client, settings.mongodb_db)

    try:
        yield
    finally:
        audit_service.reset_audit()
        if audit_client is not client:
            audit_client.close()
        client.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="COMPAS API",
        version=__version__,
        lifespan=lifespan,
    )

    @app.get("/health", tags=["health"])
    def liveness() -> dict[str, str]:
        """Liveness — SIN tocar la BD. Es el healthCheckPath de render.yaml."""
        return {"status": "ok", "service": "compas-api", "version": __version__}

    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
```


## archivo: backend/app/config.py

```
# backend/app/config.py
"""Configuración de la app vía Pydantic Settings.

Regla 12 de CLAUDE.md / STACK §5.1: las env vars son SOLO para secretos y
conexiones. Las reglas de negocio parametrizables (umbrales, calendario DIAN)
NO viven aquí: van en la colección `configuracion` (Spec §1.10), y se
implementan desde el Sprint 0b.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # ignora env vars ajenas (Render/OS inyectan muchas)
        case_sensitive=False,
    )

    # ── Entorno ────────────────────────────────────────────────────────
    app_env: str = "development"  # development | staging | production
    # Zona horaria única de la app (regla 2). La región cloud es otra cosa
    # (se hereda de SISMO; ver RUNBOOK §0).
    tz: str = "America/Bogota"

    # ── Scheduler (regla 6) ────────────────────────────────────────────
    # false en el servicio web SIEMPRE; true SOLO en el worker compas-jobs.
    run_scheduler: bool = False

    # ── Conexión a Mongo (secreto: sync=false en render.yaml) ──────────
    mongodb_uri_compas: str = "mongodb://localhost:27017"
    mongodb_db: str = "compas"
    # Segunda cadena a la MISMA database `compas`, usuario `compas_audit`
    # (rol audit_writer). Inmutabilidad del audit_log (DoD #6 / errata E-7).
    # Opcional en dev; obligatoria en staging/producción.
    mongodb_uri_audit: str | None = None

    # ── Secretos (opcionales en dev/skeleton; obligatorios en prod) ────
    jwt_secret: str | None = None
    sentry_dsn: str | None = None
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    s3_bucket: str | None = None


@lru_cache
def get_settings() -> Settings:
    """Instancia única de Settings (cacheada). Los tests que cambian env vars
    deben llamar `get_settings.cache_clear()`."""
    return Settings()
```


## archivo: scripts/create_audit_role.py

```
#!/usr/bin/env python
"""Crea (idempotente) el rol `audit_writer` y el usuario `compas_audit` en Mongo.

DoD #6 / RUNBOOK §2: el usuario general de la app NO tiene update/remove sobre
`audit_log`; solo `compas_audit` (rol `audit_writer` = insert+find) escribe. Ambos
sobre la MISMA database `compas` (no una db separada — así el audit_log entra en el
dump/restore/archivado).

Uso (contra un mongod con auth de admin):
    python scripts/create_audit_role.py "<MONGODB_ADMIN_URI>" [db=compas] [pass=<compas_audit_pwd>]

Idempotente: si el rol/usuario ya existen, actualiza privilegios sin fallar. Este
script lo corre el operador (RUNBOOK) y el CI de la Sesión 3 sobre un mongod efímero
con auth para validar los tests @requires_real_mongo. NO se ejecuta en runtime de la app.
"""

from __future__ import annotations

import sys

from pymongo import MongoClient
from pymongo.errors import OperationFailure


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit('Uso: python scripts/create_audit_role.py "<MONGODB_ADMIN_URI>" [db] [pass]')
    uri = sys.argv[1]
    db_name = sys.argv[2] if len(sys.argv) > 2 else "compas"
    audit_pwd = sys.argv[3] if len(sys.argv) > 3 else "CHANGE_ME"

    client: MongoClient = MongoClient(uri)
    db = client[db_name]

    # 1) Rol audit_writer: insert + find sobre audit_log; SIN update/remove.
    role = {
        "createRole": "audit_writer",
        "privileges": [
            {
                "resource": {"db": db_name, "collection": "audit_log"},
                "actions": ["insert", "find"],
            }
        ],
        "roles": [],
    }
    try:
        db.command(role)
        print("Rol audit_writer creado.")
    except OperationFailure as e:
        if e.code == 51002 or "already exists" in str(e).lower():  # Role already exists
            db.command({
                "updateRole": "audit_writer",
                "privileges": role["privileges"],
                "roles": [],
            })
            print("Rol audit_writer ya existía → privilegios actualizados.")
        else:
            raise

    # 2) Usuario compas_audit con ese rol.
    user = {
        "createUser": "compas_audit",
        "pwd": audit_pwd,
        "roles": [{"role": "audit_writer", "db": db_name}],
    }
    try:
        db.command(user)
        print("Usuario compas_audit creado.")
    except OperationFailure as e:
        if e.code == 51003 or "already exists" in str(e).lower():  # User already exists
            db.command({
                "updateUser": "compas_audit",
                "roles": [{"role": "audit_writer", "db": db_name}],
            })
            print("Usuario compas_audit ya existía → roles actualizados.")
        else:
            raise

    # 3) Índice forense (Kimi O3): lo crea el setup con privilegios de admin, NO el
    # rol audit_writer (solo insert+find). Idempotente (createIndex no duplica).
    # Debe coincidir con AUDIT_INDEXES de app/audit/models.py.
    db["audit_log"].create_index(
        [("entidad", 1), ("entidad_id", 1), ("timestamp", 1)],
        name="forense_entidad_ts",
    )
    print("Índice forense (entidad, entidad_id, timestamp) asegurado.")

    print(
        "Listo. El usuario general de la app NO debe tener update/remove sobre "
        f"{db_name}.audit_log (verificar su rol readWrite acotado)."
    )


if __name__ == "__main__":
    main()
```


## archivo: backend/tests/conftest.py

```
# backend/tests/conftest.py
#
# ==========================================================================
#  ESTRATEGIA DE BASE DE DATOS EN TESTS  (Sprint 0, Sesión 1)
# ==========================================================================
# En esta sesión usamos mongomock-motor (AsyncMongoMockClient) para los
# tests que tocan Mongo (readiness /health/ready, init_beanie). Es rápido y
# no requiere un mongod local.
#
#  ⚠️  LÍMITE DELIBERADO — mongomock NO es suficiente a partir del Sprint 1:
#
#   • Sprint 1 — Deduplicación: el índice ÚNICO PARCIAL
#       (banco, id_banco) con partialFilterExpression {id_banco:{$type:'string'}}
#     (regla 5 de CLAUDE.md / Spec §2.3) NO está soportado por mongomock:
#     no valida unicidad parcial ni lanza DuplicateKeyError como el motor real.
#
#   • Sprint 4 — Transacciones multi-documento: las transacciones de MongoDB
#     (aprobación de presupuesto, finalización de carga, cierre de mes;
#     regla 8 / Spec §2.2.6) NO existen en mongomock (no hay sessions con
#     commit/abort ni TransientTransactionError).
#
#  Por eso, TODO test que dependa de esos dos comportamientos DEBE marcarse
#  con @pytest.mark.requires_real_mongo y correr contra un Mongo REAL
#  (mongod local o contenedor; se configurará en el CI del Sprint 1).
#  Estos tests se saltan por defecto y solo corren con:  pytest -m requires_real_mongo
#  (habiendo exportado COMPAS_TEST_MONGO_URI apuntando a un Mongo real).
# ==========================================================================

import os

import pytest
from app.deps import get_mongo_client
from app.main import create_app
from mongomock_motor import AsyncMongoMockClient


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "requires_real_mongo: el test necesita un Mongo REAL (índice único "
        "parcial del Sprint 1 y/o transacciones multi-documento del Sprint 4). "
        "mongomock NO los soporta. Correr con: pytest -m requires_real_mongo",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Salta por defecto los tests que exigen Mongo real, salvo que se pidan
    explícitamente con `-m requires_real_mongo`."""
    marker_expr = config.getoption("-m")
    if "requires_real_mongo" in marker_expr:
        return  # el usuario los pidió explícitamente
    skip = pytest.mark.skip(
        reason="requiere Mongo real; correr con: pytest -m requires_real_mongo"
    )
    for item in items:
        if "requires_real_mongo" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def mock_mongo_client() -> AsyncMongoMockClient:
    """Cliente Mongo simulado para tests de esta sesión."""
    return AsyncMongoMockClient()


@pytest.fixture
def app(mock_mongo_client: AsyncMongoMockClient):
    """App FastAPI con el cliente Mongo real reemplazado por el mock.

    RUN_SCHEDULER queda en false (default): el servicio web NUNCA arranca el
    scheduler (regla 6 de CLAUDE.md)."""
    from app.config import get_settings

    os.environ.pop("RUN_SCHEDULER", None)
    get_settings.cache_clear()
    application = create_app()
    application.dependency_overrides[get_mongo_client] = lambda: mock_mongo_client
    return application
```


## archivo: backend/tests/test_audit_events.py

```
# backend/tests/test_audit_events.py
"""Catálogo CERRADO de auditoría — regla 11 / Spec §1.11 / CR-001.

29 (Spec §1.11) + extracto.cargado (CR-001) = 30. No se inventan eventos."""

from app.audit.events import CATALOGO_EVENTOS, AuditEvento


def test_catalogo_tiene_exactamente_30_eventos():
    assert len(AuditEvento) == 30
    assert len(CATALOGO_EVENTOS) == 30


def test_extracto_cargado_es_el_evento_30_de_cr001():
    # CR-001: extracto.cargado (extracto mensual) != carga.completada (carga diaria).
    assert AuditEvento.extracto_cargado.value == "extracto.cargado"
    assert AuditEvento.carga_completada.value == "carga.completada"
    assert AuditEvento.extracto_cargado != AuditEvento.carga_completada


def test_eventos_clave_presentes():
    for esperado in (
        "user.login",
        "user.login_fallido",
        "user.bloqueado",
        "mes.cerrado",
        "presupuesto.definido",
        "iva_generado.override",
        "factura_emitida.anulada",
    ):
        assert esperado in CATALOGO_EVENTOS


def test_valores_son_dominio_punto_accion():
    # Convención: "<dominio>.<acción>" en minúsculas.
    for e in AuditEvento:
        assert "." in e.value
        assert e.value == e.value.lower()
```


## archivo: backend/tests/test_audit_emit.py

```
# backend/tests/test_audit_emit.py
"""emit_audit — inserción append-only por la conexión dedicada (PR-1)."""

from datetime import UTC

import pytest
from app.audit import service
from app.audit.events import AuditEvento
from mongomock_motor import AsyncMongoMockClient


@pytest.fixture
def audit_col():
    """Configura emit_audit contra una colección mongomock y la devuelve."""
    client = AsyncMongoMockClient()
    service.configure_audit(client, "compas_test")
    yield client["compas_test"]["audit_log"]
    service.reset_audit()


async def test_emit_audit_inserta_doc_bien_formado(audit_col):
    await service.emit_audit(
        AuditEvento.user_login,
        entidad="user",
        entidad_id="507f1f77bcf86cd799439011",
        actor_id="507f1f77bcf86cd799439011",
        metadata={"ip": "1.2.3.4"},
    )
    doc = await audit_col.find_one({"evento": "user.login"})
    assert doc is not None
    assert doc["entidad"] == "user"
    assert doc["metadata"] == {"ip": "1.2.3.4"}


async def test_emit_audit_timestamp_es_utc_aware(audit_col):
    # Regla A-04: persistencia en UTC aware, nunca naive.
    d = await service.emit_audit(
        AuditEvento.mes_creado, entidad="mes", entidad_id="2026-07"
    )
    assert d.timestamp.tzinfo is not None
    assert d.timestamp.utcoffset() == UTC.utcoffset(None)


async def test_emit_audit_rechaza_evento_invalido(audit_col):
    with pytest.raises((ValueError, KeyError)):
        await service.emit_audit("evento.inventado", entidad="x")  # type: ignore[arg-type]


async def test_emit_audit_sin_configurar_falla():
    service.reset_audit()
    with pytest.raises(RuntimeError, match="configur"):
        await service.emit_audit(AuditEvento.user_login, entidad="user")
```


## archivo: backend/tests/test_audit_immutable.py

```
# backend/tests/test_audit_immutable.py
"""DoD #6 — inmutabilidad del audit_log verificada contra Mongo REAL.

mongomock NO evalúa privilegios de BD (haría placebo). Estos tests corren contra
un mongod REAL con auth y el rol `audit_writer` (usuario `compas_audit`), y el
usuario general de la app SIN update/remove. Se validan en el CI de la Sesión 3.

Por decisión (CEO 18-jul): diferidos a CI. El marker @requires_real_mongo hace que
FALLEN (no skip) si se piden con `-m requires_real_mongo` sin un mongod con auth."""

import pytest

pytestmark = pytest.mark.requires_real_mongo


def test_update_sobre_audit_log_falla_con_rol_app():
    # Con la conexión general de la app (sin update), un update_one sobre audit_log
    # debe lanzar OperationFailure (code 13, Unauthorized).
    raise AssertionError("Pendiente CI Sesión 3: requiere mongod real con roles.")


def test_remove_sobre_audit_log_falla_con_rol_app():
    raise AssertionError("Pendiente CI Sesión 3: requiere mongod real con roles.")


def test_insert_y_find_como_compas_audit_funcionan():
    # Test POSITIVO: sin él, un rol roto sin insert pasaría el negativo y el audit
    # moriría en silencio.
    raise AssertionError("Pendiente CI Sesión 3: requiere mongod real con roles.")
```


## archivo: backend/tests/test_audit_failfast.py

```
# backend/tests/test_audit_failfast.py
"""Kimi C-01: fuera de dev, el arranque FALLA si falta MONGODB_URI_AUDIT.

Un warning no es un control; el canal de auditoría no puede degradarse en silencio."""

import pytest
from app.config import get_settings
from app.main import create_app
from fastapi.testclient import TestClient


def test_arranque_falla_sin_uri_audit_fuera_de_dev(monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.delenv("MONGODB_URI_AUDIT", raising=False)
    monkeypatch.delenv("RUN_SCHEDULER", raising=False)
    get_settings.cache_clear()
    app = create_app()
    with pytest.raises(RuntimeError, match="MONGODB_URI_AUDIT"):
        with TestClient(app):
            pass
    get_settings.cache_clear()


def test_arranque_ok_en_dev_sin_uri_audit(monkeypatch):
    """En dev SÍ cae a la conexión general (con warning), sin fallar."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("MONGODB_URI_AUDIT", raising=False)
    monkeypatch.delenv("RUN_SCHEDULER", raising=False)
    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
    get_settings.cache_clear()
```


## archivo: backend/.env.example

```
# COMPAS backend — variables de entorno (EJEMPLO). Copiar a backend/.env
# Regla 12: ningún secreto en el repo. Este archivo solo documenta las claves;
# los valores reales se cargan a mano en Render/Vercel (RUNBOOK §8) y nunca se
# commitean (.env está en .gitignore).

# ── Entorno ──
APP_ENV=development
TZ=America/Bogota

# ── Scheduler (regla 6) ──
# false en el web SIEMPRE; true SOLO en el worker compas-jobs.
RUN_SCHEDULER=false

# ── Mongo ──
MONGODB_URI_COMPAS=mongodb://localhost:27017
MONGODB_DB=compas
# Conexión dedicada de auditoría (usuario compas_audit, rol audit_writer) a la
# MISMA db compas. Opcional en dev; obligatoria en staging/producción (DoD #6).
MONGODB_URI_AUDIT=

# ── Secretos (dejar vacíos en dev/skeleton) ──
JWT_SECRET=
SENTRY_DSN=
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
S3_BUCKET=
```


## salida: pytest -q (suite completa)

```
..........sss.....s....                                                  [100%]
=========================== short test summary info ===========================
SKIPPED [3] tests\test_audit_immutable.py: requiere Mongo real; correr con: pytest -m requires_real_mongo
SKIPPED [1] tests\test_real_mongo_marker.py:11: requiere Mongo real; correr con: pytest -m requires_real_mongo
19 passed, 4 skipped in 0.21s
```


## salida: pytest -q -m requires_real_mongo (deben FALLAR, no skip)

```
FFFF                                                                     [100%]
================================== FAILURES ===================================
________________ test_update_sobre_audit_log_falla_con_rol_app ________________

    def test_update_sobre_audit_log_falla_con_rol_app():
        # Con la conexión general de la app (sin update), un update_one sobre audit_log
        # debe lanzar OperationFailure (code 13, Unauthorized).
>       raise AssertionError("Pendiente CI Sesión 3: requiere mongod real con roles.")
E       AssertionError: Pendiente CI Sesión 3: requiere mongod real con roles.

tests\test_audit_immutable.py:19: AssertionError
________________ test_remove_sobre_audit_log_falla_con_rol_app ________________

    def test_remove_sobre_audit_log_falla_con_rol_app():
>       raise AssertionError("Pendiente CI Sesión 3: requiere mongod real con roles.")
E       AssertionError: Pendiente CI Sesión 3: requiere mongod real con roles.

tests\test_audit_immutable.py:23: AssertionError
_______________ test_insert_y_find_como_compas_audit_funcionan ________________

    def test_insert_y_find_como_compas_audit_funcionan():
        # Test POSITIVO: sin él, un rol roto sin insert pasaría el negativo y el audit
        # moriría en silencio.
>       raise AssertionError("Pendiente CI Sesión 3: requiere mongod real con roles.")
E       AssertionError: Pendiente CI Sesión 3: requiere mongod real con roles.

tests\test_audit_immutable.py:29: AssertionError
_________________ test_placeholder_dedup_indice_unico_parcial _________________

    @pytest.mark.requires_real_mongo
    def test_placeholder_dedup_indice_unico_parcial():
        # Sprint 1: aquí irá el test del índice único parcial (banco, id_banco)
        # con partialFilterExpression {id_banco:{$type:'string'}} + DuplicateKeyError.
        # mongomock NO lo soporta → debe correr contra Mongo real.
>       raise AssertionError(
            "Este test no debería ejecutarse sin `-m requires_real_mongo`."
        )
E       AssertionError: Este test no debería ejecutarse sin `-m requires_real_mongo`.

tests\test_real_mongo_marker.py:16: AssertionError
=========================== short test summary info ===========================
FAILED tests/test_audit_immutable.py::test_update_sobre_audit_log_falla_con_rol_app
FAILED tests/test_audit_immutable.py::test_remove_sobre_audit_log_falla_con_rol_app
FAILED tests/test_audit_immutable.py::test_insert_y_find_como_compas_audit_funcionan
FAILED tests/test_real_mongo_marker.py::test_placeholder_dedup_indice_unico_parcial
4 failed, 19 deselected in 0.17s
```


## salida: ruff check .

```
All checks passed!
```


## diff: docs/RUNBOOK-INFRA.md (§2 y §8)

```
§2 (+): Usuario `compas_audit` con SOLO el rol `audit_writer` (2ª cadena
MONGODB_URI_AUDIT a la MISMA db compas). El usuario general compas_app NO
tiene update/remove sobre audit_log. Crear con scripts/create_audit_role.py.
§8 (+): | MONGODB_URI_AUDIT | Render (api y worker)/Actions — usuario compas_audit | Semestral |
```

