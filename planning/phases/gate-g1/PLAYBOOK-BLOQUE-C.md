# Playbook — Bloque C del Gate G1 (operacional · responsable: CEO/Andrés)

Paso a paso para producir la **evidencia operacional** que falta para el veredicto final de G1.
No depende de GitHub Actions (salvo **C3**, que sí espera al incidente, igual que A5/A6).
**Orden de la ruta crítica:** C6/C7 (secretos + Atlas) → C1 (readiness) → C4 (cabeceras).

> Cluster Atlas = **M10** (Opción A) → `createRole/createUser` funcionan por script. Si por lo que
> sea fuera Free/Flex, esos dos se hacen por **Atlas UI** (RUNBOOK §2). **Siempre `compas_stg` primero,
> luego `compas`.** Todos los scripts son **idempotentes**: re-correr no daña nada.

---

## C6 — Provisionar secretos en Render (valores)
En Render, servicios `compas-api`, `compas-jobs` (worker) y `compas-api-stg`, pestaña *Environment*:

1. **`MFA_ENC_KEY`** (Fernet, 32B urlsafe-b64). Genérala una vez:
   ```
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
   Pégala en `compas-api` y `compas-api-stg`. ⚠️ **Rotarla = re-enrolar MFA de todos** (RUNBOOK §8).
2. **`MONGODB_URI_AUDIT`** — cadena del usuario `compas_audit` (rol `audit_writer`), MISMA db `compas`.
   La obtienes en C7. Cárgala en `compas-api` y `compas-jobs`.
3. Verifica que `MONGODB_URI_COMPAS` / `_STG` y `JWT_SECRET` ya estén (RUNBOOK §8).

*Sin `MFA_ENC_KEY`/`MONGODB_URI_AUDIT` el arranque no-dev hace fail-fast a propósito (C-01/MFA).*

---

## C7 — Aprovisionar datos/roles en Atlas  *(el más importante — sin esto staging arranca vacío y el audit_log falla)*
Necesitas una **URI de admin** con privilegio `userAdmin` sobre la db. Corre **primero contra `compas_stg`**:

```bash
# 1) Rol audit_writer + usuario compas_audit (contraseña por env, ≥16 chars, NUNCA por argv)
COMPAS_AUDIT_PWD='<clave-fuerte-16+>' python scripts/create_audit_role.py "<ADMIN_URI>" compas_stg

# 2) Índices de auth (únicos email/jti + TTL de throttle)
python scripts/create_auth_indexes.py "<MONGODB_URI_STG>" compas_stg

# 3) Semillas idempotentes (32 rubros + config: UMBRAL, CALENDARIO_DIAN, DIAS_CREDITO)
python migrations/20260901_seed_rubros.py "<MONGODB_URI_STG>" compas_stg
python migrations/20260901_seed_configuracion.py "<MONGODB_URI_STG>" compas_stg
```
Cuando salga OK en staging, **repite los 4 contra `compas`** (cambiando `compas_stg`→`compas` y las URIs).
La cadena de `compas_audit` que armes en el paso 1 es la `MONGODB_URI_AUDIT` de **C6**.
**Evidencia G1:** pega los logs idempotentes de los 4 scripts (staging y prod).

---

## C1 — Readiness en staging (no solo liveness)
Con `compas-api-stg` desplegado y C6/C7 hechos:
```
curl -s https://<host-staging>/api/v1/health/ready
```
**Evidencia G1:** salida `{"status":"ready","mongo":"up","beanie":"ready"}`.
(`/health` daría 200 aunque Mongo esté caído — por eso G1 exige `/ready`, Kimi G-2.)

---

## C4 — Cabeceras de seguridad vivas (DoD #12)
```
curl -I https://compas.roddos.com            # SPA (Vercel)
curl -I https://api.compas.roddos.com/health # API (Render)
```
**Evidencia G1:** que aparezcan CSP / HSTS / X-Content-Type-Options: nosniff / Referrer-Policy /
X-Frame-Options. (HSTS puede venir de Cloudflare **y** del origen: benigno; solo define el dueño.)

---

## Resto del bloque C (completan G1)
- **C2 — Bloqueo de producción:** intenta desplegar a prod SIN tag `v*`+reviewer → debe fallar.
  Evidencia: captura del intento bloqueado. (Reviewer de prod = CEO + evidencia Kimi, CR-003.)
- **C3 — PR con secreto sembrado:** abre un PR de prueba con un secreto falso → pip-audit/gitleaks
  deben ponerlo ROJO. ⚠️ **Espera a que el incidente de Actions se resuelva** (igual que A5/A6).
- **C5 — Buckets + CRR:** anota región primaria/réplica en RUNBOOK §0; sube un objeto de prueba y
  verifica que replica. Evidencia: objeto replicado + notas §0.

---

## Cuando termines
Avísame con las evidencias (o dónde las dejaste). Yo: (1) apenas Actions vuelva, disparo el run verde
del PR #6 y corro el gate Kimi del código (cierra A5/A6); (2) con tu bloque C + A5/A6 verdes, genero
el paquete final `auditorias/G1-I/` para el veredicto de Kimi y el cierre del Sprint 0.
