# RUNBOOK — Infra S3 para la carga por `/cargas` (PR-S3 / M-04)

**Objetivo:** dejar operativa la carga de extractos por la app (el cierre de julio depende de esto).
Sin el env `S3_BUCKET` en Render, `/cargas` responde **M-04** (`OriginalNoPreservableError`) por diseño
(regla dura: no se acepta una carga si no hay dónde preservar el original).

**Qué lee el código** (`backend/app/cargas/storage.py` + `config.py`), nombres EXACTOS:

| Env (Render) | Lo usa | Nota |
|---|---|---|
| `S3_BUCKET` | destino de la subida | sin esto → M-04 |
| `AWS_ACCESS_KEY_ID` | credencial boto3 | del usuario IAM `compas-api` |
| `AWS_SECRET_ACCESS_KEY` | credencial boto3 | idem (se ve una sola vez al crearla) |
| `AWS_DEFAULT_REGION` | región de boto3 | = la región del bucket |

`subir_original` hace `put_object(Bucket, Key=originales/{hash}{ext}, Body)` **sin** parámetros de
retención → **el bucket debe tener una regla de retención POR DEFECTO** para que Object Lock aplique a
cada objeto automáticamente.

---

## Decisiones que debes tomar antes de empezar

1. **Nombre del bucket** — global en todo AWS, debe ser único. Sugerido: `compas-archivo-roddos`
   (si `compas-archivo` está libre, mejor). Sustituye `<BUCKET>` abajo.
2. **Región** — sugerida `us-east-1` (N. Virginia: más simple, no exige `LocationConstraint`, y Render
   corre en US). Sustituye `<REGION>`.
3. **Retención por defecto (Object Lock)** — **irreversible en modo COMPLIANCE**: ningún objeto (ni con
   root) se puede borrar antes de que expire. Object Lock **solo se puede habilitar al CREAR el bucket**.
   - Recomendación para AHORA (un solo entorno en desarrollo, el endurecimiento es de go-live):
     **COMPLIANCE, `1` año**. Cubre el original de julio y no compromete storage por una década.
   - Si quieres alinear a firmeza DIAN, `5` años. Sustituye `<RETENCION_ANIOS>`.
   - Alternativa si prefieres poder corregir en dev: modo `GOVERNANCE` (un usuario con permiso lo puede
     sobrescribir). El spec pidió COMPLIANCE; lo dejo a tu criterio.

---

## Camino A — AWS CLI (si tienes credenciales admin y el CLI instalado)

> Requiere estar autenticado como admin/root (`aws configure` ya hecho). Ejecuta en orden.

```bash
# Variables (edítalas)
BUCKET=compas-archivo-roddos
REGION=us-east-1
RET_ANIOS=1

# 1) Crear el bucket CON Object Lock (habilita versioning automáticamente).
#    Para us-east-1 NO se pasa LocationConstraint; para otra región, descomenta la línea.
aws s3api create-bucket \
  --bucket "$BUCKET" \
  --region "$REGION" \
  --object-lock-enabled-for-bucket
#  --create-bucket-configuration LocationConstraint="$REGION"   # <-- solo si REGION != us-east-1

# 2) Retención POR DEFECTO (COMPLIANCE) — para que cada put_object quede inmutable sin
#    que el código tenga que pedirlo. IRREVERSIBLE para los objetos que se suban.
aws s3api put-object-lock-configuration \
  --bucket "$BUCKET" \
  --object-lock-configuration "{\"ObjectLockEnabled\":\"Enabled\",\"Rule\":{\"DefaultRetention\":{\"Mode\":\"COMPLIANCE\",\"Years\":$RET_ANIOS}}}"

# 3) Bloquear TODO acceso público (defensa en profundidad).
aws s3api put-public-access-block \
  --bucket "$BUCKET" \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

# 4) Usuario IAM de mínimo privilegio para la app.
aws iam create-user --user-name compas-api

# 5) Política inline: solo Put/Get sobre originales/* de ESTE bucket (nada más).
aws iam put-user-policy \
  --user-name compas-api \
  --policy-name compas-api-s3-originales \
  --policy-document "{
    \"Version\": \"2012-10-17\",
    \"Statement\": [{
      \"Sid\": \"OriginalesRW\",
      \"Effect\": \"Allow\",
      \"Action\": [\"s3:PutObject\", \"s3:GetObject\"],
      \"Resource\": \"arn:aws:s3:::$BUCKET/originales/*\"
    }]
  }"

# 6) Crear la access key (GUARDA la salida: el secret se ve UNA sola vez).
aws iam create-access-key --user-name compas-api
#    -> AccessKeyId  = AWS_ACCESS_KEY_ID
#    -> SecretAccessKey = AWS_SECRET_ACCESS_KEY
```

