# EVIDENCIA — sprint0b-dominio-mfa · PR2-I

Rama `sprint0b-pr2-mfa`, commits `29bf705`+`d6b96c3`+`385682a`. Código real + salidas (no descripciones).

## 1. pytest (suite completa)

```
164 passed, 9 skipped, 9 warnings in ~125s
SKIPPED (todos @requires_real_mongo): test_domain_indexes[3], test_audit_immutable[3], test_auth_concurrency[1], test_auth_indexes[1], test_real_mongo_marker[1]
Incluye: test_auth_mfa.py(12) test_auth_hibp.py(8) test_auth_mfa_flow.py(10) test_auth_mfa_endpoints.py(4) test_audit_failfast.py(4, +MFA)
```

## 2. ruff

```
All checks passed!
```

## 3. Protocolo de commit

```
app.alegra.com/api/r1: 0
journal-entries: 0
estado.*pending: 0
```

## 4. git diff --stat (0cc8ee5..385682a)

```
 backend/app/auth/deps.py                 |  36 +++++-
 backend/app/auth/mfa.py                  |  68 ++++++++++++
 backend/app/auth/models.py               |   4 +
 backend/app/auth/passwords.py            |  59 +++++++++-
 backend/app/auth/repository.py           |  68 ++++++++++++
 backend/app/auth/router.py               |  86 ++++++++++++++-
 backend/app/auth/service.py              | 158 +++++++++++++++++++++++++-
 backend/app/auth/tokens.py               |  22 ++++
 backend/app/config.py                    |   9 ++
 backend/app/main.py                      |   7 ++
 backend/requirements.txt                 |   2 +
 backend/tests/test_audit_failfast.py     |  20 +++-
 backend/tests/test_auth_hibp.py          |  94 ++++++++++++++++
 backend/tests/test_auth_mfa.py           |  72 ++++++++++++
 backend/tests/test_auth_mfa_endpoints.py | 134 ++++++++++++++++++++++
 backend/tests/test_auth_mfa_flow.py      | 184 +++++++++++++++++++++++++++++++
 docs/COMPAS_Control_Desarrollo.xlsx      | Bin 19257 -> 19372 bytes
 docs/RUNBOOK-INFRA.md                    |   8 ++
 render.yaml                              |   4 +
 19 files changed, 1019 insertions(+), 16 deletions(-)
```

## 5. Código nuevo: app/auth/mfa.py

```python
# backend/app/auth/mfa.py
"""Núcleo criptográfico de MFA (Spec §8.1 / DoD #11).

- **TOTP** (pyotp): secreto base32, URI otpauth para QR, verificación con ventana
  ±1 paso (tolerancia de reloj).
- **Cifrado del secreto en reposo** (Fernet/AES): el `mfa_secret` NUNCA se guarda en
  claro; se descifra solo para verificar. Clave desde `settings.mfa_enc_key`.
- **Códigos de respaldo**: hasheados con bcrypt (como las contraseñas) y de UN SOLO
  USO (consumirlos los elimina de la lista).

Funciones puras: la clave se pasa explícita (como `tokens` con el JWT secret), sin
estado global → fácil de testear y sin acoplar a Settings.
"""

import secrets

import pyotp
from cryptography.fernet import Fernet

from app.auth import passwords

_ISSUER = "COMPAS RODDOS"
_BACKUP_BYTES = 4  # 8 hex chars por código


# ── TOTP ────────────────────────────────────────────────────────────────
def new_totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(secret: str, email: str) -> str:
    """URI otpauth:// para el QR de enrolamiento (Google/Microsoft Authenticator)."""
    return pyotp.totp.TOTP(secret).provisioning_uri(name=email, issuer_name=_ISSUER)


def verify_totp(secret: str, code: str, *, valid_window: int = 1) -> bool:
    """valid_window=1 tolera ±1 paso (30s) de desfase de reloj."""
    if not code or not code.strip().isdigit():
        return False
    return pyotp.TOTP(secret).verify(code.strip(), valid_window=valid_window)


# ── Cifrado del secreto en reposo ────────────────────────────────────────
def encrypt_secret(secret: str, key: str) -> str:
    return Fernet(key).encrypt(secret.encode()).decode()


def decrypt_secret(token: str, key: str) -> str:
    """Lanza cryptography.fernet.InvalidToken si la clave no corresponde."""
    return Fernet(key).decrypt(token.encode()).decode()


# ── Códigos de respaldo (bcrypt, un solo uso) ────────────────────────────
def generate_backup_codes(n: int) -> tuple[list[str], list[str]]:
    """Devuelve (claros, hasheados). Los claros se muestran UNA vez al usuario; solo
    los hasheados se persisten."""
    plain = [secrets.token_hex(_BACKUP_BYTES) for _ in range(n)]
    hashed = [passwords.hash_password(c) for c in plain]
    return plain, hashed


def consume_backup_code(code: str, hashed: list[str]) -> tuple[bool, list[str]]:
    """Si `code` coincide con alguno de los hashes, devuelve (True, lista SIN ese hash);
    si no, (False, lista intacta). El consumo garantiza el uso único."""
    for i, h in enumerate(hashed):
        if passwords.verify_password(code, h):
            return True, hashed[:i] + hashed[i + 1 :]
    return False, hashed

```

## 6. Diffs de archivos modificados

### diff `backend/app/auth/tokens.py`

```diff
diff --git a/backend/app/auth/tokens.py b/backend/app/auth/tokens.py
index 791e9d3..4cd5fa0 100644
--- a/backend/app/auth/tokens.py
+++ b/backend/app/auth/tokens.py
@@ -17,6 +17,7 @@ ALGO = "HS256"
 LEEWAY = 30
 ACCESS_TTL = timedelta(minutes=15)
 REFRESH_TTL = timedelta(days=30)
+CHALLENGE_TTL = timedelta(minutes=5)  # ventana para completar el 2º paso (MFA)
 
 
 class TokenError(Exception):
@@ -34,6 +35,7 @@ def create_access_token(
     tv: int,
     jti: str | None = None,
     ttl: timedelta = ACCESS_TTL,
+    mfa_at: int | None = None,
 ) -> str:
     now = now_utc()
     claims = {
@@ -44,6 +46,26 @@ def create_access_token(
         "iat": now,
         "exp": now + ttl,
     }
+    if mfa_at is not None:
+        # Epoch UTC del último factor MFA superado → base del step-up (ventana).
+        claims["mfa_at"] = mfa_at
+    return jwt.encode(claims, secret, algorithm=ALGO)
+
+
+def create_challenge_token(
+    secret: str, *, sub: str, tv: int, ttl: timedelta = CHALLENGE_TTL
+) -> str:
+    """Token efímero del 1er paso del login cuando el usuario tiene MFA: NO da acceso;
+    solo autoriza a canjear un código en /auth/mfa/verify."""
+    now = now_utc()
+    claims = {
+        "sub": sub,
+        "tv": tv,
+        "type": "mfa_challenge",
+        "jti": _new_jti(),
+        "iat": now,
+        "exp": now + ttl,
+    }
     return jwt.encode(claims, secret, algorithm=ALGO)
 
 

```

