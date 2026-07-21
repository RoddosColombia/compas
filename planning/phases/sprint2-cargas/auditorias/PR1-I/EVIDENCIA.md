# EVIDENCIA — sprint2-cargas · PR1-I

Rama `feat/cargas-endpoints-manual`, commit `54f12d6` (SIN mergear). Código real + salidas.

## 1. pytest (suite completa local)
```
232 passed, 23 skipped (20 nuevos)
```

## 2. ruff
```
All checks passed!
```

## 3. Protocolo de commit
```
r1:0 | journal-entries:0 | estado-pending:0
```

## 4. git diff --stat (main..54f12d6)
```
backend/app/api/v1/__init__.py             |   4 +
 backend/app/cargas/router.py               | 132 ++++++++++++++++++
 backend/app/config.py                      |   6 +
 backend/app/core/ulid.py                   |  22 +++
 backend/app/domain/__init__.py             |   3 +
 backend/app/domain/idempotency.py          |  46 +++++++
 backend/app/transacciones/__init__.py      |   2 +
 backend/app/transacciones/router.py        | 132 ++++++++++++++++++
 backend/app/transacciones/service.py       | 102 ++++++++++++++
 backend/tests/test_cargas_endpoint.py      | 127 ++++++++++++++++++
 backend/tests/test_db.py                   |   2 +-
 backend/tests/test_transacciones_manual.py | 208 +++++++++++++++++++++++++++++
 backend/tests/test_ulid.py                 |  19 +++
 13 files changed, 804 insertions(+), 1 deletion(-)
```