## Camino B — Consola AWS (para Claude Chrome / a mano)

**B1. Crear el bucket (con Object Lock):** S3 → *Create bucket* →
- Name: `<BUCKET>` · Region: `<REGION>`.
- **Advanced settings → Object Lock → Enable** (marca "I acknowledge..."). *(Esto solo se puede aquí, al crear.)*
- Block Public Access: **dejar TODO activado** (por defecto).
- *Create bucket*.

**B2. Retención por defecto:** el bucket → pestaña **Properties** → *Object Lock* → *Edit* →
- Default retention: **Enable** · Mode: **Compliance** · Period: `<RETENCION_ANIOS>` **Years** → *Save*.

**B3. Usuario IAM:** IAM → Users → *Create user* → name `compas-api` → *sin* acceso a consola →
*Next* → **Attach policies → Create inline policy** → pestaña **JSON**, pega:
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "OriginalesRW",
    "Effect": "Allow",
    "Action": ["s3:PutObject", "s3:GetObject"],
    "Resource": "arn:aws:s3:::<BUCKET>/originales/*"
  }]
}
```
→ nombre `compas-api-s3-originales` → *Create* → *Create user*.

**B4. Access key:** el usuario `compas-api` → **Security credentials** → *Create access key* →
uso *Application running outside AWS* → *Create* → **copia `Access key` y `Secret access key`** (el
secret NO se vuelve a mostrar).

## Paso final — envs en Render (Claude Chrome / a mano)

Render → servicio **web** `compas-api` (el que sirve `/cargas`, NO el worker) → **Environment** →
*Add Environment Variable* (una por una), luego *Save changes* (dispara redeploy):

| Key | Value |
|---|---|
| `S3_BUCKET` | `<BUCKET>` |
| `AWS_ACCESS_KEY_ID` | el AccessKeyId del paso 6 / B4 |
| `AWS_SECRET_ACCESS_KEY` | el SecretAccessKey del paso 6 / B4 |
| `AWS_DEFAULT_REGION` | `<REGION>` |

> Los secretos NO van al repo (regla 12). Se pegan solo en Render. `docs/INVENTARIO-SECRETOS.xlsx`
> puede registrar su ubicación, no hace falta el valor aquí.

---

## Verificación (después del redeploy)

1. En la app, subir `docs/Global66_MovimientosCuentaCOP_2026-07.xlsx` por **/cargas**.
   - Esperado: **565 total · ~86 creadas / ~479 duplicadas / 0 errores** (sin M-04).
2. Confirmar que el original quedó en el bucket:
   ```bash
   aws s3api list-objects-v2 --bucket "$BUCKET" --prefix originales/
   # y verificar el candado de retención de un objeto:
   aws s3api head-object --bucket "$BUCKET" --key originales/<HASH>.xlsx
   #   -> debe traer ObjectLockMode=COMPLIANCE y ObjectLockRetainUntilDate futuro
   ```
3. Si sale **M-04** al subir: falta `S3_BUCKET` en el env del servicio web, o el redeploy no terminó.
4. Si sale **403 AccessDenied** al subir: la política IAM o la región/credenciales no cuadran
   (revisa que el `Resource` del policy apunte al bucket correcto y `AWS_DEFAULT_REGION` = región del bucket).

## Notas

- **Object Lock solo se habilita al crear el bucket.** Si el bucket ya existe sin él, hay que crear uno nuevo.
- **COMPLIANCE es irreversible**: los objetos subidos no se borran hasta que expire la retención, ni con root.
  Por eso se recomienda empezar con retención corta en el entorno de desarrollo.
- El código sube **antes de insertar** la carga (fail-closed): si S3 rechaza, la carga se aborta sin
  persistir nada (no hay dinero fantasma).