### diff `backend/app/auth/models.py`

```diff
diff --git a/backend/app/auth/models.py b/backend/app/auth/models.py
index 870c25e..a940321 100644
--- a/backend/app/auth/models.py
+++ b/backend/app/auth/models.py
@@ -45,6 +45,10 @@ class User(BaseModel):
     activo: bool = True
     failed_attempts: int = 0
     locked_until: datetime | None = None
+    # ── MFA (Spec §8.1 / DoD #11) ──
+    mfa_habilitado: bool = False
+    mfa_secret: str | None = None  # CIFRADO en reposo (Fernet); nunca en claro
+    mfa_backup_codes: list[str] = Field(default_factory=list)  # hashes bcrypt, un uso
     created_at: datetime = Field(default_factory=now_utc)
     updated_at: datetime = Field(default_factory=now_utc)
 

```

### diff `backend/app/auth/repository.py`

```diff
diff --git a/backend/app/auth/repository.py b/backend/app/auth/repository.py
index ce0975d..eee56f7 100644
--- a/backend/app/auth/repository.py
+++ b/backend/app/auth/repository.py
@@ -114,6 +114,48 @@ async def reset_failed_login(user_id: str) -> None:
     )
 
 
+# ── MFA ────────────────────────────────────────────────────────────────
+async def _set_user(user_id: str, campos: dict) -> None:
+    from bson import ObjectId
+
+    campos["updated_at"] = now_utc()
+    await _col(USERS_COLLECTION).update_one(
+        {"_id": ObjectId(user_id)}, {"$set": campos}
+    )
+
+
+async def set_mfa_secret(user_id: str, enc_secret: str) -> None:
+    """Enrolamiento (setup): guarda el secreto CIFRADO; mfa_habilitado sigue False
+    hasta que /activate confirme un código válido."""
+    await _set_user(user_id, {"mfa_secret": enc_secret, "mfa_habilitado": False})
+
+
+async def enable_mfa(user_id: str, hashed_backup_codes: list[str]) -> None:
+    """Activación: habilita MFA y fija los códigos de respaldo (hashes)."""
+    await _set_user(
+        user_id,
+        {"mfa_habilitado": True, "mfa_backup_codes": hashed_backup_codes},
+    )
+
+
+async def replace_backup_codes(user_id: str, hashed_backup_codes: list[str]) -> None:
+    await _set_user(user_id, {"mfa_backup_codes": hashed_backup_codes})
+
+
+async def clear_mfa(user_id: str, new_token_version: int) -> None:
+    """Reset de MFA: borra secreto y códigos, deshabilita y BUMP token_version
+    (revoca todas las sesiones activas — el access viejo deja de validar)."""
+    await _set_user(
+        user_id,
+        {
+            "mfa_secret": None,
+            "mfa_habilitado": False,
+            "mfa_backup_codes": [],
+            "token_version": new_token_version,
+        },
+    )
+
+
 # ── Refresh sessions ───────────────────────────────────────────────────
 async def create_refresh_session(session: RefreshSession) -> None:
     await _col(REFRESH_SESSIONS_COLLECTION).insert_one(
@@ -182,3 +224,29 @@ async def reset_ip_attempts(ip: str) -> None:
     """Libera el cupo de la IP tras un login exitoso (Kimi H1): así una ráfaga
     legítima desde una NAT de oficina no se auto-bloquea con 429."""
     await _col(LOGIN_THROTTLE_COLLECTION).delete_one({"_id": f"ip:{ip}"})
+
+
+async def _bump_throttle(key: str, window_min: int) -> int:
+    doc = await _col(LOGIN_THROTTLE_COLLECTION).find_one_and_update(
+        {"_id": key},
+        {
+            "$inc": {"count": 1},
+            "$setOnInsert": {"expires_at": now_utc() + timedelta(minutes=window_min)},
+        },
+        upsert=True,
+        return_document=True,
+    )
+    return doc.get("count", 1) if doc else 1
+
+
+async def register_mfa_attempt(user_id: str, ip: str, *, window_min: int) -> int:
+    """Throttle de /auth/mfa/verify por CUENTA e IP (6 dígitos = fuerza bruta viable).
+    Devuelve el mayor de los dos contadores. Mismo TTL que el rate limit de login."""
+    a = await _bump_throttle(f"mfa:acct:{user_id}", window_min)
+    b = await _bump_throttle(f"mfa:ip:{ip}", window_min)
+    return max(a, b)
+
+
+async def reset_mfa_attempts(user_id: str, ip: str) -> None:
+    await _col(LOGIN_THROTTLE_COLLECTION).delete_one({"_id": f"mfa:acct:{user_id}"})
+    await _col(LOGIN_THROTTLE_COLLECTION).delete_one({"_id": f"mfa:ip:{ip}"})

```

### diff `backend/app/auth/service.py`

