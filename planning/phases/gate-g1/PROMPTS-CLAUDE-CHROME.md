# Bloque C — orquestación por herramienta + prompts para Claude Chrome

Dos ejecutores: **Terminal** (tú, en tu terminal — donde vive tu cadena de Atlas) y **Claude Chrome**
(todo lo web). Claude Code (yo) preparó los comandos/prompts y hace el análisis.

## Mapa de tareas
| Tarea | Herramienta | Estado |
|---|---|---|
| C7 — rol/usuario audit + índices + semillas (Atlas) | **Terminal (tú)** | comandos listos (mensaje previo / `CEO-PASOS-SIMPLES.md`) |
| Generar `MFA_ENC_KEY` | **Terminal (tú)** | 1 comando (abajo) |
| Obtener URLs de Render + estado Auto-Deploy | **Chrome** | Prompt 1 — *hazlo ya* |
| C6 — meter 2 secretos en Render | **Chrome** | Prompt 2 (tras generar valores) |
| C1 — readiness de staging | **Chrome** | Prompt 3 (tras C6 + redeploy) |
| C4 — cabeceras vivas web + API | **Chrome** | Prompt 4 |
| C2 — bloqueo de prod (Render + GitHub) | **Chrome** + 1 tag de terminal | Prompt 5 |
| C5 — región AWS + réplica | **Chrome** | Prompt 6 |

## Secuencia recomendada
1. **Chrome Prompt 1** (URLs de Render) — sin dependencias, arranca aquí.
2. **Terminal**: C7 (Atlas) + generar `MFA_ENC_KEY`.
3. **Chrome Prompt 2** (C6: secretos) — ya con los valores.
4. Staging redespliega solo → **Chrome Prompt 3** (C1) + **Prompt 4** (C4).
5. **Chrome Prompt 5** (C2) y **Prompt 6** (C5).

---

## Terminal (tú) — generar MFA_ENC_KEY
```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
Copia la línea que imprime: ese es el valor de `MFA_ENC_KEY` para el Prompt 2.

---

## PROMPT 1 — Render: URLs y Auto-Deploy  *(pégalo en Claude Chrome ahora)*
```
Estás en el dashboard de Render. Entra, uno por uno, a estos 3 servicios y NO cambies nada (solo leer):
compas-api, compas-api-stg, compas-jobs.
Para cada servicio dime:
1) la URL pública que aparece arriba (la .onrender.com o el dominio custom),
2) si es servicio web, si "Auto-Deploy" está On u Off,
3) confirma que existe la pestaña "Environment".
Devuélveme una tabla: servicio | URL | Auto-Deploy | ¿tiene Environment?
```

## PROMPT 2 — C6: secretos en Render  *(cuando ya tengas MFA_ENC_KEY y MONGODB_URI_AUDIT)*
> Reemplaza los `<...>` por los valores reales antes de pegar. Son **secretos**: solo van en el
> formulario de Render.
```
En Render, agrega variables de entorno (pestaña Environment de cada servicio; si ya existen, actualiza).
Guarda al final y confírmame en qué servicio quedó cada una:

- compas-api      → MFA_ENC_KEY = <LLAVE_FERNET>
- compas-api-stg  → MFA_ENC_KEY = <LLAVE_FERNET>
- compas-api      → MONGODB_URI_AUDIT = <URI_AUDIT_PROD>
- compas-jobs     → MONGODB_URI_AUDIT = <URI_AUDIT_PROD>
- compas-api-stg  → MONGODB_URI_AUDIT = <URI_AUDIT_STG>

(No pongas MFA_ENC_KEY en compas-jobs: el worker no verifica MFA.)
```
Donde:
- `<URI_AUDIT_PROD>` = `mongodb+srv://compas_audit:<CLAVE>@<cluster-host>/compas?authSource=compas`
- `<URI_AUDIT_STG>`  = `mongodb+srv://compas_audit:<CLAVE>@<cluster-host>/compas_stg?authSource=compas_stg`
- `<CLAVE>` = la contraseña de `compas_audit` que elegiste en C7 (alfanumérica).

## PROMPT 3 — C1: readiness de staging  *(tras C6 + redeploy)*
> Sustituye `<URL_API_STG>` por la URL de `compas-api-stg` del Prompt 1.
```
Navega a: <URL_API_STG>/api/v1/health/ready
Pégame TAL CUAL todo el JSON que devuelve. Debería ser algo como
{"status":"ready","mongo":"up","beanie":"ready"}. Dime los valores de status, mongo y beanie.
```

## PROMPT 4 — C4: cabeceras de seguridad vivas
> Sustituye `<URL_WEB>` (la SPA) y `<URL_API>` (usa la de prod `compas-api`, o la de staging).
```
Con las herramientas de red del navegador (pestaña Network), carga estas 2 URLs y para CADA una
dame el valor EXACTO de estas cabeceras de respuesta:
Content-Security-Policy, Strict-Transport-Security, X-Content-Type-Options, Referrer-Policy,
X-Frame-Options (o frame-ancestors dentro de CSP).
URLs:
- Web: <URL_WEB>
- API: <URL_API>/health
Devuélveme una tabla cabecera | valor, una por URL. Marca cuáles faltan.
```

## PROMPT 5 — C2: bloqueo de producción  *(control sin costo — decisión CEO opción b)*
```
En Render, servicio compas-api (producción), ve a Settings y dime:
1) si "Auto-Deploy" está en Off (debe estarlo),
2) confirma que un merge/push a main NO dispara deploy de compas-api (solo compas-api-stg despliega).
Repórtame ambas cosas con captura.
```
Evidencia de C2 = esa captura (Auto-Deploy OFF + prod no despliega solo). El deploy a prod es
manual/por tag, y solo el CEO (único admin del repo) puede crear tags `v*`. *(El reviewer nativo de
GitHub se difirió: requiere plan Team.)*

## PROMPT 6 — C5: región AWS + réplica
```
En la consola de AWS (S3), dime:
1) la región de los buckets de compas (el bucket principal y "compas-archivo"),
2) sube un archivo de prueba pequeño al prefijo compas/backups/ y dime si aparece replicado en el
   bucket de la segunda región (CRR).
Anota las dos regiones (primaria y réplica).
```

---

## Qué hago YO (Claude Code) con lo que te devuelva Chrome
- Prompt 1 → registro las URLs reales aquí y en el RUNBOOK §0.
- Prompt 3/4 → evalúo el JSON y las cabeceras contra el DoD (#12) y te digo si pasan o qué falta.
- Prompt 5(b) → empujo el tag y confirmo el bloqueo.
- Con todo verde → armo el paquete final `auditorias/G1-I/` para el veredicto de Kimi.
