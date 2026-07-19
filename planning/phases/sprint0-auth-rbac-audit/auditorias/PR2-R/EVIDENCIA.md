# EVIDENCIA — R-PR2 (auth): diff de líneas cambiadas + salidas

Diff `ce2cfab..f103a2d` (todos los hallazgos I-PR2 aplicados). Al final, salidas.


## diff

```
diff --git a/backend/app/auth/models.py b/backend/app/auth/models.py
index fb1ead9..870c25e 100644
--- a/backend/app/auth/models.py
+++ b/backend/app/auth/models.py
@@ -48,6 +48,13 @@ class User(BaseModel):
     created_at: datetime = Field(default_factory=now_utc)
     updated_at: datetime = Field(default_factory=now_utc)
 
+    @field_validator("email", mode="before")
+    @classmethod
+    def _normaliza_email(cls, v: object) -> object:
+        # L5: normalizar en ESCRITURA (no solo en login); si no, A@Roddos.com
+        # queda inlogueable. Unicidad por el índice sobre el valor normalizado.
+        return v.strip().lower() if isinstance(v, str) else v
+
     @field_validator("rol", mode="before")
     @classmethod
     def _cast_rol(cls, v: object) -> Role:
diff --git a/backend/app/auth/repository.py b/backend/app/auth/repository.py
index 5d6190e..ce0975d 100644
--- a/backend/app/auth/repository.py
+++ b/backend/app/auth/repository.py
@@ -140,10 +140,13 @@ async def rotate_refresh_session(jti: str) -> bool:
     return doc is not None
 
 
-async def revoke_family(family_id: str) -> None:
-    await _col(REFRESH_SESSIONS_COLLECTION).update_many(
-        {"family_id": family_id}, {"$set": {"revocado": True}}
+async def revoke_family(family_id: str) -> int:
+    """Revoca la familia y devuelve cuántas sesiones NO-revocadas pasó a revocadas
+    (para emitir el evento solo en la transición — Kimi H5)."""
+    res = await _col(REFRESH_SESSIONS_COLLECTION).update_many(
+        {"family_id": family_id, "revocado": False}, {"$set": {"revocado": True}}
     )
+    return getattr(res, "modified_count", 0)
 
 
 # ── Denylist ───────────────────────────────────────────────────────────
@@ -159,7 +162,9 @@ async def denylist_contains(jti: str) -> bool:
 
 # ── Rate limit por IP ──────────────────────────────────────────────────
 async def register_ip_attempt(ip: str, *, window_min: int) -> int:
-    """Incrementa el contador de intentos de la IP en la ventana y devuelve el total."""
+    """Incrementa el contador de intentos de la IP en la ventana y devuelve el total.
+    El TTL (expires_at + índice expireAfterSeconds:0) reinicia la ventana; sin ese
+    índice el contador sería monótono para siempre (Kimi L4)."""
     col = _col(LOGIN_THROTTLE_COLLECTION)
     doc = await col.find_one_and_update(
         {"_id": f"ip:{ip}"},
@@ -171,3 +176,9 @@ async def register_ip_attempt(ip: str, *, window_min: int) -> int:
         return_document=True,
     )
     return doc.get("count", 1) if doc else 1
+
+
+async def reset_ip_attempts(ip: str) -> None:
+    """Libera el cupo de la IP tras un login exitoso (Kimi H1): así una ráfaga
+    legítima desde una NAT de oficina no se auto-bloquea con 429."""
+    await _col(LOGIN_THROTTLE_COLLECTION).delete_one({"_id": f"ip:{ip}"})
diff --git a/backend/app/auth/router.py b/backend/app/auth/router.py
index f6c3b9d..ccc00cc 100644
--- a/backend/app/auth/router.py
+++ b/backend/app/auth/router.py
@@ -36,6 +36,21 @@ def verify_origin(request: Request, settings: Settings = Depends(_settings)) ->
         raise HTTPException(403, "Origin no permitido.")
 
 
+def client_ip(request: Request) -> str:
+    """IP real del cliente tras Cloudflare→Render (Kimi L2). `request.client.host`
+    a secas sería la IP del proxy → un solo bucket para todos (rate limit inútil y
+    DoS colectivo). Preferimos `CF-Connecting-IP` (canónica de Cloudflare), luego el
+    primer salto de `X-Forwarded-For`, y por último el peer. Requiere que el origen
+    Render solo sea alcanzable vía Cloudflare + `uvicorn --proxy-headers` (RUNBOOK)."""
+    cf = request.headers.get("cf-connecting-ip")
+    if cf:
+        return cf.strip()
+    xff = request.headers.get("x-forwarded-for")
+    if xff:
+        return xff.split(",")[0].strip()
+    return request.client.host if request.client else "unknown"
+
+
 def _set_refresh_cookie(response: Response, settings: Settings, token: str) -> None:
     response.set_cookie(
         REFRESH_COOKIE,
@@ -56,7 +71,7 @@ async def login(
     settings: Settings = Depends(_settings),
     _: None = Depends(verify_origin),
 ):
-    ip = request.client.host if request.client else "unknown"
+    ip = client_ip(request)
     try:
         pair = await service.login(
             settings, email=body.email, password=body.password, ip=ip
diff --git a/backend/app/auth/service.py b/backend/app/auth/service.py
index bbc234c..ecd5a72 100644
--- a/backend/app/auth/service.py
+++ b/backend/app/auth/service.py
@@ -44,7 +44,14 @@ async def _safe_emit(evento: AuditEvento, **kw) -> None:
     try:
         await emit_audit(evento, **kw)
     except Exception:  # noqa: BLE001 — auth no debe fallar por el canal de audit (O1)
+        # H3: registrar Y alertar (Sentry si está), no tragar en silencio.
         logger.error("no se pudo emitir %s", evento, exc_info=True)
+        try:
+            import sentry_sdk
+
+            sentry_sdk.capture_exception()
+        except ImportError:
+            pass
 
 
 def _issue_pair(
@@ -92,21 +99,30 @@ async def login(settings: Settings, *, email: str, password: str, ip: str) -> To
     email = email.strip().lower()
     user = await repository.get_user_by_email(email)
 
-    # Anti-enumeración: si no existe, gastamos el mismo tiempo con el hash dummy.
+    # Anti-enumeración: si no existe, gastamos el mismo tiempo con el hash dummy (L1).
     if user is None:
         passwords.verify_password(password, passwords.DUMMY_HASH)
         await _safe_emit(
-            AuditEvento.user_login_fallido, entidad="user", metadata={"email": email}
+            AuditEvento.user_login_fallido,
+            entidad="user",
+            metadata={"email": email, "ip": ip},
         )
         raise AuthError(_INVALID)
 
-    bloqueado = user.locked_until is not None and user.locked_until > now_utc()
-    if (
-        bloqueado
-        or not user.activo
-        or not passwords.verify_password(password, user.password_hash)
-    ):
-        # Solo cuenta como fallo real (no si ya estaba bloqueado/inactivo).
+    now = now_utc()
+    # L6: si el bloqueo ya expiró, la condena se cumplió → ventana nueva (reset ANTES
+    # de evaluar; si no, un fallo tras la expiración re-bloquea con 6≥5).
+    if user.locked_until is not None and user.locked_until <= now:
+        await repository.reset_failed_login(user.id)
+        user.failed_attempts = 0
+        user.locked_until = None
+
+    bloqueado = user.locked_until is not None and user.locked_until > now
+    # L1: verificar SIEMPRE (una vez), incluso si está bloqueado/inactivo → sin oráculo
+    # de timing (el cortocircuito del `or` delataba la cuenta con un 401 inmediato).
+    password_ok = passwords.verify_password(password, user.password_hash)
+
+    if bloqueado or not user.activo or not password_ok:
         if user.activo and not bloqueado:
             await repository.register_failed_login(
                 user.id,
@@ -114,21 +130,25 @@ async def login(settings: Settings, *, email: str, password: str, ip: str) -> To
                 lock_min=settings.login_lock_min,
             )
             refreshed = await repository.get_user_by_email(email)
-            if (
-                refreshed
-                and refreshed.locked_until
-                and refreshed.failed_attempts >= settings.login_max_intentos
-            ):
+            # H5: emitir bloqueado SOLO en la transición exacta (== max).
+            if refreshed and refreshed.failed_attempts == settings.login_max_intentos:
                 await _safe_emit(
-                    AuditEvento.user_bloqueado, entidad="user", entidad_id=user.id
+                    AuditEvento.user_bloqueado,
+                    entidad="user",
+                    entidad_id=user.id,
+                    metadata={"ip": ip},
                 )
         await _safe_emit(
-            AuditEvento.user_login_fallido, entidad="user", entidad_id=user.id
+            AuditEvento.user_login_fallido,
+            entidad="user",
+            entidad_id=user.id,
+            metadata={"ip": ip},
         )
         raise AuthError(_INVALID)
 
     # Éxito.
     await repository.reset_failed_login(user.id)
+    await repository.reset_ip_attempts(ip)  # H1: liberar el cupo IP en éxito
     family_id = uuid4().hex
     pair, session = _issue_pair(settings, user, family_id, now_utc())
     await repository.create_refresh_session(session)
@@ -142,6 +162,19 @@ async def login(settings: Settings, *, email: str, password: str, ip: str) -> To
     return pair
 
 
+async def _flag_reuse(family_id: str, sub: str) -> None:
+    """Revoca la familia y emite user.bloqueado SOLO si hubo transición (H5:
+    evita el doble evento por carrera o por replays sucesivos)."""
+    revocadas = await repository.revoke_family(family_id)
+    if revocadas > 0:
+        await _safe_emit(
+            AuditEvento.user_bloqueado,
+            entidad="user",
+            entidad_id=sub,
+            metadata={"motivo": "reuso_refresh"},
+        )
+
+
 async def refresh(settings: Settings, *, refresh_token: str) -> TokenPair:
     if not settings.jwt_secret:
         raise AuthError("servicio de auth no configurado", status=500)
@@ -165,13 +198,7 @@ async def refresh(settings: Settings, *, refresh_token: str) -> TokenPair:
     session = await repository.get_refresh_session(jti)
     if session is None or session.revocado:
         # jti desconocido o familia revocada → tratar como reuso: revocar familia.
-        await repository.revoke_family(family_id)
-        await _safe_emit(
-            AuditEvento.user_bloqueado,
-            entidad="user",
-            entidad_id=sub,
-            metadata={"motivo": "reuso_refresh"},
-        )
+        await _flag_reuse(family_id, sub)
         raise AuthError(_INVALID)
 
     now = now_utc()
@@ -186,13 +213,7 @@ async def refresh(settings: Settings, *, refresh_token: str) -> TokenPair:
     # Rotación ATÓMICA. Si perdemos (ya rotado) → REUSO → revocar familia.
     gano = await repository.rotate_refresh_session(jti)
     if not gano:
-        await repository.revoke_family(family_id)
-        await _safe_emit(
-            AuditEvento.user_bloqueado,
-            entidad="user",
-            entidad_id=sub,
-            metadata={"motivo": "reuso_refresh"},
-        )
+        await _flag_reuse(family_id, sub)
         raise AuthError(_INVALID)
 
     # Nueva sesión en la MISMA familia (family_created_at heredado → TTL estable).
diff --git a/backend/app/main.py b/backend/app/main.py
index 0b61993..4cd81fa 100644
--- a/backend/app/main.py
+++ b/backend/app/main.py
@@ -20,6 +20,44 @@ from app.db import mongo
 
 logger = logging.getLogger("compas")
 
+# Campos de dominio que NUNCA deben salir a Sentry (STACK §7, F-23).
+_PII_KEYS = {
+    "descripcion",
+    "proveedor",
+    "acreedor",
+    "valor",
+    "authorization",
+    "password",
+}
+
+
+def _scrub_pii(event: dict, _hint: dict) -> dict:
+    """before_send de Sentry: elimina campos sensibles antes de enviar."""
+    req = event.get("request", {})
+    if isinstance(req.get("headers"), dict):
+        req["headers"] = {
+            k: v for k, v in req["headers"].items() if k.lower() not in _PII_KEYS
+        }
+    return event
+
+
+def _init_sentry(settings) -> None:
+    """Inicializa Sentry si hay DSN y el SDK está instalado (H3). send_default_pii=False
+    + scrubbing. Import guardado: dev/tests sin el paquete no fallan."""
+    if not settings.sentry_dsn:
+        return
+    try:
+        import sentry_sdk
+    except ImportError:
+        logger.warning("SENTRY_DSN presente pero sentry_sdk no instalado.")
+        return
+    sentry_sdk.init(
+        dsn=settings.sentry_dsn,
+        environment=settings.app_env,
+        send_default_pii=False,
+        before_send=_scrub_pii,
+    )
+
 
 @asynccontextmanager
 async def lifespan(app: FastAPI):
@@ -32,6 +70,19 @@ async def lifespan(app: FastAPI):
             "Los jobs viven solo en el worker compas-jobs."
         )
 
+    # L3 (Kimi): fail-fast del secreto JWT fuera de dev — mismo principio que C-01.
+    # Sin esto la app arranca "sana" (health no toca auth) y cada login da 500.
+    if settings.app_env != "development" and (
+        not settings.jwt_secret or len(settings.jwt_secret) < 32
+    ):
+        raise RuntimeError(
+            "JWT_SECRET requerido y >= 32 bytes fuera de dev (Spec §8.1)."
+        )
+
+    _init_sentry(
+        settings
+    )  # H3: observabilidad de errores (incl. fallos del canal audit)
+
     # Cliente Motor perezoso (no conecta hasta el primer comando) → el web
     # arranca aunque Mongo esté caído; la liveness no depende de la BD.
     client = mongo.create_client(settings.mongodb_uri_compas)
diff --git a/backend/requirements.txt b/backend/requirements.txt
index 2846a62..525897f 100644
--- a/backend/requirements.txt
+++ b/backend/requirements.txt
@@ -12,3 +12,4 @@ openpyxl==3.1.5
 APScheduler==3.11.2
 bcrypt==5.0.0
 PyJWT==2.12.1
+sentry-sdk>=2.0,<3.0
diff --git a/backend/tests/test_audit_failfast.py b/backend/tests/test_audit_failfast.py
index 6d6fe8c..26a5235 100644
--- a/backend/tests/test_audit_failfast.py
+++ b/backend/tests/test_audit_failfast.py
@@ -11,6 +11,9 @@ from fastapi.testclient import TestClient
 
 def test_arranque_falla_sin_uri_audit_fuera_de_dev(monkeypatch):
     monkeypatch.setenv("APP_ENV", "staging")
+    monkeypatch.setenv(
+        "JWT_SECRET", "x" * 40
+    )  # pasa el fail-fast de JWT (L3) para llegar al de audit
     monkeypatch.delenv("MONGODB_URI_AUDIT", raising=False)
     monkeypatch.delenv("RUN_SCHEDULER", raising=False)
     get_settings.cache_clear()
@@ -21,6 +24,19 @@ def test_arranque_falla_sin_uri_audit_fuera_de_dev(monkeypatch):
     get_settings.cache_clear()
 
 
+def test_arranque_falla_sin_jwt_secret_fuera_de_dev(monkeypatch):
+    # L3 (Kimi): mismo principio que C-01, aplicado a JWT_SECRET.
+    monkeypatch.setenv("APP_ENV", "staging")
+    monkeypatch.delenv("JWT_SECRET", raising=False)
+    monkeypatch.delenv("RUN_SCHEDULER", raising=False)
+    get_settings.cache_clear()
+    app = create_app()
+    with pytest.raises(RuntimeError, match="JWT_SECRET"):
+        with TestClient(app):
+            pass
+    get_settings.cache_clear()
+
+
 def test_arranque_ok_en_dev_sin_uri_audit(monkeypatch):
     """En dev SÍ cae a la conexión general (con warning), sin fallar."""
     monkeypatch.setenv("APP_ENV", "development")
diff --git a/backend/tests/test_auth_endpoints.py b/backend/tests/test_auth_endpoints.py
index 711c5d7..726cd33 100644
--- a/backend/tests/test_auth_endpoints.py
+++ b/backend/tests/test_auth_endpoints.py
@@ -88,3 +88,56 @@ async def test_logout_revoca(api):
     # tras logout, el refresh (cookie aún presente en el cliente) ya no sirve
     r = await api.post("/api/v1/auth/refresh")
     assert r.status_code == 401
+
+
+async def _build(monkeypatch, **env):
+    for k, v in env.items():
+        monkeypatch.setenv(k, v)
+    monkeypatch.delenv("RUN_SCHEDULER", raising=False)
+    get_settings.cache_clear()
+    app = create_app()
+    c = AsyncMongoMockClient()
+    repository.configure_auth(c, "compas_test")
+    configure_audit(c, "compas_test")
+    await repository.create_user(
+        User(
+            email="a@roddos.com",
+            password_hash=passwords.hash_password(PWD),
+            rol=Role.admin,
+        )
+    )
+    return app
+
+
+async def test_verify_origin_bloquea_fuera_de_dev(monkeypatch):
+    # H4: la defensa verify_origin nunca se ejercía (tests en dev). Aquí sí.
+    app = await _build(
+        monkeypatch, APP_ENV="staging", JWT_SECRET="x" * 40, COOKIE_SECURE="False"
+    )
+    transport = httpx.ASGITransport(app=app)
+    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
+        r = await ac.post(
+            "/api/v1/auth/login",
+            json={"email": "a@roddos.com", "password": PWD},
+            headers={"Origin": "https://evil.example"},
+        )
+    repository.reset_auth()
+    reset_audit()
+    get_settings.cache_clear()
+    assert r.status_code == 403
+
+
+async def test_cookie_secure_cuando_configurado(monkeypatch):
+    app = await _build(
+        monkeypatch, APP_ENV="development", JWT_SECRET="x" * 40, COOKIE_SECURE="True"
+    )
+    transport = httpx.ASGITransport(app=app)
+    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
+        r = await ac.post(
+            "/api/v1/auth/login", json={"email": "a@roddos.com", "password": PWD}
+        )
+    repository.reset_auth()
+    reset_audit()
+    get_settings.cache_clear()
+    assert r.status_code == 200
+    assert "secure" in " ".join(r.headers.get_list("set-cookie")).lower()
diff --git a/backend/tests/test_auth_indexes.py b/backend/tests/test_auth_indexes.py
new file mode 100644
index 0000000..2c42840
--- /dev/null
+++ b/backend/tests/test_auth_indexes.py
@@ -0,0 +1,18 @@
+# backend/tests/test_auth_indexes.py
+"""Existencia de los índices de auth contra Mongo REAL (Kimi L4).
+
+mongomock NO exige índices → un CI solo-mongomock daría verde aunque falten (y el TTL
+del rate-limit por IP no expiraría: 429 permanente). Este test corre tras
+`scripts/create_auth_indexes.py` en el CI de la Sesión 3."""
+
+import pytest
+
+pytestmark = pytest.mark.requires_real_mongo
+
+
+def test_indices_de_auth_existen_tras_el_script():
+    # Verificará: users.email único; refresh_sessions.jti único + family_id + TTL;
+    # jwt_denylist.jti único + TTL; login_throttle TTL (expireAfterSeconds:0).
+    raise AssertionError(
+        "Pendiente CI Sesión 3: requiere mongod real + create_auth_indexes.py."
+    )
diff --git a/backend/tests/test_auth_service.py b/backend/tests/test_auth_service.py
index 3439d35..d4d3edd 100644
--- a/backend/tests/test_auth_service.py
+++ b/backend/tests/test_auth_service.py
@@ -123,3 +123,90 @@ async def test_rate_limit_por_ip(client):
     with pytest.raises(service.AuthError) as ei:
         await service.login(s, email="a@roddos.com", password=PWD, ip="9.9.9.9")
     assert ei.value.status == 429  # bloqueado por IP antes de validar credenciales
+
+
+async def test_login_exitoso_libera_cupo_ip(client):
+    # H1: el éxito borra el contador de la IP → una ráfaga legítima no se auto-bloquea.
+    s = _settings(login_ip_max=3)
+    await service.login(s, email="a@roddos.com", password=PWD, ip="5.5.5.5")
+    doc = await client["compas_test"]["login_throttle"].find_one({"_id": "ip:5.5.5.5"})
+    assert doc is None
+
+
+async def test_lock_expirado_da_ventana_nueva(client):
+    # L6: con el lock ya vencido, un login correcto entra (reset previo), no re-bloquea.
+    from datetime import timedelta
+
+    from app.core.time import now_utc
+
+    await client["compas_test"]["users"].update_one(
+        {"email": "a@roddos.com"},
+        {
+            "$set": {
+                "failed_attempts": 5,
+                "locked_until": now_utc() - timedelta(minutes=1),
+            }
+        },
+    )
+    s = _settings()
+    pair = await service.login(s, email="a@roddos.com", password=PWD, ip="1.1.1.1")
+    assert pair.access_token
+
+
+async def test_refresh_idle_expira(client):
+    from datetime import timedelta
+
+    from app.core.time import now_utc
+
+    s = _settings()
+    pair = await service.login(s, email="a@roddos.com", password=PWD, ip="1.1.1.1")
+    jti = tokens.decode_token(
+        s.jwt_secret, pair.refresh_token, expected_type="refresh"
+    )["jti"]
+    await client["compas_test"]["refresh_sessions"].update_one(
+        {"jti": jti}, {"$set": {"ultimo_uso": now_utc() - timedelta(hours=13)}}
+    )
+    with pytest.raises(service.AuthError):
+        await service.refresh(s, refresh_token=pair.refresh_token)
+
+
+async def test_refresh_max_vida_expira(client):
+    from datetime import timedelta
+
+    from app.core.time import now_utc
+
+    s = _settings()
+    pair = await service.login(s, email="a@roddos.com", password=PWD, ip="1.1.1.1")
+    jti = tokens.decode_token(
+        s.jwt_secret, pair.refresh_token, expected_type="refresh"
+    )["jti"]
+    await client["compas_test"]["refresh_sessions"].update_one(
+        {"jti": jti}, {"$set": {"expires_at": now_utc() - timedelta(seconds=1)}}
+    )
+    with pytest.raises(service.AuthError):
+        await service.refresh(s, refresh_token=pair.refresh_token)
+
+
+async def test_tv_desincronizado_invalida_refresh(client):
+    s = _settings()
+    pair = await service.login(s, email="a@roddos.com", password=PWD, ip="1.1.1.1")
+    u = await repository.get_user_by_email("a@roddos.com")
+    await repository.set_token_version(u.id, u.token_version + 1)
+    with pytest.raises(service.AuthError):
+        await service.refresh(s, refresh_token=pair.refresh_token)
+
+
+async def test_logout_con_access_expirado_lo_deniega(client):
+    from datetime import timedelta
+
+    s = _settings()
+    expirado = tokens.create_access_token(
+        s.jwt_secret, sub="507f1f77bcf86cd799439011", tv=1, ttl=timedelta(seconds=-60)
+    )
+    jti = tokens.decode_token(
+        s.jwt_secret, expirado, expected_type="access", verify_exp=False
+    )["jti"]
+    await service.logout(
+        s, access_token=expirado, refresh_token=None
+    )  # H-6: no debe fallar
+    assert await repository.denylist_contains(jti) is True
diff --git a/docs/RUNBOOK-INFRA.md b/docs/RUNBOOK-INFRA.md
index 098a01f..1a08130 100644
--- a/docs/RUNBOOK-INFRA.md
+++ b/docs/RUNBOOK-INFRA.md
@@ -56,6 +56,7 @@
 
 - [ ] `compas.roddos.com` → Vercel · `api.compas.roddos.com` → Render
 - [ ] TLS full-strict · WAF básico · HSTS
+- [ ] **Restringir el origen Render a IPs de Cloudflare** (firewall / Authenticated Origin Pulls) para que `CF-Connecting-IP` no sea spoofeable (Kimi L2). El backend corre con `uvicorn --proxy-headers` y lee la IP real de ese header.
 
 ## 6. S3 (cuenta AWS existente)
 
diff --git a/render.yaml b/render.yaml
index 3043938..05789c8 100644
--- a/render.yaml
+++ b/render.yaml
@@ -14,7 +14,10 @@ services:
     autoDeploy: false           # producción solo por tag + reviewer (F-32)
     rootDir: backend
     buildCommand: pip install -r requirements.txt
-    startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 2
+    # --proxy-headers: honra X-Forwarded-* del edge. La IP real del cliente se lee en
+    # código vía CF-Connecting-IP (Kimi L2); el origen DEBE quedar restringido a IPs de
+    # Cloudflare (RUNBOOK §5) para que ese header no sea spoofeable.
+    startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 2 --proxy-headers
     healthCheckPath: /health
     envVars:
       - key: RUN_SCHEDULER
@@ -79,7 +82,7 @@ services:
     autoDeploy: true            # staging SÍ auto-despliega desde main
     rootDir: backend
     buildCommand: pip install -r requirements.txt
-    startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT
+    startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers
     healthCheckPath: /health
     envVars:
       - key: RUN_SCHEDULER
diff --git a/scripts/create_auth_indexes.py b/scripts/create_auth_indexes.py
new file mode 100644
index 0000000..d35e498
--- /dev/null
+++ b/scripts/create_auth_indexes.py
@@ -0,0 +1,48 @@
+#!/usr/bin/env python
+"""Crea (idempotente) los índices de auth. Kimi L4.
+
+Sin estos índices: el TTL de login_throttle no existe → el contador por IP es
+MONÓTONO para siempre (429 permanente); email/jti no serían únicos; el refresh no
+expiraría. mongomock no exige índices, así que el CI verde NO lo detecta → este
+script + un test @requires_real_mongo de existencia son el control real.
+
+Fuente única de verdad: AUTH_INDEXES en app/auth/models.py (no duplicar aquí).
+
+Uso:
+    python scripts/create_auth_indexes.py "<MONGODB_URI>" [db=compas]
+Lo corre el operador (RUNBOOK) y el CI de la Sesión 3.
+"""
+
+from __future__ import annotations
+
+import sys
+
+from pymongo import MongoClient
+
+# El script vive en scripts/ (fuera del paquete); importamos el modelo por ruta.
+sys.path.insert(0, "backend")
+from app.auth.models import AUTH_INDEXES  # noqa: E402
+
+
+def main() -> None:
+    if len(sys.argv) < 2:
+        sys.exit('Uso: python scripts/create_auth_indexes.py "<MONGODB_URI>" [db]')
+    uri = sys.argv[1]
+    db_name = sys.argv[2] if len(sys.argv) > 2 else "compas"
+    db = MongoClient(uri)[db_name]
+
+    for coleccion, indices in AUTH_INDEXES.items():
+        for idx in indices:
+            kwargs: dict = {"name": idx["name"]}
+            if idx.get("unique"):
+                kwargs["unique"] = True
+            if "expireAfterSeconds" in idx:
+                kwargs["expireAfterSeconds"] = idx["expireAfterSeconds"]
+            db[coleccion].create_index(idx["keys"], **kwargs)
+            print(f"[{coleccion}] índice {idx['name']} asegurado ({kwargs}).")
+
+    print("Índices de auth OK (idempotente).")
+
+
+if __name__ == "__main__":
+    main()
```