```diff
diff --git a/backend/app/auth/service.py b/backend/app/auth/service.py
index ecd5a72..7452fcd 100644
--- a/backend/app/auth/service.py
+++ b/backend/app/auth/service.py
@@ -14,7 +14,7 @@ from uuid import uuid4
 
 from app.audit.events import AuditEvento
 from app.audit.service import emit_audit
-from app.auth import passwords, repository, tokens
+from app.auth import mfa, passwords, repository, tokens
 from app.auth.models import RefreshSession, User
 from app.config import Settings
 from app.core.time import now_utc
@@ -40,6 +40,14 @@ class TokenPair:
     refresh_expires_at: datetime
 
 
+@dataclass
+class MfaChallenge:
+    """1er paso del login para usuarios con MFA: no da acceso; se canjea en
+    /auth/mfa/verify con un código TOTP o de respaldo."""
+
+    challenge_token: str
+
+
 async def _safe_emit(evento: AuditEvento, **kw) -> None:
     try:
         await emit_audit(evento, **kw)
@@ -55,7 +63,12 @@ async def _safe_emit(evento: AuditEvento, **kw) -> None:
 
 
 def _issue_pair(
-    settings: Settings, user: User, family_id: str, family_created_at: datetime
+    settings: Settings,
+    user: User,
+    family_id: str,
+    family_created_at: datetime,
+    *,
+    mfa_at: int | None = None,
 ) -> tuple[TokenPair, RefreshSession]:
     secret = settings.jwt_secret
     access = tokens.create_access_token(
@@ -63,6 +76,7 @@ def _issue_pair(
         sub=user.id,
         tv=user.token_version,
         ttl=timedelta(minutes=settings.access_ttl_min),
+        mfa_at=mfa_at,
     )
     jti = uuid4().hex
     refresh = tokens.create_refresh_token(
@@ -85,7 +99,9 @@ def _issue_pair(
     return TokenPair(access, refresh, expires_at), session
 
 
-async def login(settings: Settings, *, email: str, password: str, ip: str) -> TokenPair:
+async def login(
+    settings: Settings, *, email: str, password: str, ip: str
+) -> TokenPair | MfaChallenge:
     if not settings.jwt_secret:
         raise AuthError("servicio de auth no configurado", status=500)
 
@@ -146,9 +162,19 @@ async def login(settings: Settings, *, email: str, password: str, ip: str) -> To
         )
         raise AuthError(_INVALID)
 
-    # Éxito.
+    # Contraseña correcta (1er factor).
     await repository.reset_failed_login(user.id)
     await repository.reset_ip_attempts(ip)  # H1: liberar el cupo IP en éxito
+
+    # 2º factor: si el usuario tiene MFA, NO emitimos login ni creamos sesión aún;
+    # devolvemos un challenge que se canjea en /auth/mfa/verify.
+    if user.mfa_habilitado:
+        return MfaChallenge(
+            tokens.create_challenge_token(
+                settings.jwt_secret, sub=user.id, tv=user.token_version
+            )
+        )
+
     family_id = uuid4().hex
     pair, session = _issue_pair(settings, user, family_id, now_utc())
     await repository.create_refresh_session(session)
@@ -246,8 +272,123 @@ async def logout(
             pass
 
 
-async def authenticate(settings: Settings, *, access_token: str) -> User:
-    """Valida el access por request: firma, tipo, denylist, activo y token_version."""
+# ── MFA: verificación (2º paso), enrolamiento y reset ───────────────────
+async def mfa_verify(
+    settings: Settings, *, challenge_token: str, code: str, ip: str
+) -> TokenPair:
+    """2º paso del login: canjea el challenge + un código TOTP (o de respaldo) por el
+    par de tokens, con claim `mfa_at`. Throttle por cuenta+IP (fuerza bruta de 6
+    dígitos)."""
+    if not settings.jwt_secret or not settings.mfa_enc_key:
+        raise AuthError("servicio de auth no configurado", status=500)
+    try:
+        claims = tokens.decode_token(
+            settings.jwt_secret, challenge_token, expected_type="mfa_challenge"
+        )
+    except tokens.TokenError as e:
+        raise AuthError(_INVALID) from e
+    sub, tv = claims["sub"], claims["tv"]
+
+    count = await repository.register_mfa_attempt(
+        sub, ip, window_min=settings.mfa_verify_window_min
+    )
+    if count > settings.mfa_verify_max:
+        raise AuthError("Demasiados intentos. Intente más tarde.", status=429)
+
+    user = await repository.get_user_by_id(sub)
+    if (
+        user is None
+        or not user.activo
+        or user.token_version != tv
+        or not user.mfa_habilitado
+        or not user.mfa_secret
+    ):
+        raise AuthError(_INVALID)
+
+    try:
+        secret_plano = mfa.decrypt_secret(user.mfa_secret, settings.mfa_enc_key)
+    except Exception as e:  # noqa: BLE001 — clave de cifrado mala = error de config
+        logger.error("no se pudo descifrar mfa_secret", exc_info=True)
+        raise AuthError("servicio de auth no configurado", status=500) from e
+
+    ok = mfa.verify_totp(secret_plano, code)
+    if not ok:
+        consumido, restantes = mfa.consume_backup_code(code, user.mfa_backup_codes)
+        if consumido:
+            ok = True
+            await repository.replace_backup_codes(user.id, restantes)
+
+    if not ok:
+        await _safe_emit(
+            AuditEvento.user_login_fallido,
+            entidad="user",
+            entidad_id=user.id,
+            metadata={"ip": ip, "factor": "mfa"},
+        )
+        raise AuthError(_INVALID)
+
+    # Éxito del 2º factor.
+    await repository.reset_mfa_attempts(sub, ip)
+    now = now_utc()
+    family_id = uuid4().hex
+    pair, session = _issue_pair(
+        settings, user, family_id, now, mfa_at=int(now.timestamp())
+    )
+    await repository.create_refresh_session(session)
+    await _safe_emit(
+        AuditEvento.user_login,
+        entidad="user",
+        entidad_id=user.id,
+        actor_id=user.id,
+        metadata={"ip": ip, "mfa": True},
+    )
+    return pair
+
+
+async def mfa_setup(settings: Settings, *, user: User, password: str) -> dict:
+    """Enrolamiento: re-verifica la contraseña (paso protegido), genera el secreto,
+    lo guarda CIFRADO (mfa_habilitado sigue False) y devuelve el secreto + URI para el
+    QR UNA sola vez. No se activa hasta /mfa/activate con un código válido."""
+    if not settings.mfa_enc_key:
+        raise AuthError("MFA no configurado", status=500)
+    if not passwords.verify_password(password, user.password_hash):
+        raise AuthError(_INVALID)
+    secret = mfa.new_totp_secret()
+    await repository.set_mfa_secret(
+        user.id, mfa.encrypt_secret(secret, settings.mfa_enc_key)
+    )
+    return {"secret": secret, "otpauth_uri": mfa.totp_uri(secret, user.email)}
+
+
+async def mfa_activate(settings: Settings, *, user: User, code: str) -> list[str]:
+    """Confirma el enrolamiento con un código TOTP válido → habilita MFA y devuelve
+    los códigos de respaldo (en claro, UNA vez)."""
+    if not settings.mfa_enc_key:
+        raise AuthError("MFA no configurado", status=500)
+    if not user.mfa_secret:
+        raise AuthError("Primero /auth/mfa/setup.", status=400)
+    secret = mfa.decrypt_secret(user.mfa_secret, settings.mfa_enc_key)
+    if not mfa.verify_totp(secret, code):
+        raise AuthError("Código inválido.", status=400)
+    plain, hashed = mfa.generate_backup_codes(settings.mfa_backup_codes)
+    await repository.enable_mfa(user.id, hashed)
+    return plain
+
+
+async def mfa_reset(settings: Settings, *, user_id: str) -> None:
+    """Reset de MFA (self con step-up, o Admin sobre otro): borra secreto/códigos y
+    hace BUMP de token_version → revoca todas las sesiones."""
+    user = await repository.get_user_by_id(user_id)
+    if user is None:
+        raise AuthError("Usuario no encontrado.", status=404)
+    await repository.clear_mfa(user_id, user.token_version + 1)
+
+
+async def authenticate_with_claims(
+    settings: Settings, *, access_token: str
+) -> tuple[User, dict]:
+    """Valida el access por request: firma, tipo, denylist, activo y token_version.
+    Devuelve también los claims (para el step-up, que lee `mfa_at`)."""
     try:
         claims = tokens.decode_token(
             settings.jwt_secret, access_token, expected_type="access"
@@ -259,6 +400,11 @@ async def authenticate(settings: Settings, *, access_token: str) -> User:
     user = await repository.get_user_by_id(claims["sub"])
     if user is None or not user.activo or user.token_version != claims["tv"]:
         raise AuthError("Sesión revocada.")
+    return user, claims
+
+
+async def authenticate(settings: Settings, *, access_token: str) -> User:
+    user, _ = await authenticate_with_claims(settings, access_token=access_token)
     return user
 
 

```

