# Habilitar la carga por `/cargas` — SIN AWS (disco persistente de Render)

**Decisión CEO (2026-08-02):** camino A. Nada de AWS. El original de cada carga se guarda en un
**disco persistente de Render** (sobrevive los redeploys). Todos los datos siguen en MongoDB; esto es
solo el archivador del `.xlsx` original (regla M-04, §1.6). Object Lock / inmutabilidad = go-live.

## Qué lee el código

`procesar_carga` acepta la carga si hay dónde preservar el original. Con el env **`ORIGINALES_DIR`**
apuntando a una carpeta, el original se escribe ahí (`local://{ruta}`) y la carga pasa (sin M-04). Si
esa carpeta es un **disco persistente**, el original no se pierde en el próximo deploy.

## Pasos (dashboard de Render — para Claude Chrome o a mano)

> Todo en `dashboard.render.com`. `[ANDRÉS]` = paso que hace el humano (login).

```
[ANDRÉS] Inicia sesión en Render.
1. Abre el servicio web "compas-api" (NO el worker "compas-jobs").
2. Ve a la sección "Disks" (o Settings → Disks) → "Add Disk":
   - Name: originales
   - Mount Path: /var/data/originales
   - Size: 1 GB
   → guardar.
3. Ve a "Environment" → "Add Environment Variable":
   - Key: ORIGINALES_DIR
   - Value: /var/data/originales
   → "Save changes" (dispara redeploy).
4. Espera a que el servicio vuelva a estado "Live".
```

> Nota: un disco persistente ata el servicio a **1 instancia** (correcto hoy: compas-api es 1
> instancia). Requiere plan de pago (compas-api ya es Standard).

## Verificación

1. En COMPAS → `/cargas` → subir `Global66_MovimientosCuentaCOP_2026-07.xlsx`.
   Esperado: **565 · ~86 creadas / ~479 duplicadas / 0 errores**, sin M-04.
2. La data queda en Mongo (los movimientos); el original queda en el disco
   (`/var/data/originales/{hash}.xlsx`).

## Diagnóstico

- **"M-04"** al subir: falta `ORIGINALES_DIR` en `compas-api`, o el redeploy no terminó.

## Para go-live (después, no ahora)

Endurecer el archivo a S3 con Object Lock (inmutable) — está descrito en `RUNBOOK-INFRA §6`. Es solo
config: el código ya soporta S3 (`S3_BUCKET` + llaves) sin tocar nada más. No es urgente y no bloquea nada.
