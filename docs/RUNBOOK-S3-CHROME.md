# Tarea para Claude Chrome — habilitar la carga por `/cargas` (S3)

> Pégale a Claude Chrome el bloque de abajo (desde "TAREA" hasta el final). Antes,
> confirma los 3 valores del recuadro. Es todo por consola web; no hay línea de comandos.

**Contexto para el humano (Andrés):** hoy `/cargas` falla con **M-04** porque falta la config de S3.
El usuario IAM **`compas-app`** y sus llaves **ya están en Render** (inventario §8 de RUNBOOK-INFRA), así
que **no hay que crear usuario ni pegar secretos nuevos** — solo: (1) crear el bucket con Object Lock,
(2) darle permiso a `compas-app` sobre ese bucket, (3) agregar `S3_BUCKET` en Render.

**Valores (confírmalos antes de empezar):**
- **Bucket:** `compas-archivo` (si está tomado, usa `compas-archivo-roddos`)
- **Región:** US East (Ohio) `us-east-2` — la misma de Render
- **Retención Object Lock:** Compliance, 1 año

---

```
TAREA (para Claude Chrome)

Objetivo: dejar operativa la carga de extractos en COMPAS. Vas a trabajar SOLO en la
consola web de AWS y en el dashboard de Render.

Reglas:
- Nada de línea de comandos; todo por la interfaz web.
- Cuando un paso diga [ANDRÉS], DETENTE y pídele a Andrés que lo haga (inicios de
  sesión y cualquier credencial/secreto). No intentes autenticarte ni escribir llaves.
- Ve paso a paso. Tras cada paso, dime qué viste (nombre creado, confirmación) antes
  de continuar. Si algo no coincide con lo descrito, para y pregunta.

Valores a usar: Bucket = compas-archivo ; Región = US East (Ohio) us-east-2 ;
Retención = Compliance, 1 año.

PARTE 1 — AWS (console.aws.amazon.com)
[ANDRÉS] Inicia sesión en la consola de AWS y avísame.
1. Arriba a la derecha, selecciona la región "US East (Ohio) us-east-2".
2. Ve al servicio S3 → botón "Create bucket".
3. Bucket name: compas-archivo. Region: US East (Ohio) us-east-2.
4. Busca la sección "Object Lock" → márcala en "Enable" y activa la casilla
   "I acknowledge that enabling Object Lock...". (Object Lock SOLO se puede activar
   al crear el bucket; si esto no aparece, avísame antes de seguir.)
5. Deja "Block all public access" ACTIVADO (como viene por defecto).
6. "Create bucket". Confírmame que se creó.
7. Entra al bucket compas-archivo → pestaña "Properties".
8. Busca "Object Lock" → "Edit" → Default retention: "Enable", Mode: "Compliance",
   Retention period: 1 "Years" → "Save changes". Confírmame.
9. Ve al servicio IAM → "Users". Busca el usuario "compas-app" y ábrelo.
   (Si no existe un usuario con ese nombre, DETENTE y pregúntale a Andrés cuál es el
   usuario IAM cuyas llaves usa la app.)
10. En la pestaña "Permissions" → "Add permissions" → "Create inline policy" →
    pestaña "JSON". Pega EXACTAMENTE esto (además de las políticas que ya tenga):
    {
      "Version": "2012-10-17",
      "Statement": [{
        "Sid": "CompasArchivoRW",
        "Effect": "Allow",
        "Action": ["s3:PutObject", "s3:GetObject"],
        "Resource": "arn:aws:s3:::compas-archivo/originales/*"
      }]
    }
    → "Next" → nombre "compas-archivo-rw" → "Create policy". Confírmame.

PARTE 2 — Render (dashboard.render.com)
[ANDRÉS] Inicia sesión en Render y avísame.
11. Abre el servicio web "compas-api" (el que sirve la app; NO el worker
    "compas-jobs") → pestaña "Environment".
12. Revisa la lista de variables y dime si YA existen estas dos:
    AWS_ACCESS_KEY_ID  y  AWS_SECRET_ACCESS_KEY.
    - Si YA existen: NO las toques (son las de compas-app).
    - Si NO existen: DETENTE y dile a Andrés que él debe agregarlas con las llaves de
      compas-app (son secretas; no las manejo yo).
13. Agrega una variable nueva: Key = S3_BUCKET, Value = compas-archivo.
14. Revisa si existe AWS_DEFAULT_REGION. Si no, agrégala: Value = us-east-2.
    Si existe con otro valor, avísale a Andrés antes de cambiarla.
15. "Save changes" (esto dispara un redeploy). Dime cuándo el servicio vuelva a
    estado "Live".

PARTE 3 — Verificación
16. [ANDRÉS] En COMPAS, entra a /cargas y sube el archivo
    Global66_MovimientosCuentaCOP_2026-07.xlsx.
    Esperado: 565 total · ~86 creadas / ~479 duplicadas / 0 errores, SIN error M-04.
17. En AWS → S3 → bucket compas-archivo → carpeta "originales/": confirma que
    apareció un archivo .xlsx. Dime el nombre.

Diagnóstico si algo falla:
- Error "M-04" al subir: falta S3_BUCKET en compas-api, o el redeploy no terminó.
- Error "403 / AccessDenied" al subir: la política IAM (paso 10) o la región no
  cuadran. Revisa que el Resource sea arn:aws:s3:::compas-archivo/originales/* y que
  AWS_DEFAULT_REGION = us-east-2.
FIN DE LA TAREA
```

---

**Notas para Andrés (no van a Chrome):**
- Los nombres de env que lee el código son EXACTOS: `S3_BUCKET`, `AWS_ACCESS_KEY_ID`,
  `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`. Si las llaves de `compas-app` en Render están con
  otros nombres, hay que exponerlas también con estos.
- Object Lock **Compliance es irreversible**: los objetos subidos no se borran hasta expirar (ni con
  root). Por eso 1 año en dev. Endurecer a más años es decisión de go-live.
- Si el usuario IAM real no es `compas-app`, dale a Chrome el nombre correcto en el paso 9.