### diff `backend/app/auth/deps.py`

```diff
diff --git a/backend/app/auth/deps.py b/backend/app/auth/deps.py
index e24ca4e..e0248fe 100644
--- a/backend/app/auth/deps.py
+++ b/backend/app/auth/deps.py
@@ -13,24 +13,52 @@ from app.auth.models import User
 from app.auth.permissions import has_permission
 from app.auth.roles import Role
 from app.config import Settings, get_settings
+from app.core.time import now_utc
 
 
 def _settings() -> Settings:
     return get_settings()
 
 
-async def get_current_user(
-    request: Request, settings: Settings = Depends(_settings)
-) -> User:
+def _bearer(request: Request) -> str:
     auth = request.headers.get("authorization", "")
     if not auth.startswith("Bearer "):
         raise HTTPException(401, "No autenticado.")
+    return auth[7:]
+
+
+async def get_current_user(
+    request: Request, settings: Settings = Depends(_settings)
+) -> User:
     try:
-        return await service.authenticate(settings, access_token=auth[7:])
+        return await service.authenticate(settings, access_token=_bearer(request))
     except service.AuthError as e:
         raise HTTPException(e.status, e.detail) from e
 
 
+def require_step_up() -> Callable[..., Awaitable[User]]:
+    """Exige MFA RECIENTE (claim `mfa_at` dentro de la ventana) — para acciones
+    sensibles: ciclo:reabrir, ciclo:config, editar saldo inicial (Spec §2.4). No basta
+    estar autenticado: hay que haber pasado el 2º factor hace poco."""
+
+    async def dep(
+        request: Request, settings: Settings = Depends(_settings)
+    ) -> User:
+        try:
+            user, claims = await service.authenticate_with_claims(
+                settings, access_token=_bearer(request)
+            )
+        except service.AuthError as e:
+            raise HTTPException(e.status, e.detail) from e
+        mfa_at = claims.get("mfa_at")
+        ventana = settings.mfa_stepup_window_min * 60
+        if mfa_at is None or (now_utc().timestamp() - mfa_at) > ventana:
+            raise HTTPException(403, "Step-up MFA requerido.")
+        return user
+
+    return dep
+
+
 def require_permission(capacidad: str) -> Callable[..., Awaitable[User]]:
     """Dependencia RBAC para endpoints de NEGOCIO (fuente: config §4.1/§2.4)."""
 

```

### diff `backend/app/auth/router.py`

```diff
diff --git a/backend/app/auth/router.py b/backend/app/auth/router.py
index 0e9cd53..cbfc7cb 100644
--- a/backend/app/auth/router.py
+++ b/backend/app/auth/router.py
@@ -8,7 +8,7 @@ from fastapi import APIRouter, Depends, HTTPException, Request, Response
 from pydantic import BaseModel, ConfigDict
 
 from app.auth import service
-from app.auth.deps import get_current_user
+from app.auth.deps import get_current_user, require_step_up
 from app.auth.models import User
 from app.auth.permissions import capabilities_for
 from app.config import Settings, get_settings
@@ -25,6 +25,22 @@ class LoginBody(BaseModel):
     password: str
 
 
+class MfaSetupBody(BaseModel):
+    model_config = ConfigDict(strict=True, extra="forbid")
+    password: str  # re-autenticación para proteger el enrolamiento
+
+
+class MfaActivateBody(BaseModel):
+    model_config = ConfigDict(strict=True, extra="forbid")
+    code: str
+
+
+class MfaVerifyBody(BaseModel):
+    model_config = ConfigDict(strict=True, extra="forbid")
+    mfa_token: str
+    code: str
+
+
 def _settings() -> Settings:
     return get_settings()
 
@@ -76,15 +92,81 @@ async def login(
 ):
     ip = client_ip(request)
     try:
-        pair = await service.login(
+        result = await service.login(
             settings, email=body.email, password=body.password, ip=ip
         )
     except service.AuthError as e:
         raise HTTPException(e.status, e.detail) from e
+    # Usuario con MFA: 1er paso OK → challenge (sin cookie ni access).
+    if isinstance(result, service.MfaChallenge):
+        return {"mfa_required": True, "mfa_token": result.challenge_token}
+    _set_refresh_cookie(response, settings, result.refresh_token)
+    return {"access_token": result.access_token, "token_type": "bearer"}
+
+
+@router.post("/mfa/verify")
+async def mfa_verify(
+    body: MfaVerifyBody,
+    request: Request,
+    response: Response,
+    settings: Settings = Depends(_settings),
+    _: None = Depends(verify_origin),
+):
+    """2º paso del login: canjea challenge + código (TOTP o respaldo) por los tokens."""
+    ip = client_ip(request)
+    try:
+        pair = await service.mfa_verify(
+            settings, challenge_token=body.mfa_token, code=body.code, ip=ip
+        )
+    except service.AuthError as e:
+        raise HTTPException(e.status, e.detail) from e
     _set_refresh_cookie(response, settings, pair.refresh_token)
     return {"access_token": pair.access_token, "token_type": "bearer"}
 
 
+@router.post("/mfa/setup")
+async def mfa_setup(
+    body: MfaSetupBody,
+    settings: Settings = Depends(_settings),
+    user: User = Depends(get_current_user),
+    _: None = Depends(verify_origin),
+):
+    """Inicia el enrolamiento: devuelve secreto + URI otpauth (para el QR) UNA vez."""
+    try:
+        return await service.mfa_setup(settings, user=user, password=body.password)
+    except service.AuthError as e:
+        raise HTTPException(e.status, e.detail) from e
+
+
+@router.post("/mfa/activate")
+async def mfa_activate(
+    body: MfaActivateBody,
+    settings: Settings = Depends(_settings),
+    user: User = Depends(get_current_user),
+    _: None = Depends(verify_origin),
+):
+    """Confirma el enrolamiento con un código válido → habilita MFA y entrega los
+    códigos de respaldo (en claro, UNA vez)."""
+    try:
+        codes = await service.mfa_activate(settings, user=user, code=body.code)
+    except service.AuthError as e:
+        raise HTTPException(e.status, e.detail) from e
+    return {"backup_codes": codes}
+
+
+@router.post("/mfa/reset")
+async def mfa_reset(
+    settings: Settings = Depends(_settings),
+    user: User = Depends(require_step_up()),
+    _: None = Depends(verify_origin),
+):
+    """Reset del PROPIO MFA (exige step-up: MFA reciente). Borra secreto/códigos y
+    revoca sesiones (bump token_version). El reset de OTRO usuario lo hará el Admin
+    desde el módulo /users."""
+    await service.mfa_reset(settings, user_id=user.id)
+    return {"status": "ok"}
+
+
 @router.post("/refresh")
 async def refresh(
     request: Request,

```

