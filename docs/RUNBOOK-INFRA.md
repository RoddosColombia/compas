# RUNBOOK-INFRA — COMPAS

**Versión:** 1.0 · 18-jul-2026 · Entregable del Sprint 0 (F-37, STACK v1.1.2 §6)
**Regla:** este runbook debe permitir re-aprovisionar COMPAS desde cero en < 1 día. Toda casilla se marca con fecha e iniciales. Su completitud es evidencia del gate G1.

---

## 0. Nombramientos (Día 0 — ya decididos por el CEO, 18-jul-2026)

| Rol | Persona | Notas |
|---|---|---|
| Superadmin COMPAS | Andrés Sanjuan — andres@roddos.com | Único usuario inicial; MFA TOTP obligatoria antes del go-live |
| Segunda cuenta | Iván Echeverri | Rol a asignar (recomendado: financiero para UAT y segregación) |
| Par revisor / required reviewer de producción | Iván Echeverri | GitHub environment `production` |
| Custodio del break-glass | Andrés Sanjuan | Sobre sellado o gestor; uso dispara alerta; revisión trimestral |
| Acceso a secretos de producción (máx. 2) | Andrés Sanjuan + Iván Echeverri | Inventario en §8 |
| Región primaria cloud | ☐ PENDIENTE — leer de las cuentas SISMO (Render dashboard → región del servicio; Atlas → región del cluster; S3 → región del bucket) y ANOTAR AQUÍ: `________` | La zona horaria de la app es América/Bogotá; la región cloud es la heredada de SISMO |
| Región de réplica (CRR) | ☐ Elegir una segunda región distinta a la primaria: `________` | Para compas/backups/ y compas-archivo |

---

## 1. GitHub (org existente)

- [ ] Repo privado `compas` (monorepo `backend/` + `frontend/`)
- [ ] Branch protection en `main`: PR obligatorio + CI verde + 1 review
- [ ] Tags `v*` protegidos (solo Tech Lead crea)
- [ ] Environments: `staging` (sin reviewer) y `production` (**required reviewer: Iván**)
- [ ] Secrets por environment (ver §8) — nunca secretos org-wide para COMPAS
- [ ] Dependabot activo (pip + npm) · workflow CI con `pip-audit` + `gitleaks` bloqueantes
- [ ] `render.yaml` (blueprint) en la raíz del repo

## 2. MongoDB Atlas (organización existente — Opción A)

- [ ] Database `compas` y `compas_stg` en el cluster M10 existente
- [ ] Usuario `compas_app`: readWrite SOLO sobre `compas` (otro usuario para `compas_stg`)
- [ ] Rol custom `audit_writer`: insert + find sobre `compas.audit_log`, SIN update/remove (verificado por test en CI)
- [ ] Usuario `compas_audit` con SOLO el rol `audit_writer` (2ª cadena `MONGODB_URI_AUDIT` a la MISMA db `compas`; ver §8). El usuario general `compas_app` NO tiene update/remove sobre `audit_log`. Crear con `COMPAS_AUDIT_PWD=… python scripts/create_audit_role.py "<admin_uri>"` (idempotente; el operador necesita `userAdmin` sobre `compas`; contraseña ≥16 chars por env, nunca por argv)
  - **Tier Atlas (Kimi H-01):** `createRole`/`createUser` funcionan en **M10+** (nuestro cluster, Opción A). En **Free/Flex** están bloqueados → crear el rol/usuario por **Atlas UI o Admin API** (los cambios de custom roles tardan ~30 s). El script detecta el rechazo y remite aquí.
- [ ] Atlas Alerts al canal del Tech Lead: CPU > 70% sostenida, conexiones > 60% del límite (disparadores de migración a cluster propio, STACK §7)
- [ ] Anotar región del cluster en §0

## 3. Render (cuenta existente)

- [ ] Servicio web `compas-api` — instancia **Standard (2 GB / 1 vCPU)**, `RUN_SCHEDULER=false`
- [ ] Background worker `compas-jobs` — **Starter, 1 instancia**, `RUN_SCHEDULER=true`
- [ ] Staging `compas-api-stg` — Starter sin sleep
- [ ] **Auto-deploy de producción: DESACTIVADO.** Producción despliega solo por tag `v*` vía GitHub Actions con reviewer
- [ ] Variables de entorno por servicio (ver §8)

## 4. Vercel (cuenta Pro existente)

- [ ] Proyecto `compas` (frontend), previews por PR
- [ ] Auto-deploy de producción desactivado (mismo flujo por tag)

## 5. Cloudflare (zona roddos.com existente)