## 5. Diff completo
```diff
diff --git a/backend/app/api/v1/__init__.py b/backend/app/api/v1/__init__.py
index c5e7866..eede760 100644
--- a/backend/app/api/v1/__init__.py
+++ b/backend/app/api/v1/__init__.py
@@ -5,7 +5,11 @@ from fastapi import APIRouter
 
 from app.api.v1 import health
 from app.auth.router import router as auth_router
+from app.cargas.router import router as cargas_router
+from app.transacciones.router import router as transacciones_router
 
 api_router = APIRouter()
 api_router.include_router(health.router)
 api_router.include_router(auth_router)
+api_router.include_router(cargas_router)
+api_router.include_router(transacciones_router)
diff --git a/backend/app/cargas/router.py b/backend/app/cargas/router.py
new file mode 100644
index 0000000..a280be5
--- /dev/null
+++ b/backend/app/cargas/router.py
@@ -0,0 +1,132 @@
+# backend/app/cargas/router.py
+"""Endpoints de cargas (Spec §1.6, F-22, PRD M7).
+
+MARCADO PARA AUDITORÍA KIMI (flujo crítico: cargas bancarias).
+
+F-22: solo .xlsx/.xls; .xlsm (macros) rechazado SIEMPRE; límite 10 MB verificado
+ANTES de procesar. El archivo se escribe a un temp y `procesar_carga` corre el
+parseo en threadpool. La preservación del original (M-04) usa `ORIGINALES_DIR`
+(interim local hasta S3); sin destino → 409 con mensaje accionable."""
+
+import os
+import tempfile
+
+from anyio import to_thread
+from beanie import PydanticObjectId
+from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
+
+from app.auth.deps import require_permission
+from app.auth.models import User
+from app.auth.router import verify_origin
+from app.cargas import service
+from app.config import get_settings
+from app.domain.bancos import Banco
+from app.domain.carga import CargaBancaria
+from app.parsers.bank_parsers import detectar_banco
+
+router = APIRouter(prefix="/cargas", tags=["cargas"])
+
+_MAX_BYTES = 10 * 1024 * 1024  # F-22
+_EXT_OK = {".xlsx", ".xls"}
+
+
+def _serializar(c: CargaBancaria, *, detalle: bool = False) -> dict:
+    d = {
+        "id": str(c.id),
+        "banco": c.banco.value,
+        "archivo_nombre": c.archivo_nombre,
+        "estado": c.estado.value,
+        "total_filas": c.total_filas,
+        "nuevas": c.nuevas,
+        "duplicadas": c.duplicadas,
+        "errores": c.errores,
+        "motivo_fallo": c.motivo_fallo,
+        "created_at": c.created_at.isoformat(),
+    }
+    if detalle:
+        d["errores_detalle"] = [e.model_dump() for e in c.errores_detalle]
+    return d
+
+
+@router.post("", status_code=201)
+async def subir_extracto(
+    archivo: UploadFile,
+    user: User = Depends(require_permission("cargas:gestionar")),
+    _: None = Depends(verify_origin),
+):
+    nombre = archivo.filename or "extracto"
+    ext = os.path.splitext(nombre)[1].lower()
+    if ext == ".xlsm":
+        raise HTTPException(422, "archivos .xlsm (macros) no se aceptan (F-22)")
+    if ext not in _EXT_OK:
+        raise HTTPException(
+            422, f"extensión '{ext}' no soportada; solo .xlsx/.xls (F-22)"
+        )
+    contenido = await archivo.read(_MAX_BYTES + 1)
+    if len(contenido) > _MAX_BYTES:
+        raise HTTPException(413, "el extracto supera el límite de 10 MB (F-22)")
+
+    fd, tmp = tempfile.mkstemp(suffix=ext)
+    try:
+        with os.fdopen(fd, "wb") as f:
+            f.write(contenido)
+        try:
+            banco: Banco = await to_thread.run_sync(detectar_banco, tmp)
+        except ValueError as e:
+            raise HTTPException(422, str(e)) from e
+
+        settings = get_settings()
+        try:
+            carga = await service.procesar_carga(
+                banco=banco,
+                archivo_path=tmp,
+                archivo_nombre=nombre,
+                usuario_id=PydanticObjectId(user.id),
+                dir_originales=settings.originales_dir,
+            )
+        except service.CargaDuplicadaError as e:
+            raise HTTPException(409, str(e)) from e
+        except service.OriginalNoPreservableError as e:
+            raise HTTPException(409, str(e)) from e
+        except service.CargaError as e:
+            raise HTTPException(422, str(e)) from e
+    finally:
+        try:
+            os.unlink(tmp)
+        except OSError:
+            pass
+    return _serializar(carga, detalle=True)
+
+
+@router.get("")
+async def listar_cargas(
+    limit: int = Query(default=20, ge=1, le=100),
+    cursor: str | None = Query(default=None),
+    user: User = Depends(require_permission("cargas:gestionar")),
+):
+    q = CargaBancaria.find_all()
+    if cursor:
+        try:
+            q = CargaBancaria.find(CargaBancaria.id < PydanticObjectId(cursor))
+        except Exception:
+            raise HTTPException(422, "cursor inválido") from None
+    filas = await q.sort(-CargaBancaria.id).limit(limit + 1).to_list()
+    next_cursor = str(filas[limit - 1].id) if len(filas) > limit else None
+    return {
+        "items": [_serializar(c) for c in filas[:limit]],
+        "next_cursor": next_cursor,
+    }
+
+
+@router.get("/{carga_id}")
+async def detalle_carga(
+    carga_id: str,
+    user: User = Depends(require_permission("cargas:gestionar")),
+):
+    try:
+        carga = await CargaBancaria.get(PydanticObjectId(carga_id))
+    except Exception:
+        raise HTTPException(422, "id inválido") from None
+    if carga is None:
+        raise HTTPException(404, "carga no encontrada")
+    return _serializar(carga, detalle=True)
diff --git a/backend/app/config.py b/backend/app/config.py
index eb56b59..59c73ab 100644
--- a/backend/app/config.py
+++ b/backend/app/config.py
@@ -60,6 +60,12 @@ class Settings(BaseSettings):
     # Fail-fast fuera de dev (como JWT_SECRET): sin ella el TOTP no se puede descifrar.
     mfa_enc_key: str | None = None
 
+    # ── Cargas (M-04, interim hasta S3) ────────────────────────────────
+    # Directorio local donde se preserva el original de cada extracto. En Render
+    # el disco es efímero: esto es un puente de DESARROLLO; la carga real exige
+    # S3 (DISP-02). Sin destino, procesar_carga rechaza (OriginalNoPreservableError).
+    originales_dir: str | None = None
+
     # ── Secretos (opcionales en dev/skeleton; obligatorios en prod) ────
     jwt_secret: str | None = None
     sentry_dsn: str | None = None
diff --git a/backend/app/core/ulid.py b/backend/app/core/ulid.py
new file mode 100644
index 0000000..780ed34
--- /dev/null
+++ b/backend/app/core/ulid.py
@@ -0,0 +1,22 @@
+# backend/app/core/ulid.py
+"""ULID (F-04): identificador de 26 chars, ordenable por tiempo, Crockford base32.
+
+Se usa para el `id_banco` sintético de transacciones manuales ('MAN-'+ULID):
+único por construcción → dos manuales idénticos el mismo día no chocan en el
+índice (banco, id_banco). Sin dependencia externa: 48 bits de timestamp (ms) +
+80 bits aleatorios (spec ULID)."""
+
+import secrets
+import time
+
+CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
+
+
+def new_ulid() -> str:
+    valor = (int(time.time() * 1000) & ((1 << 48) - 1)) << 80
+    valor |= secrets.randbits(80)
+    chars = []
+    for _ in range(26):
+        chars.append(CROCKFORD[valor & 0x1F])
+        valor >>= 5
+    return "".join(reversed(chars))
diff --git a/backend/app/domain/__init__.py b/backend/app/domain/__init__.py
index cf2b296..6022dea 100644
--- a/backend/app/domain/__init__.py
+++ b/backend/app/domain/__init__.py
@@ -9,6 +9,7 @@ el ODM general.
 
 from app.domain.carga import CargaBancaria
 from app.domain.configuracion import Configuracion
+from app.domain.idempotency import IdempotencyKey
 from app.domain.mes_control import MesControl
 from app.domain.rubro import Rubro
 from app.domain.transaccion import Transaccion
@@ -19,6 +20,7 @@ DOMAIN_DOCUMENTS: list[type] = [
     Configuracion,
     Transaccion,
     CargaBancaria,
+    IdempotencyKey,
 ]
 
 __all__ = [
@@ -27,5 +29,6 @@ __all__ = [
     "Configuracion",
     "Transaccion",
     "CargaBancaria",
+    "IdempotencyKey",
     "DOMAIN_DOCUMENTS",
 ]
diff --git a/backend/app/domain/idempotency.py b/backend/app/domain/idempotency.py
new file mode 100644
index 0000000..4ecf50e
--- /dev/null
+++ b/backend/app/domain/idempotency.py
@@ -0,0 +1,46 @@
+# backend/app/domain/idempotency.py
+"""IdempotencyKeys (Spec §1.12, F-13): replay seguro de POST sensibles.
+
+Scope = índice ÚNICO COMPUESTO (usuario_id, endpoint, key). Se guarda el hash
+del request y la respuesta original: misma clave + mismo payload → replay de la
+respuesta; misma clave + payload distinto → 422. TTL 24 h (expires_at + índice
+expireAfterSeconds=0, patrón E-6)."""
+
+from datetime import datetime, timedelta
+
+from beanie import Document
+from pydantic import ConfigDict, Field
+from pymongo import IndexModel
+
+from app.core.time import now_utc
+
+IDEMPOTENCY_COLLECTION = "idempotency_keys"
+_TTL_HORAS = 24
+
+
+def _expira() -> datetime:
+    return now_utc() + timedelta(hours=_TTL_HORAS)
+
+
+class IdempotencyKey(Document):
+    model_config = ConfigDict(strict=True, extra="forbid")
+
+    usuario_id: str
+    endpoint: str
+    key: str
+    request_hash: str  # sha256 del payload canónico
+    response_status: int | None = None  # None = petición aún en curso
+    response_body: dict | None = None
+    created_at: datetime = Field(default_factory=now_utc)
+    expires_at: datetime = Field(default_factory=_expira)
+
+    class Settings:
+        name = IDEMPOTENCY_COLLECTION
+        indexes = [
+            IndexModel(
+                [("usuario_id", 1), ("endpoint", 1), ("key", 1)],
+                name="scope_unico",
+                unique=True,
+            ),
+            IndexModel([("expires_at", 1)], name="ttl", expireAfterSeconds=0),
+        ]
diff --git a/backend/app/transacciones/__init__.py b/backend/app/transacciones/__init__.py
new file mode 100644
index 0000000..e9aa9f1
--- /dev/null
+++ b/backend/app/transacciones/__init__.py
@@ -0,0 +1,2 @@
+# backend/app/transacciones/__init__.py
+"""Transacciones manuales (US-10, F-04): registro directo por el Financiero."""
diff --git a/backend/app/transacciones/router.py b/backend/app/transacciones/router.py
new file mode 100644
index 0000000..b23421c
--- /dev/null
+++ b/backend/app/transacciones/router.py
@@ -0,0 +1,132 @@
+# backend/app/transacciones/router.py
+"""POST /api/v1/transacciones — transacción manual con Idempotency-Key (§1.12).
+
+MARCADO PARA AUDITORÍA KIMI (flujo crítico).
+
+Regla 1: `valor` viaja como STRING (strict=True rechaza numbers JSON). El replay
+idempotente devuelve la respuesta original; misma key + payload distinto → 422."""
+
+import hashlib
+import json
+from decimal import Decimal, InvalidOperation
+
+from fastapi import APIRouter, Depends, Header, HTTPException
+from fastapi.responses import JSONResponse
+from pydantic import BaseModel, ConfigDict, Field, field_validator
+
+from app.auth.deps import require_permission
+from app.auth.models import User
+from app.auth.router import verify_origin
+from app.core.money import money_str
+from app.domain.idempotency import IdempotencyKey
+from app.domain.rubro import TipoFlujo
+from app.domain.transaccion import Transaccion
+from app.transacciones import service
+
+router = APIRouter(prefix="/transacciones", tags=["transacciones"])
+
+_ENDPOINT = "POST /transacciones"
+
+
+class TransaccionManualBody(BaseModel):
+    model_config = ConfigDict(strict=True, extra="forbid")
+
+    fecha: str  # YYYY-MM-DD (valida el Document)
+    descripcion: str = Field(min_length=1, max_length=300)
+    valor: str  # monto COP como string (regla 1)
+    tipo_flujo: TipoFlujo
+    rubro_id: str | None = None
+
+    @field_validator("tipo_flujo", mode="before")
+    @classmethod
+    def _cast_tipo(cls, v: object) -> object:
+        # strict=True no coerciona str→StrEnum; el cast explícito es el patrón
+        # del dominio. Un valor inválido lanza ValueError → 422.
+        return v if isinstance(v, TipoFlujo) else TipoFlujo(v)
+
+
+def _parse_valor(s: str) -> Decimal:
+    try:
+        v = Decimal(s)
+    except InvalidOperation:
+        raise HTTPException(422, "valor no es un decimal válido") from None
+    if v <= 0:
+        raise HTTPException(422, "valor debe ser > 0")
+    return v
+
+
+def _serializar(tx: Transaccion) -> dict:
+    return {
+        "id": str(tx.id),
+        "fecha": tx.fecha,
+        "descripcion": tx.descripcion,
+        "valor": money_str(tx.valor),
+        "tipo_flujo": tx.tipo_flujo.value,
+        "rubro_id": str(tx.rubro_id),
+        "mes_id": str(tx.mes_id),
+        "banco": tx.banco.value,
+        "id_banco": tx.id_banco,
+        "tardia": tx.tardia,
+    }
+
+
+@router.post("", status_code=201)
+async def crear_manual(
+    body: TransaccionManualBody,
+    idempotency_key: str = Header(
+        alias="Idempotency-Key", min_length=1, max_length=128
+    ),
+    user: User = Depends(require_permission("cargas:gestionar")),
+    _: None = Depends(verify_origin),
+):
+    valor = _parse_valor(body.valor)
+    req_hash = hashlib.sha256(
+        json.dumps(body.model_dump(), sort_keys=True).encode()
+    ).hexdigest()
+
+    # §1.12: scope (usuario, endpoint, key). El índice único respalda la carrera;
+    # mongomock no lo exige, pero el find_one previo cubre el flujo normal.
+    previa = await IdempotencyKey.find_one(
+        IdempotencyKey.usuario_id == user.id,
+        IdempotencyKey.endpoint == _ENDPOINT,
+        IdempotencyKey.key == idempotency_key,
+    )
+    if previa is not None:
+        if previa.request_hash != req_hash:
+            raise HTTPException(
+                422, "Idempotency-Key ya usada con un payload distinto"
+            )
+        if previa.response_status is None:
+            raise HTTPException(409, "petición con esta Idempotency-Key en curso")
+        # Replay: la respuesta ORIGINAL, con su status original (§1.12).
+        return JSONResponse(previa.response_body, status_code=previa.response_status)
+
+    marca = IdempotencyKey(
+        usuario_id=user.id,
+        endpoint=_ENDPOINT,
+        key=idempotency_key,
+        request_hash=req_hash,
+    )
+    await marca.insert()
+
+    try:
+        tx = await service.crear_transaccion_manual(
+            fecha=body.fecha,
+            descripcion=body.descripcion,
+            valor=valor,
+            tipo_flujo=body.tipo_flujo,
+            usuario_id=user.id,
+            rubro_id=body.rubro_id,
+        )
+    except service.TransaccionManualError as e:
+        await marca.delete()  # una petición fallida no quema la key
+        raise HTTPException(e.status, e.detalle) from e
+    except Exception:
+        await marca.delete()
+        raise
+
+    respuesta = _serializar(tx)
+    marca.response_status = 201
+    marca.response_body = respuesta
+    await marca.save()
+    return respuesta
diff --git a/backend/app/transacciones/service.py b/backend/app/transacciones/service.py
new file mode 100644
index 0000000..9a62221
--- /dev/null
+++ b/backend/app/transacciones/service.py
@@ -0,0 +1,102 @@
+# backend/app/transacciones/service.py
+"""Creación de transacciones manuales (US-10, F-04).
+
+MARCADO PARA AUDITORÍA KIMI (flujo crítico: crea movimientos de dinero).
+
+Reglas: id_banco = 'MAN-'+ULID (único por construcción → dos manuales idénticos
+coexisten, F-04); el mes de la fecha debe existir y NO estar cerrado (regla 4 —
+las tardías llegan con el flujo de cierre, Sprint 4); rubro explícito debe existir,
+estar activo y ser coherente con tipo_flujo (regla 7: no se adivina); sin rubro →
+'Por clasificar'. Evento `transaccion.clasificada` SOLO con rubro explícito (el
+catálogo cerrado no tiene 'creación manual'; declarado al gate Kimi — regla 11)."""
+
+from decimal import Decimal
+
+from beanie import PydanticObjectId
+
+from app.audit.events import AuditEvento
+from app.audit.service import emit_audit
+from app.core.time import now_utc
+from app.core.ulid import new_ulid
+from app.domain.bancos import Banco
+from app.domain.mes_control import EstadoMes, MesControl
+from app.domain.rubro import Rubro, TipoFlujo
+from app.domain.transaccion import Transaccion
+
+RUBRO_POR_CLASIFICAR = "Por clasificar"
+
+
+class TransaccionManualError(Exception):
+    def __init__(self, detalle: str, status: int = 422) -> None:
+        super().__init__(detalle)
+        self.detalle = detalle
+        self.status = status
+
+
+async def crear_transaccion_manual(
+    *,
+    fecha: str,
+    descripcion: str,
+    valor: Decimal,
+    tipo_flujo: TipoFlujo,
+    usuario_id: str,
+    rubro_id: str | None = None,
+) -> Transaccion:
+    mes = fecha[:7] + "-01"
+    mc = await MesControl.find_one(MesControl.mes == mes)
+    if mc is None:
+        raise TransaccionManualError(
+            f"el mes {mes[:7]} no tiene MesControl abierto (abrir el mes primero)"
+        )
+    if mc.estado is EstadoMes.CERRADO:
+        raise TransaccionManualError(
+            f"el mes {mes[:7]} está cerrado (regla 4); la transacción tardía "
+            "llega con el flujo de cierre (Sprint 4)",
+            status=409,
+        )
+
+    clasificada = rubro_id is not None
+    if clasificada:
+        rubro = await Rubro.get(PydanticObjectId(rubro_id))
+        if rubro is None or not rubro.activo:
+            raise TransaccionManualError("rubro inexistente o inactivo")
+        if rubro.tipo_flujo is not tipo_flujo:
+            raise TransaccionManualError(
+                f"rubro '{rubro.nombre}' es {rubro.tipo_flujo.value}, "
+                f"incoherente con tipo_flujo={tipo_flujo.value}"
+            )
+    else:
+        rubro = await Rubro.find_one(Rubro.nombre == RUBRO_POR_CLASIFICAR)
+        if rubro is None:
+            raise TransaccionManualError(
+                "falta el rubro de sistema 'Por clasificar' (correr semillas)",
+                status=500,
+            )
+
+    tx = Transaccion(
+        fecha=fecha,
+        descripcion=descripcion,
+        valor=valor,
+        tipo_flujo=tipo_flujo,
+        rubro_id=rubro.id,
+        mes_id=mc.id,
+        banco=Banco.MANUAL,
+        id_banco=f"MAN-{new_ulid()}",
+        clasificada_por=usuario_id if clasificada else None,
+        clasificada_at=now_utc() if clasificada else None,
+    )
+    await tx.insert()
+
+    if clasificada:
+        await emit_audit(
+            AuditEvento.transaccion_clasificada,
+            entidad="transaccion",
+            entidad_id=str(tx.id),
+            actor_id=usuario_id,
+            metadata={
+                "origen": "manual",
+                "rubro_id": str(rubro.id),
+                "valor": f"{valor:.2f}",
+            },
+        )
+    return tx
diff --git a/backend/tests/test_cargas_endpoint.py b/backend/tests/test_cargas_endpoint.py
new file mode 100644
index 0000000..bbb2fc0
--- /dev/null
+++ b/backend/tests/test_cargas_endpoint.py
@@ -0,0 +1,127 @@
+# backend/tests/test_cargas_endpoint.py
+"""Endpoints de cargas (Spec §1.6, F-22): POST /cargas (subir extracto) y GET /cargas.
+
+Los caminos de VALIDACIÓN corren en mongomock (fallan antes de tocar la transacción).
+El happy path del upload usa transacciones multi-doc → vive en test_carga.py
+(@requires_real_mongo, vía el servicio). F-22: solo .xlsx/.xls, .xlsm rechazado,
+límite 10 MB.
+"""
+
+from decimal import Decimal
+from io import BytesIO
+
+import httpx
+import openpyxl
+import pytest_asyncio
+from app.audit.service import configure_audit, reset_audit
+from app.auth import passwords, repository
+from app.auth.models import User
+from app.auth.roles import Role
+from app.config import get_settings
+from app.domain import DOMAIN_DOCUMENTS
+from app.domain.mes_control import MesControl
+from app.domain.rubro import Rubro
+from app.main import create_app
+from beanie import init_beanie
+from mongomock_motor import AsyncMongoMockClient
+
+PWD = "clave-larga-1234"
+
+
+@pytest_asyncio.fixture
+async def api(monkeypatch, tmp_path):
+    monkeypatch.setenv("APP_ENV", "development")
+    monkeypatch.setenv("JWT_SECRET", "x" * 40)
+    monkeypatch.setenv("COOKIE_SECURE", "False")
+    monkeypatch.setenv("ORIGINALES_DIR", str(tmp_path / "orig"))
+    monkeypatch.delenv("RUN_SCHEDULER", raising=False)
+    get_settings.cache_clear()
+
+    app = create_app()
+    c = AsyncMongoMockClient()
+    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
+    repository.configure_auth(c, "compas_test")
+    configure_audit(c, "compas_test")
+    await repository.create_user(
+        User(email="fin@roddos.com",
+             password_hash=passwords.hash_password(PWD), rol=Role.financiero)
+    )
+    await Rubro(
+        grupo="otros", nombre="Por clasificar", orden=98, es_sistema=True
+    ).insert()
+    await MesControl(mes="2026-03-01", saldo_inicial_caja=Decimal("0")).insert()
+
+    transport = httpx.ASGITransport(app=app)
+    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
+        yield ac
+    repository.reset_auth()
+    reset_audit()
+    get_settings.cache_clear()
+
+
+async def _h(ac) -> dict:
+    r = await ac.post(
+        "/api/v1/auth/login", json={"email": "fin@roddos.com", "password": PWD}
+    )
+    return {"Authorization": f"Bearer {r.json()['access_token']}"}
+
+
+def _xlsx_bbva() -> bytes:
+    wb = openpyxl.Workbook()
+    ws = wb.active
+    for i, hdr in enumerate(["FECHA DE OPERACIÓN", "CONCEPTO", "IMPORTE"], start=1):
+        ws.cell(row=14, column=i, value=hdr)
+    ws.cell(row=15, column=1, value="15-03-2026")
+    ws.cell(row=15, column=2, value="COMPRA")
+    ws.cell(row=15, column=3, value=-50000)
+    buf = BytesIO()
+    wb.save(buf)
+    return buf.getvalue()
+
+
+async def test_xlsm_rechazado(api):
+    # F-22: .xlsm (macros) se rechaza SIEMPRE, antes de parsear.
+    h = await _h(api)
+    r = await api.post(
+        "/api/v1/cargas",
+        files={"archivo": ("macro.xlsm", b"PK\x03\x04fake", "application/x-xlsm")},
+        headers=h,
+    )
+    assert r.status_code == 422
+    assert "xlsm" in r.json()["detail"].lower()
+
+
+async def test_extension_desconocida_rechazada(api):
+    h = await _h(api)
+    r = await api.post(
+        "/api/v1/cargas",
+        files={"archivo": ("datos.csv", b"a,b,c", "text/csv")},
+        headers=h,
+    )
+    assert r.status_code == 422
+
+
+async def test_limite_10mb(api):
+    # F-22: límite de tamaño ANTES de procesar.
+    h = await _h(api)
+    grande = b"x" * (10 * 1024 * 1024 + 1)
+    r = await api.post(
+        "/api/v1/cargas",
+        files={"archivo": ("ext.xlsx", grande, "application/octet-stream")},
+        headers=h,
+    )
+    assert r.status_code == 413
+
+
+async def test_sin_auth_401(api):
+    r = await api.post(
+        "/api/v1/cargas", files={"archivo": ("e.xlsx", b"PK", "application/x")}
+    )
+    assert r.status_code == 401
+
+
+async def test_listar_cargas_vacio(api):
+    h = await _h(api)
+    r = await api.get("/api/v1/cargas", headers=h)
+    assert r.status_code == 200
+    assert r.json() == {"items": [], "next_cursor": None}
diff --git a/backend/tests/test_db.py b/backend/tests/test_db.py
index a06811f..51d7e6c 100644
--- a/backend/tests/test_db.py
+++ b/backend/tests/test_db.py
@@ -19,7 +19,7 @@ async def test_init_beanie_registra_los_documents_de_dominio():
     from app.domain import DOMAIN_DOCUMENTS, Transaccion
 
     assert mongo.DOCUMENT_MODELS == DOMAIN_DOCUMENTS
-    assert len(DOMAIN_DOCUMENTS) == 5
+    assert len(DOMAIN_DOCUMENTS) == 6
     assert Transaccion in mongo.DOCUMENT_MODELS
     assert AuditLog not in mongo.DOCUMENT_MODELS
     client = AsyncMongoMockClient()
diff --git a/backend/tests/test_transacciones_manual.py b/backend/tests/test_transacciones_manual.py
new file mode 100644
index 0000000..8308b96
--- /dev/null
+++ b/backend/tests/test_transacciones_manual.py
@@ -0,0 +1,208 @@
+# backend/tests/test_transacciones_manual.py
+"""POST /api/v1/transacciones — transacción manual (US-10, F-04, Spec §1.12).
+
+MARCADO PARA AUDITORÍA KIMI (flujo crítico: crea movimientos de dinero).
+
+Reglas cubiertas:
+  - Regla 1: `valor` viaja como STRING en el JSON; un number float → 422 (strict).
+  - F-04: id_banco = 'MAN-'+ULID → dos manuales idénticos el mismo día coexisten.
+  - §1.12: Idempotency-Key OBLIGATORIA; misma key+mismo payload → replay (no
+    duplica); misma key+payload distinto → 422.
+  - RBAC: cargas:gestionar (consulta → 403).
+  - Regla 4: mes cerrado → 409 (tardías llegan con el flujo de cierre, Sprint 4).
+  - Regla 11: rubro explícito emite `transaccion.clasificada` (catálogo cerrado).
+"""
+
+from decimal import Decimal
+
+import httpx
+import pytest_asyncio
+from app.audit.service import configure_audit, reset_audit
+from app.auth import passwords, repository
+from app.auth.models import User
+from app.auth.roles import Role
+from app.config import get_settings
+from app.domain import DOMAIN_DOCUMENTS
+from app.domain.mes_control import EstadoMes, MesControl
+from app.domain.rubro import Rubro
+from app.domain.transaccion import Transaccion
+from app.main import create_app
+from beanie import init_beanie
+from mongomock_motor import AsyncMongoMockClient
+
+PWD = "clave-larga-1234"
+
+
+@pytest_asyncio.fixture
+async def api(monkeypatch):
+    monkeypatch.setenv("APP_ENV", "development")
+    monkeypatch.setenv("JWT_SECRET", "x" * 40)
+    monkeypatch.setenv("COOKIE_SECURE", "False")
+    monkeypatch.delenv("RUN_SCHEDULER", raising=False)
+    get_settings.cache_clear()
+
+    app = create_app()
+    c = AsyncMongoMockClient()
+    await init_beanie(database=c["compas_test"], document_models=DOMAIN_DOCUMENTS)
+    repository.configure_auth(c, "compas_test")
+    configure_audit(c, "compas_test")
+    for correo, rol in [
+        ("consulta@roddos.com", Role.consulta),
+        ("fin@roddos.com", Role.financiero),
+    ]:
+        await repository.create_user(
+            User(email=correo, password_hash=passwords.hash_password(PWD), rol=rol)
+        )
+    # Semillas mínimas del dominio.
+    await Rubro(
+        grupo="otros", nombre="Por clasificar", orden=98, es_sistema=True
+    ).insert()
+    await Rubro(
+        grupo="otros", nombre="Recaudo", tipo_flujo="ingreso", orden=99,
+        es_sistema=True,
+    ).insert()
+    await MesControl(mes="2026-03-01", saldo_inicial_caja=Decimal("0")).insert()
+    await MesControl(
+        mes="2026-01-01", saldo_inicial_caja=Decimal("0"), estado=EstadoMes.CERRADO
+    ).insert()
+
+    transport = httpx.ASGITransport(app=app)
+    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
+        yield ac, c
+    repository.reset_auth()
+    reset_audit()
+    get_settings.cache_clear()
+
+
+async def _token(ac, email="fin@roddos.com") -> dict:
+    r = await ac.post("/api/v1/auth/login", json={"email": email, "password": PWD})
+    assert r.status_code == 200
+    return {"Authorization": f"Bearer {r.json()['access_token']}"}
+
+
+def _body(**over):
+    base = {
+        "fecha": "2026-03-15",
+        "descripcion": "EGRESO EFECTIVO CAJA",
+        "valor": "50000",
+        "tipo_flujo": "egreso",
+    }
+    base.update(over)
+    return base
+
+
+async def _post(ac, h, body, key="k-001"):
+    return await ac.post(
+        "/api/v1/transacciones", json=body,
+        headers={**h, "Idempotency-Key": key},
+    )
+
+
+async def test_crea_manual_ok(api):
+    ac, _ = api
+    h = await _token(ac)
+    r = await _post(ac, h, _body())
+    assert r.status_code == 201
+    d = r.json()
+    assert d["banco"] == "manual"
+    assert d["id_banco"].startswith("MAN-")
+    assert d["valor"] == "50000.00"  # string, 2 decimales (regla 1)
+    assert isinstance(d["valor"], str)
+
+
+async def test_dos_manuales_identicos_coexisten(api):
+    # F-04 / US-10: mismo día, mismo valor, misma descripción → ambos entran.
+    ac, _ = api
+    h = await _token(ac)
+    r1 = await _post(ac, h, _body(), key="k-A")
+    r2 = await _post(ac, h, _body(), key="k-B")
+    assert r1.status_code == 201 and r2.status_code == 201
+    assert r1.json()["id_banco"] != r2.json()["id_banco"]
+    assert await Transaccion.find_all().count() == 2
+
+
+async def test_idempotency_key_obligatoria(api):
+    ac, _ = api
+    h = await _token(ac)
+    r = await ac.post("/api/v1/transacciones", json=_body(), headers=h)
+    assert r.status_code == 422
+
+
+async def test_replay_misma_key_mismo_payload(api):
+    # §1.12: replay de la respuesta original, NO segunda transacción.
+    ac, _ = api
+    h = await _token(ac)
+    r1 = await _post(ac, h, _body(), key="k-R")
+    r2 = await _post(ac, h, _body(), key="k-R")
+    assert r2.status_code == r1.status_code == 201
+    assert r2.json()["id_banco"] == r1.json()["id_banco"]
+    assert await Transaccion.find_all().count() == 1
+
+
+async def test_misma_key_payload_distinto_422(api):
+    ac, _ = api
+    h = await _token(ac)
+    await _post(ac, h, _body(), key="k-X")
+    r = await _post(ac, h, _body(valor="99999"), key="k-X")
+    assert r.status_code == 422
+
+
+async def test_valor_como_number_es_422(api):
+    # Regla 1: montos como string en la API; un number JSON se rechaza (strict).
+    ac, _ = api
+    h = await _token(ac)
+    r = await _post(ac, h, _body(valor=50000.0))
+    assert r.status_code == 422
+
+
+async def test_valor_no_positivo_422(api):
+    ac, _ = api
+    h = await _token(ac)
+    assert (await _post(ac, h, _body(valor="0"), key="kz")).status_code == 422
+    assert (await _post(ac, h, _body(valor="-5"), key="kn")).status_code == 422
+
+
+async def test_consulta_403(api):
+    ac, _ = api
+    h = await _token(ac, "consulta@roddos.com")
+    r = await _post(ac, h, _body())
+    assert r.status_code == 403
+
+
+async def test_mes_cerrado_409(api):
+    # Regla 4: el histórico es inmutable; la tardía llega en Sprint 4.
+    ac, _ = api
+    h = await _token(ac)
+    r = await _post(ac, h, _body(fecha="2026-01-15"))
+    assert r.status_code == 409
+
+
+async def test_mes_inexistente_422(api):
+    ac, _ = api
+    h = await _token(ac)
+    r = await _post(ac, h, _body(fecha="2026-06-15"))
+    assert r.status_code == 422
+
+
+async def test_rubro_explicito_emite_clasificada(api):
+    ac, c = api
+    h = await _token(ac)
+    recaudo = await Rubro.find_one(Rubro.nombre == "Recaudo")
+    r = await _post(ac, h, _body(
+        tipo_flujo="ingreso", rubro_id=str(recaudo.id), descripcion="ABONO CUOTA",
+    ))
+    assert r.status_code == 201
+    ev = await c["compas_test"]["audit_log"].find_one(
+        {"evento": "transaccion.clasificada"}
+    )
+    assert ev is not None
+    assert ev["metadata"]["origen"] == "manual"
+
+
+async def test_rubro_incoherente_con_tipo_422(api):
+    # Recaudo es ingreso; declararlo egreso es ambigüedad → 422, no se adivina.
+    ac, _ = api
+    h = await _token(ac)
+    recaudo = await Rubro.find_one(Rubro.nombre == "Recaudo")
+    r = await _post(ac, h, _body(tipo_flujo="egreso", rubro_id=str(recaudo.id)))
+    assert r.status_code == 422
diff --git a/backend/tests/test_ulid.py b/backend/tests/test_ulid.py
new file mode 100644
index 0000000..d850396
--- /dev/null
+++ b/backend/tests/test_ulid.py
@@ -0,0 +1,19 @@
+# backend/tests/test_ulid.py
+"""ULID (F-04): id_banco de transacciones manuales = 'MAN-'+ULID."""
+
+from app.core.ulid import CROCKFORD, new_ulid
+
+
+def test_largo_y_alfabeto():
+    u = new_ulid()
+    assert len(u) == 26
+    assert all(c in CROCKFORD for c in u)
+
+
+def test_unicos():
+    lote = {new_ulid() for _ in range(2000)}
+    assert len(lote) == 2000
+
+
+def test_man_prefijo_cabe_en_40():
+    assert len("MAN-" + new_ulid()) <= 40  # límite String(40) de id_banco (§1.5)
```