### diff `backend/app/auth/passwords.py`

```diff
diff --git a/backend/app/auth/passwords.py b/backend/app/auth/passwords.py
index 5b2c283..0ba66de 100644
--- a/backend/app/auth/passwords.py
+++ b/backend/app/auth/passwords.py
@@ -2,12 +2,18 @@
 """Hashing bcrypt + política de contraseñas (Spec §1.1 / §8.1).
 
 Costo fijo rounds=12 (no solo longitud). Política de LONGITUD: 12 para admin/directivo,
-10 para el resto. HIBP y expiración quedan para Sprint 0b (fuera de PR-2)."""
+10 para el resto. HIBP (k-anonymity) añadido en Sprint 0b / PR-2."""
+
+import hashlib
+import logging
+from collections.abc import Awaitable, Callable
 
 import bcrypt
 
 from app.auth.roles import Role
 
+logger = logging.getLogger("compas.auth")
+
 ROUNDS = 12
 _LARGOS = {Role.admin: 12, Role.directivo: 12, Role.financiero: 10, Role.consulta: 10}
 
@@ -30,3 +36,54 @@ def password_meets_policy(password: str, rol: Role) -> bool:
 # Hash dummy para comparar cuando el email no existe → login de tiempo/forma uniforme
 # (anti-enumeración, Kimi M-04). Se computa una vez al importar.
 DUMMY_HASH = hash_password("dummy-password-anti-enumeration-000")
+
+
+# ── HIBP (Have I Been Pwned) — k-anonymity ───────────────────────────────
+_HIBP_RANGE = "https://api.pwnedpasswords.com/range/"
+
+
+async def _default_fetch(prefix: str) -> str:
+    """GET al rango de HIBP. Solo viaja el prefijo de 5 hex del SHA-1 (k-anonymity):
+    ni la contraseña ni el hash completo salen del backend."""
+    import httpx
+
+    async with httpx.AsyncClient(timeout=5.0) as client:
+        r = await client.get(f"{_HIBP_RANGE}{prefix}", headers={"Add-Padding": "true"})
+        r.raise_for_status()
+        return r.text
+
+
+async def password_pwned(
+    password: str, *, fetch: Callable[[str], Awaitable[str]] = _default_fetch
+) -> bool:
+    """True si la contraseña aparece en filtraciones conocidas (HIBP). `fetch` se
+    inyecta en tests. El SHA-1 aquí NO es para almacenar: es el protocolo de HIBP."""
+    digest = hashlib.sha1(password.encode()).hexdigest().upper()  # noqa: S324
+    prefix, suffix = digest[:5], digest[5:]
+    cuerpo = await fetch(prefix)
+    for linea in cuerpo.splitlines():
+        parte = linea.split(":", 1)[0].strip().upper()
+        if parte == suffix:
+            return True
+    return False
+
+
+async def password_acceptable(
+    password: str,
+    rol: Role,
+    *,
+    fetch: Callable[[str], Awaitable[str]] = _default_fetch,
+) -> tuple[bool, str | None]:
+    """Política completa (§8.1): longitud por rol + no estar en HIBP. Punto de
+    integración para el alta/cambio de contraseña (módulo /users, futuro).
+
+    HIBP es advisory: si la API no responde, NO bloqueamos el cambio (fail-open con
+    log) — no dejamos al usuario sin poder operar por una caída de un tercero."""
+    if not password_meets_policy(password, rol):
+        return False, "La contraseña no cumple la longitud mínima."
+    try:
+        if await password_pwned(password, fetch=fetch):
+            return False, "Contraseña presente en filtraciones conocidas (HIBP)."
+    except Exception:  # noqa: BLE001 — HIBP caído no debe bloquear (advisory)
+        logger.warning("HIBP no disponible; se omite la verificación.", exc_info=True)
+    return True, None

```

### diff `backend/app/main.py`

```diff
diff --git a/backend/app/main.py b/backend/app/main.py
index 553043a..b2b6775 100644
--- a/backend/app/main.py
+++ b/backend/app/main.py
@@ -97,6 +97,13 @@ async def lifespan(app: FastAPI):
             "JWT_SECRET requerido y >= 32 bytes fuera de dev (Spec §8.1)."
         )
 
+    # MFA_ENC_KEY: sin ella el mfa_secret no se puede descifrar → MFA inservible.
+    # Fail-fast fuera de dev (mismo principio que JWT/audit).
+    if settings.app_env != "development" and not settings.mfa_enc_key:
+        raise RuntimeError(
+            "MFA_ENC_KEY requerida fuera de dev: cifra el secreto TOTP (DoD #11)."
+        )
+
     _init_sentry(
         settings
     )  # H3: observabilidad de errores (incl. fallos del canal audit)

```

