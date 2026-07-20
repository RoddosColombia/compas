# S0-06 / S0-07 — Aprovisionar la infra de COMPAS (para desbloquear el Bloque C del Gate G1)

**Contexto:** COMPAS **no está desplegado**. Hay que crear los servicios desde `render.yaml`,
aprovisionar Atlas, cargar secretos, y conectar Vercel/AWS. `roddos-api`/`roddos-scoring-api` son de
OTRO producto — **no tocar**. Región = **Ohio** (heredada de SISMO, ya fijada en `render.yaml`).

**Ejecutores:** **Terminal** (tú — tu cadena de Atlas nunca sale de tu máquina) · **Chrome** (Claude
en Chrome, todo lo web) · **Claude Code** (yo — `gh`, análisis, evaluación).

**Ruta crítica (lo mínimo para C1/C4):** Fase 1 (Atlas) → Fase 2 (secretos) → Fase 3 (Blueprint
staging arriba) → C1/C4. Prod (C2), Vercel, AWS (C5) en paralelo/después.

---

## ⚠️ DECISIÓN 1 (C2) — plan de GitHub
El *required reviewer* de producción (C2) **necesita plan Team** (en repo privado Free no se puede;
lo confirmé: HTTP 422). Opciones:
- **(a) Subir `RoddosColombia` a GitHub Team** (~US$4/usuario/mes) → habilito el environment
  `production` con reviewer = tú, vía `gh` (1 comando). Es la opción "de manual".
- **(b) Control alternativo sin costo:** producción ya es `autoDeploy:false` en Render (no despliega
  sola) + tags `v*` protegidos (solo tú los creas) + deploy manual en Render. Documentamos ESO como
  el control de C2. Cumple el espíritu (nada llega a prod sin acción deliberada tuya), sin reviewer nativo.
- **Mi recomendación:** (b) por ahora (no gastar), y (a) cuando quieras el gate humano formal.
- ✅ **DECISIÓN DEL CEO (20-jul-2026): opción (b)** — control sin costo. Documentado en RUNBOOK §9 y
  G1-CHECKLIST C2. La Fase 4 queda como (b); si en el futuro se sube a Team, se activa (a) con 1 comando `gh`.

---

## Fase 1 — Atlas (cluster M10 existente)
### 1a. Usuarios de app  *(Chrome en Atlas UI, o tú)* — Database Access → Add New Database User
- `compas_app` → rol **readWrite @ `compas`** (contraseña alfanumérica, guárdala).
- `compas_app_stg` → rol **readWrite @ `compas_stg`**.
Copia la connection string que da Atlas para cada uno → serán `MONGODB_URI_COMPAS` (prod y stg).

### 1b. Rol de auditoría + índices + semillas  *(Terminal, tú)* — con tu `<ADMIN_URI>`
```powershell
cd C:\Users\AndresSanJuan\roddos-workspace\COMPAS
python -m pip install -r backend/requirements.txt
# staging:
python scripts/create_audit_role.py "<ADMIN_URI>" compas_stg      # pide clave compas_audit (alfanum, ≥16)
python scripts/create_auth_indexes.py "<ADMIN_URI>" compas_stg
python migrations/20260901_seed_rubros.py "<ADMIN_URI>" compas_stg
python migrations/20260901_seed_configuracion.py "<ADMIN_URI>" compas_stg
# prod (mismos 4, cambiando la base):
python scripts/create_audit_role.py "<ADMIN_URI>" compas
python scripts/create_auth_indexes.py "<ADMIN_URI>" compas
python migrations/20260901_seed_rubros.py "<ADMIN_URI>" compas
python migrations/20260901_seed_configuracion.py "<ADMIN_URI>" compas
```
Corre cada bloque **2 veces** (evidencia de idempotencia: "N nuevos" → "0 nuevos").

## Fase 2 — Generar secretos de app  *(Terminal, tú)*
```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"                       # JWT_SECRET
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # MFA_ENC_KEY
```
Ensambla (con la clave de `compas_audit` de la Fase 1b):
- `MONGODB_URI_AUDIT` prod: `mongodb+srv://compas_audit:<CLAVE>@<cluster-host>/compas?authSource=compas`
- `MONGODB_URI_AUDIT` stg:  `mongodb+srv://compas_audit:<CLAVE>@<cluster-host>/compas_stg?authSource=compas_stg`

