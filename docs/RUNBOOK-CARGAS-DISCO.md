# Habilitar la carga por `/cargas` — SIN AWS

**Decisión CEO (2026-08-02):** nada de AWS. Todos los datos siguen en MongoDB; esto es solo dónde se
guarda el `.xlsx` original de cada carga (regla M-04, §1.6). El código acepta la carga si `ORIGINALES_DIR`
apunta a una carpeta escribible (la crea sola con `mkdir`). Object Lock / inmutabilidad = go-live.

## Dos opciones

| | **Opción 1 — Gratis, ya** | **Opción 2 — Disco persistente (pago)** |
|---|---|---|
| Acción | env `ORIGINALES_DIR=/tmp/originales` | upgrade compas-api a Starter + disco + env |
| `/cargas` funciona | Sí | Sí |
| Datos (movimientos) → Mongo | Durables | Durables |
| Archivo original `.xlsx` | Efímero (se pierde en redeploy/spin-down) | Durable |
| Costo | Ninguno | ~US$7/mes |

**compas-api está en plan Free** → los discos persistentes exigen Starter (pago). Por eso la Opción 1
es la vía sin fricción para hoy; el archivado durable del original es endurecimiento de go-live.

## Opción 1 — pasos (Render, `dashboard.render.com`)

> `[ANDRÉS]` = login (humano).

```
[ANDRÉS] Inicia sesión en Render.
1. Abre el servicio web "compas-api" (NO el worker "compas-jobs") → "Environment".
2. "Add Environment Variable":
   - Key:   ORIGINALES_DIR
   - Value: /tmp/originales
   → "Save changes" (dispara redeploy).
3. Espera a estado "Live".
```

## Opción 2 — pasos (cuando quieras el original durable)

```
[ANDRÉS] Upgrade de compas-api a Starter (cambio de facturación — lo haces tú).
1. compas-api → "Disks" → "Add Disk": name=originales, mount=/var/data/originales, size=1 GB.
2. "Environment" → ORIGINALES_DIR = /var/data/originales → "Save changes".
3. Espera a "Live".
```

## Verificación (cualquiera de las dos)

1. COMPAS → `/cargas` → subir `Global66_MovimientosCuentaCOP_2026-07.xlsx`.
   Esperado: **565 · ~86 creadas / ~479 duplicadas / 0 errores**, sin M-04.
2. Los movimientos quedan en Mongo. (Con Opción 2, el original queda en el disco;
   con Opción 1, el original es transitorio — tú conservas el `.xlsx`.)

## Diagnóstico

- **"M-04"** al subir: falta `ORIGINALES_DIR`, o el redeploy no terminó.

## Para go-live (después, no ahora)

Endurecer el archivo a S3 con Object Lock (inmutable), descrito en `RUNBOOK-INFRA §6`. El código ya
soporta S3 (`S3_BUCKET` + llaves) sin tocar nada más. No es urgente y no bloquea nada.