### diff `backend/app/config.py`

```diff
diff --git a/backend/app/config.py b/backend/app/config.py
index 7a8b041..eb56b59 100644
--- a/backend/app/config.py
+++ b/backend/app/config.py
@@ -51,6 +51,15 @@ class Settings(BaseSettings):
     cookie_secure: bool = True  # false solo para pruebas locales sin TLS
     frontend_origin: str = "https://compas.roddos.com"  # CORS + verificación de Origin
 
+    # ── MFA (Spec §8.1 / DoD #11) ──────────────────────────────────────
+    mfa_stepup_window_min: int = 5  # "MFA reciente" para step-up (claim mfa_at)
+    mfa_backup_codes: int = 10  # códigos de respaldo de un solo uso
+    mfa_verify_max: int = 5  # backoff en /auth/mfa/verify (6 dígitos = fuerza bruta)
+    mfa_verify_window_min: int = 15
+    # Clave de cifrado del mfa_secret en reposo (Fernet, urlsafe-b64 de 32 bytes).
+    # Fail-fast fuera de dev (como JWT_SECRET): sin ella el TOTP no se puede descifrar.
+    mfa_enc_key: str | None = None
+
     # ── Secretos (opcionales en dev/skeleton; obligatorios en prod) ────
     jwt_secret: str | None = None
     sentry_dsn: str | None = None

```

### diff `render.yaml`

```diff
diff --git a/render.yaml b/render.yaml
index 05789c8..b4a5bb7 100644
--- a/render.yaml
+++ b/render.yaml
@@ -30,6 +30,8 @@ services:
         sync: false             # secreto — se carga a mano (RUNBOOK §8)
       - key: JWT_SECRET
         sync: false
+      - key: MFA_ENC_KEY        # Fernet urlsafe-b64 32B — cifra el secreto TOTP (DoD #11)
+        sync: false
       - key: SENTRY_DSN
         sync: false
       - key: AWS_ACCESS_KEY_ID
@@ -95,6 +97,8 @@ services:
         sync: false
       - key: JWT_SECRET
         sync: false
+      - key: MFA_ENC_KEY
+        sync: false
 
 # Nota: el frontend (proyecto 'compas') vive en Vercel, no en este blueprint.
 # Nota: no hay Render Cron Jobs — toda la programación vive en APScheduler dentro de compas-jobs

```

## 7. Tests nuevos (código)

### `backend/tests/test_auth_mfa.py`

```python
# backend/tests/test_auth_mfa.py
"""Núcleo criptográfico de MFA (Spec §8.1 / DoD #11): TOTP, cifrado del secreto en
reposo y códigos de respaldo de un solo uso. Todo puro (sin Mongo)."""

import pyotp
import pytest
from app.auth import mfa
from cryptography.fernet import Fernet


# ── TOTP ────────────────────────────────────────────────────────────────
def test_totp_secret_y_verify_ok():
    secret = mfa.new_totp_secret()
    code = pyotp.TOTP(secret).now()
    assert mfa.verify_totp(secret, code) is True


def test_totp_verify_rechaza_codigo_malo():
    secret = mfa.new_totp_secret()
    assert mfa.verify_totp(secret, "000000") is False
    assert mfa.verify_totp(secret, "abc") is False
    assert mfa.verify_totp(secret, "") is False


def test_totp_uri_para_qr():
    secret = mfa.new_totp_secret()
    uri = mfa.totp_uri(secret, "andres@roddos.com")
    assert uri.startswith("otpauth://totp/")
    assert "roddos.com" in uri  # el email va URL-encoded (@ → %40)
    assert secret in uri
    assert "RODDOS" in uri


# ── Cifrado del secreto en reposo (Fernet) ───────────────────────────────
def test_cifrado_round_trip():
    key = Fernet.generate_key().decode()
    secret = mfa.new_totp_secret()
    enc = mfa.encrypt_secret(secret, key)
    assert enc != secret  # no queda en claro
    assert mfa.decrypt_secret(enc, key) == secret


def test_descifrar_con_clave_distinta_falla():
    k1 = Fernet.generate_key().decode()
    k2 = Fernet.generate_key().decode()
    enc = mfa.encrypt_secret(mfa.new_totp_secret(), k1)
    with pytest.raises(Exception):  # noqa: B017 — InvalidToken de cryptography
        mfa.decrypt_secret(enc, k2)


# ── Códigos de respaldo (bcrypt, un solo uso) ────────────────────────────
def test_backup_genera_n_codigos():
    plain, hashed = mfa.generate_backup_codes(10)
    assert len(plain) == 10 and len(hashed) == 10
    assert len(set(plain)) == 10  # distintos
    # hasheados (bcrypt), no en claro
    assert all(not h.startswith(p) for p, h in zip(plain, hashed, strict=True))


def test_backup_consume_ok_y_un_solo_uso():
    plain, hashed = mfa.generate_backup_codes(3)
    ok, restantes = mfa.consume_backup_code(plain[0], hashed)
    assert ok is True and len(restantes) == 2
    # el mismo código ya no sirve contra los restantes
    ok2, _ = mfa.consume_backup_code(plain[0], restantes)
    assert ok2 is False


def test_backup_consume_codigo_desconocido():
    plain, hashed = mfa.generate_backup_codes(3)
    ok, restantes = mfa.consume_backup_code("no-existe", hashed)
    assert ok is False and len(restantes) == 3

```

### `backend/tests/test_auth_hibp.py`

