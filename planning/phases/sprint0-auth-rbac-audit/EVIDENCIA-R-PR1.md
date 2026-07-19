# EVIDENCIA — R-PR1 (audit base): diff de líneas cambiadas + salidas

Diff `d08a395..288ce54` (solo los archivos de código/RUNBOOK). Al final, salidas reales.


## diff

```
diff --git a/backend/app/audit/models.py b/backend/app/audit/models.py
index cf7cd7c..657eac3 100644
--- a/backend/app/audit/models.py
+++ b/backend/app/audit/models.py
@@ -4,19 +4,22 @@
 Es un Pydantic BaseModel plano (strict): valida y serializa el registro que
 `emit_audit` inserta por la conexión DEDICADA de auditoría. NO es un Beanie
 Document: las escrituras no pasan por el ODM general (van por `compas_audit`), y
-las lecturas (query service) llegan en un PR posterior. La inmutabilidad la impone
-los PRIVILEGIOS de BD; `$jsonSchema` (Sprint 0b) es defensa en profundidad."""
+las lecturas (query service) llegan en un PR posterior — reusarán ESTE mismo
+schema. La inmutabilidad la imponen los PRIVILEGIOS de BD; `$jsonSchema` (Sprint
+0b) es defensa en profundidad."""
 
 from datetime import datetime
+from typing import Any
 
-from pydantic import BaseModel, ConfigDict, Field
+from pydantic import BaseModel, ConfigDict, Field, field_validator
 
 from app.audit.events import AuditEvento
 from app.core.time import now_utc
 
 AUDIT_COLLECTION = "audit_log"
 
-# Índice forense (Spec §2.3). Lo crea la migración/init (Sprint 0b), no este módulo.
+# Índice forense (Spec §2.3). Lo crea el script de setup (create_audit_role.py) con
+# privilegios de admin — NO el rol audit_writer (solo insert+find).
 AUDIT_INDEXES = [
     {
         "keys": [("entidad", 1), ("entidad_id", 1), ("timestamp", 1)],
@@ -30,10 +33,27 @@ class AuditLog(BaseModel):
 
     evento: AuditEvento
     entidad: str
-    # entidad_id / actor_id: str (forma canónica en texto del id referenciado) para
-    # consultas forenses consistentes con el índice (entidad, entidad_id, timestamp).
+    # entidad_id / actor_id: str (forma canónica del id referenciado) para consultas
+    # forenses consistentes con el índice (entidad, entidad_id, timestamp).
     # Kimi O2: decisión explícita str (no ObjectId); el _id del audit lo pone Mongo.
     entidad_id: str | None = None
     actor_id: str | None = None
-    metadata: dict = Field(default_factory=dict)
+    metadata: dict[str, Any] = Field(default_factory=dict)  # H-07: debe ser BSON-able
     timestamp: datetime = Field(default_factory=now_utc)  # UTC aware (regla A-04)
+
+    @field_validator("evento", mode="before")
+    @classmethod
+    def _cast_evento(cls, v: Any) -> AuditEvento:
+        # H-04: strict rechazaría un str; casteamos str→enum al leer desde Mongo
+        # (query service futuro). AuditEvento(v) lanza ValueError si no está en el
+        # catálogo cerrado (regla 11).
+        return v if isinstance(v, AuditEvento) else AuditEvento(v)
+
+    @field_validator("timestamp")
+    @classmethod
+    def _timestamp_aware(cls, v: datetime) -> datetime:
+        # H-05: nunca naive. BSON no guarda tz; el cliente usa tz_aware=True y aquí
+        # rechazamos cualquier naive que se cuele (regla A-04).
+        if v.tzinfo is None:
+            raise ValueError("timestamp debe ser UTC-aware (regla A-04), no naive")
+        return v
diff --git a/backend/app/audit/service.py b/backend/app/audit/service.py
index d7358cb..026c145 100644
--- a/backend/app/audit/service.py
+++ b/backend/app/audit/service.py
@@ -8,7 +8,7 @@ conexión (`MONGODB_URI_AUDIT`) a la MISMA database `compas` — NO una db separ
 no tiene update/remove sobre `audit_log`.
 
 En la app real, `configure_audit` se llama en el lifespan con el cliente de auditoría;
-en tests se inyecta un cliente mongomock."""
+en tests se inyecta un cliente mongomock_motor."""
 
 from typing import Any
 
@@ -63,7 +63,7 @@ async def emit_audit(
         metadata=metadata or {},
         timestamp=now_utc(),
     )
-    payload = doc.model_dump(mode="python", exclude={"id"})
+    payload = doc.model_dump(mode="python")
     payload["evento"] = doc.evento.value  # str para BSON, no el enum de Python
     await _audit_collection.insert_one(payload)
     return doc
diff --git a/backend/app/config.py b/backend/app/config.py
index 92ebca1..d0ddb20 100644
--- a/backend/app/config.py
+++ b/backend/app/config.py
@@ -8,6 +8,7 @@ implementan desde el Sprint 0b.
 """
 
 from functools import lru_cache
+from typing import Literal
 
 from pydantic_settings import BaseSettings, SettingsConfigDict
 
@@ -21,7 +22,8 @@ class Settings(BaseSettings):
     )
 
     # ── Entorno ────────────────────────────────────────────────────────
-    app_env: str = "development"  # development | staging | production
+    # Literal (Kimi Baja): un typo en APP_ENV falla al validar, no en runtime.
+    app_env: Literal["development", "staging", "production"] = "development"
     # Zona horaria única de la app (regla 2). La región cloud es otra cosa
     # (se hereda de SISMO; ver RUNBOOK §0).
     tz: str = "America/Bogota"
@@ -34,8 +36,8 @@ class Settings(BaseSettings):
     mongodb_uri_compas: str = "mongodb://localhost:27017"
     mongodb_db: str = "compas"
     # Segunda cadena a la MISMA database `compas`, usuario `compas_audit`
-    # (rol audit_writer). Inmutabilidad del audit_log (DoD #6 / errata E-7).
-    # Opcional en dev; obligatoria en staging/producción.
+    # (rol audit_writer). Inmutabilidad del audit_log (DoD #6; errata E-7 en
+    # docs/COMPAS_ERRATA_PENDIENTE_v1_1_3.md). Opcional en dev; obligatoria fuera.
     mongodb_uri_audit: str | None = None
 
     # ── Secretos (opcionales en dev/skeleton; obligatorios en prod) ────
diff --git a/backend/tests/conftest.py b/backend/tests/conftest.py
index 05aaac5..8255484 100644
--- a/backend/tests/conftest.py
+++ b/backend/tests/conftest.py
@@ -59,6 +59,17 @@ def pytest_collection_modifyitems(
             item.add_marker(skip)
 
 
+@pytest.fixture(autouse=True)
+def _clear_settings_cache():
+    """Limpia el cache de get_settings antes y después de cada test — evita que un
+    test que cambia env vars contamine a otro (Kimi Baja)."""
+    from app.config import get_settings
+
+    get_settings.cache_clear()
+    yield
+    get_settings.cache_clear()
+
+
 @pytest.fixture
 def mock_mongo_client() -> AsyncMongoMockClient:
     """Cliente Mongo simulado para tests de esta sesión."""
diff --git a/backend/tests/test_audit_emit.py b/backend/tests/test_audit_emit.py
index 56dac02..4ceb910 100644
--- a/backend/tests/test_audit_emit.py
+++ b/backend/tests/test_audit_emit.py
@@ -30,6 +30,10 @@ async def test_emit_audit_inserta_doc_bien_formado(audit_col):
     assert doc is not None
     assert doc["entidad"] == "user"
     assert doc["metadata"] == {"ip": "1.2.3.4"}
+    # H-06: el evento se persiste como str puro (no el enum). StrEnum == str, así que
+    # sin este type-check el aserto pasaría aunque se guardara el enum de Python.
+    assert type(doc["evento"]) is str
+    assert doc["evento"] == "user.login"
 
 
 async def test_emit_audit_timestamp_es_utc_aware(audit_col):
diff --git a/backend/tests/test_audit_immutable.py b/backend/tests/test_audit_immutable.py
index 9df5c63..a887c38 100644
--- a/backend/tests/test_audit_immutable.py
+++ b/backend/tests/test_audit_immutable.py
@@ -6,7 +6,12 @@ un mongod REAL con auth y el rol `audit_writer` (usuario `compas_audit`), y el
 usuario general de la app SIN update/remove. Se validan en el CI de la Sesión 3.
 
 Por decisión (CEO 18-jul): diferidos a CI. El marker @requires_real_mongo hace que
-FALLEN (no skip) si se piden con `-m requires_real_mongo` sin un mongod con auth."""
+FALLEN (no skip) si se piden con `-m requires_real_mongo` sin un mongod con auth.
+
+IMPORTANTE (Kimi Baja): en la Sesión 3, el job de CI que corre `-m requires_real_mongo`
+DEBE ser un required check que BLOQUEE el merge — si no, DoD #6 nunca se verifica de
+verdad y nadie lo nota. El mongod de CI debe tener auth habilitada + el rol audit_writer
+cableado (sin auth, el test de permisos pasa en falso)."""
 
 import pytest
 
diff --git a/docs/RUNBOOK-INFRA.md b/docs/RUNBOOK-INFRA.md
index 5c89a33..098a01f 100644
--- a/docs/RUNBOOK-INFRA.md
+++ b/docs/RUNBOOK-INFRA.md
@@ -34,7 +34,8 @@
 - [ ] Database `compas` y `compas_stg` en el cluster M10 existente
 - [ ] Usuario `compas_app`: readWrite SOLO sobre `compas` (otro usuario para `compas_stg`)
 - [ ] Rol custom `audit_writer`: insert + find sobre `compas.audit_log`, SIN update/remove (verificado por test en CI)
-- [ ] Usuario `compas_audit` con SOLO el rol `audit_writer` (2ª cadena `MONGODB_URI_AUDIT` a la MISMA db `compas`; ver §8). El usuario general `compas_app` NO tiene update/remove sobre `audit_log`. Crear con `python scripts/create_audit_role.py "<admin_uri>"` (idempotente)
+- [ ] Usuario `compas_audit` con SOLO el rol `audit_writer` (2ª cadena `MONGODB_URI_AUDIT` a la MISMA db `compas`; ver §8). El usuario general `compas_app` NO tiene update/remove sobre `audit_log`. Crear con `COMPAS_AUDIT_PWD=… python scripts/create_audit_role.py "<admin_uri>"` (idempotente; el operador necesita `userAdmin` sobre `compas`; contraseña ≥16 chars por env, nunca por argv)
+  - **Tier Atlas (Kimi H-01):** `createRole`/`createUser` funcionan en **M10+** (nuestro cluster, Opción A). En **Free/Flex** están bloqueados → crear el rol/usuario por **Atlas UI o Admin API** (los cambios de custom roles tardan ~30 s). El script detecta el rechazo y remite aquí.
 - [ ] Atlas Alerts al canal del Tech Lead: CPU > 70% sostenida, conexiones > 60% del límite (disparadores de migración a cluster propio, STACK §7)
 - [ ] Anotar región del cluster en §0
 
diff --git a/scripts/create_audit_role.py b/scripts/create_audit_role.py
index 2f75761..fefde67 100644
--- a/scripts/create_audit_role.py
+++ b/scripts/create_audit_role.py
@@ -6,28 +6,55 @@ DoD #6 / RUNBOOK §2: el usuario general de la app NO tiene update/remove sobre
 sobre la MISMA database `compas` (no una db separada — así el audit_log entra en el
 dump/restore/archivado).
 
-Uso (contra un mongod con auth de admin):
-    python scripts/create_audit_role.py "<MONGODB_ADMIN_URI>" [db=compas] [pass=<compas_audit_pwd>]
+La contraseña NUNCA va por argv (visible en ps/historial/CI, CWE-798/214): se lee de
+COMPAS_AUDIT_PWD o por getpass, sin default, mínimo 16 chars. Actualiza rol Y contraseña.
 
-Idempotente: si el rol/usuario ya existen, actualiza privilegios sin fallar. Este
-script lo corre el operador (RUNBOOK) y el CI de la Sesión 3 sobre un mongod efímero
-con auth para validar los tests @requires_real_mongo. NO se ejecuta en runtime de la app.
+Uso (contra un mongod con auth de admin, usuario con privilegio userAdmin sobre la db):
+    COMPAS_AUDIT_PWD=... python scripts/create_audit_role.py "<MONGODB_ADMIN_URI>" [db=compas]
+
+Idempotente: si el rol/usuario ya existen, actualiza privilegios y contraseña sin fallar.
+Lo corre el operador (RUNBOOK §2) y el CI de la Sesión 3 sobre un mongod efímero con auth
+para validar los tests @requires_real_mongo. NO se ejecuta en runtime de la app.
+
+NOTA de tier Atlas (Kimi H-01): createRole/createUser están disponibles en M10+ (el cluster
+de este proyecto). En clusters Free/Flex están BLOQUEADOS → usar Atlas UI o Admin API (los
+cambios de custom roles tardan ~30 s). Ver RUNBOOK §2.
 """
 
 from __future__ import annotations
 
+import getpass
+import os
 import sys
 
 from pymongo import MongoClient
 from pymongo.errors import OperationFailure
 
+# Textos/códigos con los que Atlas Free/Flex rechaza los comandos no soportados.
+_UNSUPPORTED = ("not allowed", "unsupported", "not supported", "command not found")
+
+
+def _fail_if_unsupported(e: OperationFailure) -> None:
+    msg = str(e).lower()
+    if any(s in msg for s in _UNSUPPORTED):
+        sys.exit(
+            "Atlas rechazó el comando (¿cluster Free/Flex?). En esos tiers "
+            "createRole/createUser están bloqueados: crea el rol audit_writer y el "
+            "usuario compas_audit por Atlas UI / Admin API. Ver RUNBOOK §2."
+        )
+
 
 def main() -> None:
     if len(sys.argv) < 2:
-        sys.exit('Uso: python scripts/create_audit_role.py "<MONGODB_ADMIN_URI>" [db] [pass]')
+        sys.exit('Uso: COMPAS_AUDIT_PWD=... python scripts/create_audit_role.py "<MONGODB_ADMIN_URI>" [db]')
     uri = sys.argv[1]
     db_name = sys.argv[2] if len(sys.argv) > 2 else "compas"
-    audit_pwd = sys.argv[3] if len(sys.argv) > 3 else "CHANGE_ME"
+
+    audit_pwd = os.environ.get("COMPAS_AUDIT_PWD") or getpass.getpass(
+        "Password para compas_audit (>=16 chars): "
+    )
+    if len(audit_pwd) < 16:
+        sys.exit("La contraseña de compas_audit debe tener al menos 16 caracteres.")
 
     client: MongoClient = MongoClient(uri)
     db = client[db_name]
@@ -47,6 +74,7 @@ def main() -> None:
         db.command(role)
         print("Rol audit_writer creado.")
     except OperationFailure as e:
+        _fail_if_unsupported(e)  # H-01: tier Free/Flex
         if e.code == 51002 or "already exists" in str(e).lower():  # Role already exists
             db.command({
                 "updateRole": "audit_writer",
@@ -67,12 +95,16 @@ def main() -> None:
         db.command(user)
         print("Usuario compas_audit creado.")
     except OperationFailure as e:
+        _fail_if_unsupported(e)  # H-01: tier Free/Flex
         if e.code == 51003 or "already exists" in str(e).lower():  # User already exists
+            # H-02: actualizar roles Y contraseña (coherente con la rotación
+            # semestral del RUNBOOK §8; sin pwd, la URI rotada dejaría de autenticar).
             db.command({
                 "updateUser": "compas_audit",
+                "pwd": audit_pwd,
                 "roles": [{"role": "audit_writer", "db": db_name}],
             })
-            print("Usuario compas_audit ya existía → roles actualizados.")
+            print("Usuario compas_audit ya existía → roles y contraseña actualizados.")
         else:
             raise
 
```