- [ ] `compas.roddos.com` → Vercel · `api.compas.roddos.com` → Render
- [ ] TLS full-strict · WAF básico · HSTS
- [ ] **Restringir el origen Render a IPs de Cloudflare** (firewall / Authenticated Origin Pulls) para que `CF-Connecting-IP` no sea spoofeable (Kimi L2). El backend corre con `uvicorn --proxy-headers` y lee la IP real de ese header.

## 6. S3 (cuenta AWS existente)

- [ ] IAM user `compas-app`: Get/Put SOLO sobre `arn:...:bucket-sismo/compas/*` (sin Delete)
- [ ] Prefijos `compas/archivos/` (extractos, facturas, evidencias) y `compas/backups/` (dumps nocturnos, retención 90 días) — Block Public Access + SSE
- [ ] **Bucket NUEVO `compas-archivo`** con **Object Lock (compliance)** habilitado EN LA CREACIÓN + lifecycle a Glacier Deep Archive; IAM del job de archivado = único con PutObjectRetention
- [ ] **CRR**: `compas/backups/` y `compas-archivo` → bucket réplica en la 2ª región (el bucket destino TAMBIÉN con Object Lock)

## 7. Observabilidad (cuentas existentes)

- [ ] Sentry: proyectos `compas-api` y `compas-web`, `send_default_pii=False` + `before_send` (scrubbing de descripcion/proveedor/acreedor/valor/tokens)
- [ ] Better Stack: source `compas` (logs 30 días) + uptime check de `compas.roddos.com` y `/health`
- [ ] **8 heartbeats** (uno por job): carga-diaria-830, snapshot-caja, recalculo-sugeridos, alertas-iva, reaper-cargas, dump-nocturno, archivado-mensual, verificacion-referencial — ausencia = alerta
- [ ] Canales de alerta con dueño: negocio → canal del Financiero (WhatsApp/email); técnico → Tech Lead

## 8. Secretos (inventario — acceso: Andrés + Iván)

| Secreto | Dónde vive | Rotación |
|---|---|---|
| MONGODB_URI_COMPAS / _STG | Render (api y worker) / Actions | Semestral |
| MONGODB_URI_AUDIT | Render (api y worker) / Actions — usuario `compas_audit` (audit_writer) | Semestral |
| JWT_SECRET (propio, ≠ SISMO) | Render | Semestral; compromiso → rotar + bump global de token_version |
| MFA_ENC_KEY (Fernet urlsafe-b64 32B) | Render (api + api-stg) | Cifra el `mfa_secret` TOTP en reposo (DoD #11). Generar: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. **Rotación = re-enrolar** (los secretos cifrados con la clave vieja dejan de descifrar): coordinar reset de MFA de los usuarios. |
| SENTRY_DSN ×2 | Render / Vercel | — |
| AWS keys IAM `compas-app` | Render | Semestral |
| BETTER_STACK_TOKEN + heartbeat URLs | Render (worker) | — |

Procedimiento de compromiso: rotar el secreto afectado → `token_version` global +1 → verificar sesiones caídas → registrar en audit log.

### Break-glass de MFA (usuario que perdió su segundo factor)
1. El usuario usa un **código de respaldo** en `/auth/mfa/verify` para entrar; luego re-enrola (`/auth/mfa/setup` → `/auth/mfa/activate`).
2. Si también perdió los respaldos → el **Admin** resetea su MFA (borra secreto/códigos y hace bump de `token_version`); el usuario re-enrola en el próximo login. (Endpoint admin sobre otro usuario: módulo `/users`, sprint posterior; hoy el reset self con step-up ya existe, y el Admin puede resetear vía script/DB con `repository.clear_mfa`).
3. Todo reset de MFA revoca las sesiones activas del usuario (bump `token_version`).

> **Gap conocido (pre-existente, no de PR-2):** `MONGODB_URI_AUDIT` está en este inventario pero **falta declararlo en `render.yaml`** (los dos servicios web). Sin él, staging/prod hacen fail-fast al arrancar (Kimi C-01). Provisionar junto con `MFA_ENC_KEY` antes del primer deploy no-dev (tracked en CR-002 / S0B).

## 9. Verificación de cierre del Sprint 0 (evidencias para G1)

- [ ] `render.yaml` aplicado y servicios arriba (`/health` 200 en staging)
- [ ] Deploy a staging por merge a `main` funcionando; deploy a producción BLOQUEADO sin tag+reviewer (probar el bloqueo)
- [ ] Test CI de inmutabilidad de `audit_log` en verde
- [ ] pip-audit + gitleaks bloqueando un PR de prueba con secreto sembrado
- [ ] Región primaria y de réplica anotadas en §0; buckets y CRR verificados con un objeto de prueba
- [ ] Este runbook completo, con fecha e iniciales por sección