```python
# backend/tests/test_auth_hibp.py
"""HIBP k-anonymity (Spec §8.1): nunca se envía la contraseña ni su hash completo,
solo el prefijo de 5 hex del SHA-1; el sufijo se compara localmente."""

import hashlib

from app.auth import passwords
from app.auth.roles import Role


def _sha1_upper(s: str) -> str:
    return hashlib.sha1(s.encode()).hexdigest().upper()  # noqa: S324 — HIBP usa SHA-1


async def test_pwned_true_cuando_el_sufijo_aparece():
    pwd = "password"
    h = _sha1_upper(pwd)
    prefix, suffix = h[:5], h[5:]

    async def fetch(p):
        assert p == prefix  # k-anonymity: solo el prefijo sale
        return f"{suffix}:99999\nAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA:1"

    assert await passwords.password_pwned(pwd, fetch=fetch) is True


async def test_pwned_false_cuando_no_aparece():
    async def fetch(_p):
        return "0000000000000000000000000000000000A:5\nBBBB:2"

    assert await passwords.password_pwned("clave-unica-larga-xyz", fetch=fetch) is False


async def test_pwned_solo_envia_prefijo_de_5():
    capturado = {}

    async def fetch(p):
        capturado["p"] = p
        return ""

    await passwords.password_pwned("otra-clave", fetch=fetch)
    assert len(capturado["p"]) == 5
    assert capturado["p"] == capturado["p"].upper()


async def test_pwned_cuenta_prefijada_en_la_linea():
    # Formato real de la API: "SUFIJO:conteo" con conteo > 0.
    pwd = "123456"
    h = _sha1_upper(pwd)

    async def fetch(_p):
        return f"{h[5:]}:24230577"

    assert await passwords.password_pwned(pwd, fetch=fetch) is True


# ── Política completa (longitud + HIBP) ──────────────────────────────────
async def _no_pwned(_p):
    return ""


async def test_politica_rechaza_corta():
    ok, motivo = await passwords.password_acceptable(
        "corta", Role.admin, fetch=_no_pwned
    )
    assert ok is False and "longitud" in motivo.lower()


async def test_politica_rechaza_filtrada():
    pwd = "password1234"  # 12 chars (cumple longitud admin) pero filtrada
    h = _sha1_upper(pwd)

    async def fetch(_p):
        return f"{h[5:]}:5"

    ok, motivo = await passwords.password_acceptable(pwd, Role.admin, fetch=fetch)
    assert ok is False and "HIBP" in motivo


async def test_politica_acepta_larga_y_no_filtrada():
    ok, motivo = await passwords.password_acceptable(
        "clave-unica-larga-2026", Role.admin, fetch=_no_pwned
    )
    assert ok is True and motivo is None


async def test_politica_hibp_caido_no_bloquea():
    async def fetch_falla(_p):
        raise RuntimeError("HIBP caído")

    ok, _ = await passwords.password_acceptable(
        "clave-unica-larga-2026", Role.admin, fetch=fetch_falla
    )
    assert ok is True  # fail-open

```

### `backend/tests/test_auth_mfa_flow.py`

```python
# backend/tests/test_auth_mfa_flow.py
"""Flujos MFA (Spec §8.1 / DoD #11) con mongomock: enrolamiento (setup→activate),
login en 2 pasos (challenge → verify), respaldo un-solo-uso, throttle y reset."""

import pyotp
import pytest
import pytest_asyncio
from app.audit.service import configure_audit, reset_audit
from app.auth import passwords, repository, service
from app.auth.models import User
from app.auth.roles import Role
from app.config import Settings
from cryptography.fernet import Fernet
from mongomock_motor import AsyncMongoMockClient

PWD = "clave-larga-1234"
ENC_KEY = Fernet.generate_key().decode()


def _settings(**kw) -> Settings:
    base = dict(
        jwt_secret="x" * 40,
        mfa_enc_key=ENC_KEY,
        cookie_secure=False,
        app_env="development",
        login_ip_max=1000,
    )
    base.update(kw)
    return Settings(**base)


@pytest_asyncio.fixture
async def client():
    c = AsyncMongoMockClient()
    repository.configure_auth(c, "compas_test")
    configure_audit(c, "compas_test")
    await repository.create_user(
        User(
            email="a@roddos.com",
            password_hash=passwords.hash_password(PWD),
            rol=Role.admin,
        )
    )
    yield c
    repository.reset_auth()
    reset_audit()


async def _user():
    return await repository.get_user_by_email("a@roddos.com")


async def _enroll(s) -> str:
    """setup + activate; devuelve el secreto TOTP en claro (para calcular códigos)."""
    info = await service.mfa_setup(s, user=await _user(), password=PWD)
    secret = info["secret"]
    await service.mfa_activate(s, user=await _user(), code=pyotp.TOTP(secret).now())
    return secret


# ── Enrolamiento ─────────────────────────────────────────────────────────
async def test_setup_exige_password(client):
    s = _settings()
    with pytest.raises(service.AuthError):
        await service.mfa_setup(s, user=await _user(), password="mala")


async def test_setup_guarda_secreto_cifrado_sin_habilitar(client):
    s = _settings()
    info = await service.mfa_setup(s, user=await _user(), password=PWD)
    assert info["secret"] and info["otpauth_uri"].startswith("otpauth://")
    u = await _user()
    assert u.mfa_secret is not None and u.mfa_secret != info["secret"]  # cifrado
    assert u.mfa_habilitado is False  # aún no activado


async def test_activate_habilita_y_da_respaldos(client):
    s = _settings()
    info = await service.mfa_setup(s, user=await _user(), password=PWD)
    codes = await service.mfa_activate(
        s, user=await _user(), code=pyotp.TOTP(info["secret"]).now()
    )
    assert len(codes) == s.mfa_backup_codes
    assert (await _user()).mfa_habilitado is True


async def test_activate_codigo_malo_no_habilita(client):
    s = _settings()
    await service.mfa_setup(s, user=await _user(), password=PWD)
    with pytest.raises(service.AuthError):
        await service.mfa_activate(s, user=await _user(), code="000000")
    assert (await _user()).mfa_habilitado is False


# ── Login en 2 pasos ───────────────────────────────────────────────────────
async def test_login_con_mfa_devuelve_challenge(client):
    s = _settings()
    await _enroll(s)
    res = await service.login(s, email="a@roddos.com", password=PWD, ip="1.1.1.1")
    assert isinstance(res, service.MfaChallenge)
    # No se creó sesión ni se emitió login todavía.
    assert await client["compas_test"]["refresh_sessions"].count_documents({}) == 0


async def test_verify_totp_da_tokens_con_mfa_at(client):
    s = _settings()
    secret = await _enroll(s)
    ch = await service.login(s, email="a@roddos.com", password=PWD, ip="1.1.1.1")
    pair = await service.mfa_verify(
        s,
        challenge_token=ch.challenge_token,
        code=pyotp.TOTP(secret).now(),
        ip="1.1.1.1",
    )
    from app.auth import tokens

    claims = tokens.decode_token(
        s.jwt_secret, pair.access_token, expected_type="access"
    )
    assert "mfa_at" in claims
    log = await client["compas_test"]["audit_log"].find_one({"evento": "user.login"})
    assert log is not None


async def test_verify_codigo_malo_falla(client):
    s = _settings()
    await _enroll(s)
    ch = await service.login(s, email="a@roddos.com", password=PWD, ip="1.1.1.1")
    with pytest.raises(service.AuthError) as ei:
        await service.mfa_verify(
            s, challenge_token=ch.challenge_token, code="000000", ip="1.1.1.1"
        )
    assert ei.value.detail == service._INVALID


# ── Códigos de respaldo (un solo uso) ────────────────────────────────────
async def test_backup_code_un_solo_uso(client):
    s = _settings()
    info = await service.mfa_setup(s, user=await _user(), password=PWD)
    codes = await service.mfa_activate(
        s, user=await _user(), code=pyotp.TOTP(info["secret"]).now()
    )
    ch = await service.login(s, email="a@roddos.com", password=PWD, ip="1.1.1.1")
    pair = await service.mfa_verify(
        s, challenge_token=ch.challenge_token, code=codes[0], ip="1.1.1.1"
    )
    assert pair.access_token
    # El mismo código de respaldo ya no sirve.
    ch2 = await service.login(s, email="a@roddos.com", password=PWD, ip="1.1.1.1")
    with pytest.raises(service.AuthError):
        await service.mfa_verify(
            s, challenge_token=ch2.challenge_token, code=codes[0], ip="1.1.1.1"
        )


# ── Throttle ──────────────────────────────────────────────────────────────
async def test_verify_throttle_429(client):
    s = _settings(mfa_verify_max=3)
    await _enroll(s)
    ch = await service.login(s, email="a@roddos.com", password=PWD, ip="9.9.9.9")
    for _ in range(3):
        with pytest.raises(service.AuthError) as ei:
            await service.mfa_verify(
                s, challenge_token=ch.challenge_token, code="000000", ip="9.9.9.9"
            )
        assert ei.value.status == 401
    # El 4º supera el máximo → 429.
    with pytest.raises(service.AuthError) as ei:
        await service.mfa_verify(
            s, challenge_token=ch.challenge_token, code="000000", ip="9.9.9.9"
        )
    assert ei.value.status == 429


# ── Reset ─────────────────────────────────────────────────────────────────
async def test_reset_deshabilita_y_bump_token_version(client):
    s = _settings()
    await _enroll(s)
    antes = await _user()
    await service.mfa_reset(s, user_id=antes.id)
    despues = await _user()
    assert despues.mfa_habilitado is False
    assert despues.mfa_secret is None
    assert despues.token_version == antes.token_version + 1

```