## Fase 3 — Render: aplicar el Blueprint  *(Chrome)*
**Prompt Chrome:**
```
En Render, crea servicios desde un Blueprint: botón "New +" → "Blueprint". Conecta el repositorio
de GitHub "RoddosColombia/compas" (rama main). Render leerá el archivo render.yaml y propondrá crear
3 servicios: compas-api, compas-jobs, compas-api-stg (región Ohio). Continúa hasta la pantalla donde
pide las variables marcadas "sync:false". NO inventes valores: repórtame la lista EXACTA de variables
que Render pide por cada servicio y detente ahí (yo te paso los valores para pegar).
```
**Valores a cargar (te los da el resultado de Fases 1–2). Tabla por servicio:**

| Variable | compas-api (prod) | compas-jobs | compas-api-stg |
|---|:-:|:-:|:-:|
| MONGODB_URI_COMPAS | →`compas` | →`compas` | →`compas_stg` |
| MONGODB_URI_AUDIT | prod | prod | stg |
| JWT_SECRET | (mismo prod) | (mismo prod) | (uno para stg) |
| MFA_ENC_KEY | ✅ | — | ✅ |
| SENTRY_DSN | opcional* | opcional* | — |
| AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / S3_BUCKET | Fase 6* | Fase 6* | — |
| BETTER_STACK_HEARTBEATS | — | opcional* | — |

\* **No bloquean el arranque ni C1.** Los 4 críticos (fail-fast) son **MONGODB_URI_COMPAS,
MONGODB_URI_AUDIT, JWT_SECRET, MFA_ENC_KEY**. Sentry/AWS/S3/BetterStack se pueden dejar para cuando
tengas las cuentas/llaves (gatean features posteriores, no el readiness). Con los 4 críticos, staging
arranca y C1 debe dar "ready".

Tras cargar y desplegar: `compas-api-stg` (autoDeploy:true) queda sirviendo; `compas-api`/`compas-jobs`
(autoDeploy:false) quedan creados pero sin desplegar hasta un deploy manual/tag.

## Fase 4 — GitHub environment `production` (según DECISIÓN 1)
- Opción (a): me dices "Team" cuando lo actives y corro el `gh` para poner el reviewer.
- Opción (b): documento el control alternativo en RUNBOOK §9 (Render manual + tags protegidos).

## Fase 5 — Vercel (frontend, para C4 web)  *(Chrome)*
**Prompt Chrome:**
```
En Vercel, importa un nuevo proyecto desde el repo GitHub "RoddosColombia/compas". Configura:
Root Directory = "frontend", framework = Vite. NO despliegues a producción todavía si pide
confirmación; primero repórtame qué variables de entorno pide (si pide) y la URL de preview que asigna.
```

## Fase 6 — AWS S3 (para C5 y las llaves del worker)  *(Chrome/consola)*
- IAM user `compas-app` (Get/Put sobre el prefijo `compas/*`, sin Delete) → `AWS_ACCESS_KEY_ID/SECRET`.
- Prefijos `compas/archivos/` y `compas/backups/`; bucket nuevo `compas-archivo` con Object Lock; CRR a 2ª región.
- `S3_BUCKET` = nombre del bucket. (Detalle en RUNBOOK §6.)

## Fase 7 — Cloudflare (diferible)
Dominios `compas.roddos.com` / `api.compas.roddos.com`. **Se puede diferir**: la URL `.onrender.com`
de staging basta para C1/C4. Cuando lo hagas, restringe el origen a IPs de Cloudflare (RUNBOOK §5).

---

## Verificación final (Bloque C) — Chrome, con `PROMPTS-CLAUDE-CHROME.md`
- **C1** readiness de `compas-api-stg` · **C4** cabeceras web+API · **C2** según Decisión 1 ·
  **C5** región+réplica AWS. Yo evalúo cada resultado contra el DoD y armo el paquete `G1-I`.

## Qué hago YO ahora / al recibir resultados
- GitHub env reviewer (si eliges Team).
- Registrar URLs reales en RUNBOOK §0/§3 conforme Chrome las reporte.
- Evaluar C1/C4 y cerrar el checklist; ensamblar el paquete final de G1 para Kimi.