## salida: pytest -q

```
..........sss.....s....                                                  [100%]
=========================== short test summary info ===========================
SKIPPED [3] tests\test_audit_immutable.py: requiere Mongo real; correr con: pytest -m requires_real_mongo
SKIPPED [1] tests\test_real_mongo_marker.py:11: requiere Mongo real; correr con: pytest -m requires_real_mongo
19 passed, 4 skipped in 0.21s
```


## salida: pytest -q -m requires_real_mongo (deben FALLAR)

```
FFFF                                                                     [100%]
================================== FAILURES ===================================
________________ test_update_sobre_audit_log_falla_con_rol_app ________________

    def test_update_sobre_audit_log_falla_con_rol_app():
        # Con la conexión general de la app (sin update), un update_one sobre audit_log
        # debe lanzar OperationFailure (code 13, Unauthorized).
>       raise AssertionError("Pendiente CI Sesión 3: requiere mongod real con roles.")
E       AssertionError: Pendiente CI Sesión 3: requiere mongod real con roles.

tests\test_audit_immutable.py:24: AssertionError
________________ test_remove_sobre_audit_log_falla_con_rol_app ________________

    def test_remove_sobre_audit_log_falla_con_rol_app():
>       raise AssertionError("Pendiente CI Sesión 3: requiere mongod real con roles.")
E       AssertionError: Pendiente CI Sesión 3: requiere mongod real con roles.

tests\test_audit_immutable.py:28: AssertionError
_______________ test_insert_y_find_como_compas_audit_funcionan ________________

    def test_insert_y_find_como_compas_audit_funcionan():
        # Test POSITIVO: sin él, un rol roto sin insert pasaría el negativo y el audit
        # moriría en silencio.
>       raise AssertionError("Pendiente CI Sesión 3: requiere mongod real con roles.")
E       AssertionError: Pendiente CI Sesión 3: requiere mongod real con roles.

tests\test_audit_immutable.py:34: AssertionError
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
4 failed, 19 deselected in 0.21s
```


## salida: ruff check .

```
All checks passed!
```