### `backend/tests/test_auth_mfa_endpoints.py`

```python
# backend/tests/test_auth_mfa_endpoints.py
"""Endpoints MFA /api/v1/auth/mfa/* (PR-2): enrolamiento, login 2 pasos, step-up."""

import httpx
import pyotp
import pytest_asyncio
from app.audit.service import configure_audit, reset_audit
from app.auth import passwords, repository
from app.auth.models import User
from app.auth.roles import Role
from app.config import get_settings
from app.main import create_app
from cryptography.fernet import Fernet
from mongomock_motor import AsyncMongoMockClient

PWD = "clave-larga-1234"


@pytest_asyncio.fixture
async def api(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    monkeypatch.setenv("MFA_ENC_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("COOKIE_SECURE", "False")
    monkeypatch.delenv("RUN_SCHEDULER", raising=False)
    get_settings.cache_clear()

    app = create_app()
    c = AsyncMongoMockClient()
    repository.configure_auth(c, "compas_test")
    configure_audit(c, "compas_test")
    await repository.create_user(
        User(
            email="a@roddos.com",
            password_hash=passwords.hash_password(PWD),
            rol=Role.admin,
        )
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    repository.reset_auth()
    reset_audit()
    get_settings.cache_clear()


async def _login(api) -> str:
    r = await api.post(
        "/api/v1/auth/login", json={"email": "a@roddos.com", "password": PWD}
    )
    return r.json()["access_token"]


async def test_enrolamiento_y_login_2_pasos(api):
    access = await _login(api)
    h = {"Authorization": f"Bearer {access}"}

    # setup (protegido por contraseña)
    r = await api.post("/api/v1/auth/mfa/setup", json={"password": PWD}, headers=h)
    assert r.status_code == 200
    secret = r.json()["secret"]
    assert r.json()["otpauth_uri"].startswith("otpauth://")

    # activate con TOTP → códigos de respaldo
    r = await api.post(
        "/api/v1/auth/mfa/activate",
        json={"code": pyotp.TOTP(secret).now()},
        headers=h,
    )
    assert r.status_code == 200
    assert len(r.json()["backup_codes"]) == 10

    # ahora el login pide 2º factor
    r = await api.post(
        "/api/v1/auth/login", json={"email": "a@roddos.com", "password": PWD}
    )
    assert r.status_code == 200
    assert r.json()["mfa_required"] is True
    mfa_token = r.json()["mfa_token"]
    assert "access_token" not in r.json()

    # verify → tokens + cookie de refresh
    r = await api.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_token": mfa_token, "code": pyotp.TOTP(secret).now()},
    )
    assert r.status_code == 200
    assert r.json()["access_token"]
    assert "refresh=" in " ".join(r.headers.get_list("set-cookie"))


async def test_setup_password_malo_401(api):
    access = await _login(api)
    r = await api.post(
        "/api/v1/auth/mfa/setup",
        json={"password": "incorrecta"},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 401


async def test_step_up_bloquea_sin_mfa_reciente(api):
    # Un access SIN mfa_at (usuario sin MFA) no puede hacer /mfa/reset.
    access = await _login(api)
    r = await api.post(
        "/api/v1/auth/mfa/reset", headers={"Authorization": f"Bearer {access}"}
    )
    assert r.status_code == 403


async def test_step_up_ok_tras_verify(api):
    # Enrolar, hacer login+verify → el access trae mfa_at reciente → /mfa/reset pasa.
    access = await _login(api)
    h = {"Authorization": f"Bearer {access}"}
    r = await api.post("/api/v1/auth/mfa/setup", json={"password": PWD}, headers=h)
    secret = r.json()["secret"]
    await api.post(
        "/api/v1/auth/mfa/activate",
        json={"code": pyotp.TOTP(secret).now()},
        headers=h,
    )
    r = await api.post(
        "/api/v1/auth/login", json={"email": "a@roddos.com", "password": PWD}
    )
    mfa_token = r.json()["mfa_token"]
    r = await api.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_token": mfa_token, "code": pyotp.TOTP(secret).now()},
    )
    fresh = r.json()["access_token"]
    r = await api.post(
        "/api/v1/auth/mfa/reset", headers={"Authorization": f"Bearer {fresh}"}
    )
    assert r.status_code == 200

```
