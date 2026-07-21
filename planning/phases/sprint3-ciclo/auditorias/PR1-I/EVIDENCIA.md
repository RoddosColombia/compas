# EVIDENCIA — sprint3-ciclo · PR1-I (apertura del mes)

Rama `feat/ciclo-abrir-mes`, commit `274f47e` (SIN mergear).

## 1. pytest (suite local)
```
248 passed, 23 skipped (10 nuevos en test_ciclo_abrir_mes.py)
```

## 2. ruff
```
check: All checks passed! · format: 90 files already formatted
```

## 3. Protocolo
```
r1:0 | journal-entries:0 | estado-pending:0
```

## 4. CI de main (contexto)
```
run 29861083363: success (5 jobs — replica set en real-mongo, pip-audit tras CVE fix)
```

## 5. git diff --stat (main..274f47e)
```
backend/app/api/v1/__init__.py        |   2 +
 backend/app/ciclo/__init__.py         |   3 +
 backend/app/ciclo/router.py           | 121 +++++++++++++++++++++++
 backend/app/ciclo/service.py          |  66 +++++++++++++
 backend/tests/test_ciclo_abrir_mes.py | 178 ++++++++++++++++++++++++++++++++++
 5 files changed, 370 insertions(+)
```

## 6. Diff completo
```diff
diff --git a/backend/app/api/v1/__init__.py b/backend/app/api/v1/__init__.py
index eede760..bf6fe43 100644
--- a/backend/app/api/v1/__init__.py
+++ b/backend/app/api/v1/__init__.py
@@ -6,10 +6,12 @@ from fastapi import APIRouter
 from app.api.v1 import health
 from app.auth.router import router as auth_router
 from app.cargas.router import router as cargas_router
+from app.ciclo.router import router as ciclo_router
 from app.transacciones.router import router as transacciones_router
 
 api_router = APIRouter()
 api_router.include_router(health.router)
 api_router.include_router(auth_router)
 api_router.include_router(cargas_router)
+api_router.include_router(ciclo_router)
 api_router.include_router(transacciones_router)
diff --git a/backend/app/ciclo/__init__.py b/backend/app/ciclo/__init__.py
new file mode 100644
index 0000000..b603fd6
--- /dev/null
+++ b/backend/app/ciclo/__init__.py
@@ -0,0 +1,3 @@
+# backend/app/ciclo/__init__.py
+"""Ciclo mensual (Spec §1.3/§2.2/§2.4): apertura del mes (US-01). La propuesta,
+aprobación y cierre llegan en los siguientes incrementos (Sprint 3-4)."""
diff --git a/backend/app/ciclo/router.py b/backend/app/ciclo/router.py
new file mode 100644
index 0000000..85d60d6
--- /dev/null
+++ b/backend/app/ciclo/router.py
@@ -0,0 +1,121 @@
+# backend/app/ciclo/router.py
+"""POST /api/v1/meses (abrir mes, US-01) + GET /api/v1/meses.
+
+MARCADO PARA AUDITORÍA KIMI (flujo del ciclo mensual).
+
+RBAC §2.4: `ciclo:abrir` (financiero/directivo/admin). Regla 1: montos como
+STRING. El saldo inicial NO se edita por aquí después (eso es `ciclo:config`
++ step-up MFA, incremento futuro)."""
+
+from decimal import Decimal, InvalidOperation
+
+from fastapi import APIRouter, Depends, HTTPException
+from pydantic import BaseModel, ConfigDict, Field
+
+from app.auth.deps import require_permission
+from app.auth.models import User
+from app.auth.router import verify_origin
+from app.ciclo import service
+from app.core.money import money_str
+from app.domain.bancos import Banco
+from app.domain.mes_control import MesControl, SaldoBanco
+
+router = APIRouter(prefix="/meses", tags=["ciclo"])
+
+
+class SaldoBancoBody(BaseModel):
+    model_config = ConfigDict(strict=True, extra="forbid")
+
+    banco: str
+    saldo: str  # string (regla 1)
+    fecha_reporte: str
+
+
+class AbrirMesBody(BaseModel):
+    model_config = ConfigDict(strict=True, extra="forbid")
+
+    mes: str  # YYYY-MM-01 (valida el Document)
+    saldo_inicial_caja: str  # string (regla 1)
+    saldos_banco: list[SaldoBancoBody] = Field(default_factory=list)
+    ingresos_esperados_semana: str | None = None
+
+
+def _decimal(s: str, campo: str) -> Decimal:
+    try:
+        return Decimal(s)
+    except InvalidOperation:
+        raise HTTPException(422, f"{campo} no es un decimal válido") from None
+
+
+def _serializar(mc: MesControl) -> dict:
+    return {
+        "id": str(mc.id),
+        "mes": mc.mes,
+        "estado": mc.estado.value,
+        "saldo_inicial_caja": money_str(mc.saldo_inicial_caja),
+        "saldos_banco": [
+            {
+                "banco": s.banco.value,
+                "saldo": money_str(s.saldo),
+                "fecha_reporte": s.fecha_reporte,
+            }
+            for s in mc.saldos_banco
+        ],
+        "ingresos_esperados_semana": (
+            money_str(mc.ingresos_esperados_semana)
+            if mc.ingresos_esperados_semana is not None
+            else None
+        ),
+    }
+
+
+@router.post("", status_code=201)
+async def abrir_mes(
+    body: AbrirMesBody,
+    user: User = Depends(require_permission("ciclo:abrir")),
+    _: None = Depends(verify_origin),
+):
+    saldos: list[SaldoBanco] = []
+    for s in body.saldos_banco:
+        try:
+            banco = Banco(s.banco)
+        except ValueError:
+            raise HTTPException(422, f"banco desconocido: {s.banco}") from None
+        if banco is Banco.MANUAL:
+            raise HTTPException(422, "'manual' no es un banco de saldos (§1.3)")
+        try:
+            saldos.append(
+                SaldoBanco(
+                    banco=banco,
+                    saldo=_decimal(s.saldo, "saldo"),
+                    fecha_reporte=s.fecha_reporte,
+                )
+            )
+        except ValueError as e:
+            raise HTTPException(422, str(e)) from None
+
+    try:
+        mc = await service.abrir_mes(
+            mes=body.mes,
+            saldo_inicial_caja=_decimal(body.saldo_inicial_caja, "saldo_inicial_caja"),
+            saldos_banco=saldos,
+            ingresos_esperados_semana=(
+                _decimal(body.ingresos_esperados_semana, "ingresos_esperados_semana")
+                if body.ingresos_esperados_semana is not None
+                else None
+            ),
+            usuario_id=user.id,
+        )
+    except service.MesYaAbiertoError as e:
+        raise HTTPException(409, f"el mes {e.mes[:7]} ya está abierto") from e
+    except ValueError as e:  # validación del Document (mes no normalizado, etc.)
+        raise HTTPException(422, str(e)) from e
+    return _serializar(mc)
+
+
+@router.get("")
+async def listar_meses(
+    user: User = Depends(require_permission("dashboard:leer")),
+):
+    filas = await MesControl.find_all().sort(-MesControl.mes).to_list()
+    return {"items": [_serializar(m) for m in filas]}
diff --git a/backend/app/ciclo/service.py b/backend/app/ciclo/service.py
new file mode 100644
index 0000000..7690d7f
--- /dev/null
+++ b/backend/app/ciclo/service.py
@@ -0,0 +1,66 @@
+# backend/app/ciclo/service.py
+"""Apertura del mes (US-01).
+
+MARCADO PARA AUDITORÍA KIMI (flujo del ciclo mensual).
+
+Crea el MesControl (estado inicial `sugerido`) y emite `mes.creado` (regla 11).
+Política O1 (audit fail-closed en operaciones de estado del ciclo): si el emit
+falla, la apertura se COMPENSA (delete del mes) y el error se propaga — no queda
+un mes operable sin rastro de auditoría. La unicidad la garantiza el índice
+`mes_unico` (real) + verificación previa (mongomock/UX)."""
+
+from decimal import Decimal
+
+from pymongo.errors import DuplicateKeyError
+
+from app.audit.events import AuditEvento
+from app.audit.service import emit_audit
+from app.domain.mes_control import MesControl, SaldoBanco
+
+
+class MesYaAbiertoError(Exception):
+    def __init__(self, mes: str) -> None:
+        super().__init__(mes)
+        self.mes = mes
+
+
+async def abrir_mes(
+    *,
+    mes: str,
+    saldo_inicial_caja: Decimal,
+    saldos_banco: list[SaldoBanco],
+    ingresos_esperados_semana: Decimal | None,
+    usuario_id: str,
+) -> MesControl:
+    existente = await MesControl.find_one(MesControl.mes == mes)
+    if existente is not None:
+        raise MesYaAbiertoError(mes)
+
+    mc = MesControl(
+        mes=mes,
+        saldo_inicial_caja=saldo_inicial_caja,
+        saldos_banco=saldos_banco,
+        ingresos_esperados_semana=ingresos_esperados_semana,
+    )
+    try:
+        await mc.insert()
+    except DuplicateKeyError:  # carrera real: el índice único decide
+        raise MesYaAbiertoError(mes) from None
+
+    try:
+        await emit_audit(
+            AuditEvento.mes_creado,
+            entidad="mes",
+            entidad_id=str(mc.id),
+            actor_id=usuario_id,
+            metadata={
+                "mes": mes,
+                "saldo_inicial_caja": f"{saldo_inicial_caja:.2f}",
+                "bancos": [s.banco.value for s in saldos_banco],
+            },
+        )
+    except Exception:
+        # O1: sin auditoría no hay operación de ciclo → compensar y propagar.
+        await mc.delete()
+        raise
+    return mc
diff --git a/backend/tests/test_ciclo_abrir_mes.py b/backend/tests/test_ciclo_abrir_mes.py
new file mode 100644
index 0000000..cee4b5d
--- /dev/null
+++ b/backend/tests/test_ciclo_abrir_mes.py
@@ -0,0 +1,178 @@
+# backend/tests/test_ciclo_abrir_mes.py
+"""POST /api/v1/meses — apertura del mes (US-01, Spec §1.3/§2.4).
+
+MARCADO PARA AUDITORÍA KIMI (flujo del ciclo mensual).
+
+Reglas cubiertas:
+  - §2.4: `ciclo:abrir` = financiero/directivo/admin; consulta → 403.
+  - Regla 1: montos como STRING (number → 422); respuesta con money_str.
+  - Regla 2: mes normalizado al día 1 (YYYY-MM-01); otro día → 422.
+  - US-01 / regla 11: evento `mes.creado` en el catálogo; si el audit falla,
+    la apertura se COMPENSA (no queda mes sin rastro — política Kimi O1).
+  - Unicidad: mes ya abierto → 409 (índice único `mes_unico` en real).
+"""
+
+import httpx
+import pytest_asyncio
+from app.audit.service import configure_audit, reset_audit
+from app.auth import passwords, repository
+from app.auth.models import User
+from app.auth.roles import Role
+from app.config import get_settings
+from app.domain import DOMAIN_DOCUMENTS
+from app.domain.mes_control import MesControl
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
+        "mes": "2026-07-01",
+        "saldo_inicial_caja": "1500000",
+        "saldos_banco": [
+            {"banco": "bancolombia", "saldo": "2500000", "fecha_reporte": "2026-07-01"},
+        ],
+    }
+    base.update(over)
+    return base
+
+
+async def test_abrir_mes_201(api):
+    ac, _ = api
+    h = await _token(ac)
+    r = await ac.post("/api/v1/meses", json=_body(), headers=h)
+    assert r.status_code == 201
+    d = r.json()
+    assert d["mes"] == "2026-07-01"
+    assert d["estado"] == "sugerido"
+    assert d["saldo_inicial_caja"] == "1500000.00"  # string (regla 1)
+    assert d["saldos_banco"][0]["saldo"] == "2500000.00"
+    assert await MesControl.find_all().count() == 1
+
+
+async def test_mes_duplicado_409(api):
+    ac, _ = api
+    h = await _token(ac)
+    await ac.post("/api/v1/meses", json=_body(), headers=h)
+    r = await ac.post("/api/v1/meses", json=_body(), headers=h)
+    assert r.status_code == 409
+    assert await MesControl.find_all().count() == 1
+
+
+async def test_mes_no_normalizado_422(api):
+    ac, _ = api
+    h = await _token(ac)
+    r = await ac.post("/api/v1/meses", json=_body(mes="2026-07-15"), headers=h)
+    assert r.status_code == 422
+
+
+async def test_saldo_como_number_422(api):
+    # Regla 1: montos string; un number JSON se rechaza.
+    ac, _ = api
+    h = await _token(ac)
+    r = await ac.post(
+        "/api/v1/meses", json=_body(saldo_inicial_caja=1500000.0), headers=h
+    )
+    assert r.status_code == 422
+
+
+async def test_banco_invalido_422(api):
+    ac, _ = api
+    h = await _token(ac)
+    r = await ac.post(
+        "/api/v1/meses",
+        json=_body(
+            saldos_banco=[
+                {"banco": "davivienda", "saldo": "1", "fecha_reporte": "2026-07-01"}
+            ]
+        ),
+        headers=h,
+    )
+    assert r.status_code == 422
+
+
+async def test_consulta_403(api):
+    ac, _ = api
+    h = await _token(ac, "consulta@roddos.com")
+    r = await ac.post("/api/v1/meses", json=_body(), headers=h)
+    assert r.status_code == 403
+
+
+async def test_emite_mes_creado(api):
+    ac, c = api
+    h = await _token(ac)
+    r = await ac.post("/api/v1/meses", json=_body(), headers=h)
+    ev = await c["compas_test"]["audit_log"].find_one({"evento": "mes.creado"})
+    assert ev is not None
+    assert ev["entidad_id"] == r.json()["id"]
+
+
+async def test_audit_caido_compensa(api, monkeypatch):
+    # Política O1: sin auditoría no hay operación de ciclo → si emit falla,
+    # la apertura se revierte (no queda mes fantasma sin rastro). El error se
+    # propaga (ASGITransport lo re-lanza; en producción uvicorn responde 500).
+    import pytest
+    from app.ciclo import service as ciclo_service
+
+    async def _explota(*a, **k):
+        raise RuntimeError("audit caído")
+
+    monkeypatch.setattr(ciclo_service, "emit_audit", _explota)
+    ac, _ = api
+    h = await _token(ac)
+    with pytest.raises(RuntimeError, match="audit caído"):
+        await ac.post("/api/v1/meses", json=_body(), headers=h)
+    assert await MesControl.find_all().count() == 0  # compensado
+
+
+async def test_listar_meses(api):
+    ac, _ = api
+    h = await _token(ac)
+    await ac.post("/api/v1/meses", json=_body(mes="2026-06-01"), headers=h)
+    await ac.post("/api/v1/meses", json=_body(mes="2026-07-01"), headers=h)
+    r = await ac.get("/api/v1/meses", headers=h)
+    assert r.status_code == 200
+    meses = [m["mes"] for m in r.json()["items"]]
+    assert meses == ["2026-07-01", "2026-06-01"]  # desc
+
+
+async def test_listar_requiere_auth(api):
+    ac, _ = api
+    assert (await ac.get("/api/v1/meses")).status_code == 401
```