## salida: pytest -q

```
...........sss.....s......s.....................................s....    [100%]
=========================== short test summary info ===========================
SKIPPED [3] tests\test_audit_immutable.py: requiere Mongo real; correr con: pytest -m requires_real_mongo
SKIPPED [1] tests\test_auth_concurrency.py: requiere Mongo real; correr con: pytest -m requires_real_mongo
SKIPPED [1] tests\test_auth_indexes.py: requiere Mongo real; correr con: pytest -m requires_real_mongo
SKIPPED [1] tests\test_real_mongo_marker.py:11: requiere Mongo real; correr con: pytest -m requires_real_mongo
63 passed, 6 skipped in 11.18s
```


## salida: pytest -q -m requires_real_mongo (deben FALLAR)

```
FFFFFF                                                                   [100%]
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
_______________ test_rotacion_exactamente_una_bajo_concurrencia _______________

    def test_rotacion_exactamente_una_bajo_concurrencia():
>       raise AssertionError("Pendiente CI Sesión 3: requiere mongod real (atomicidad).")
E       AssertionError: Pendiente CI Sesión 3: requiere mongod real (atomicidad).

tests\test_auth_concurrency.py:17: AssertionError
_________________ test_indices_de_auth_existen_tras_el_script _________________

    def test_indices_de_auth_existen_tras_el_script():
        # Verificará: users.email único; refresh_sessions.jti único + family_id + TTL;
        # jwt_denylist.jti único + TTL; login_throttle TTL (expireAfterSeconds:0).
>       raise AssertionError(
            "Pendiente CI Sesión 3: requiere mongod real + create_auth_indexes.py."
        )
E       AssertionError: Pendiente CI Sesión 3: requiere mongod real + create_auth_indexes.py.

tests\test_auth_indexes.py:16: AssertionError
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
FAILED tests/test_auth_concurrency.py::test_rotacion_exactamente_una_bajo_concurrencia
FAILED tests/test_auth_indexes.py::test_indices_de_auth_existen_tras_el_script
FAILED tests/test_real_mongo_marker.py::test_placeholder_dedup_indice_unico_parcial
6 failed, 63 deselected in 0.20s
```


## salida: ruff check .

```
All checks passed!
```

