# Go-live Vigilante — "paquete del lunes" — runbook del CEO

> Encender la pieza 1 del Vigilante (paquete semanal del lunes 7:00, borrador→"publicar").
> El código ya está en `main` (rama `feat/fabs-vigilante-paquete-lunes`, gate-waiver GO CEO,
> Kimi retroactivo pendiente). Falta SOLO operación — nada de esto toca código.
> Servicio nuevo a levantar: worker **`compas-jobs`** (hoy NO existe en Render — ver Paso 0).
> Flags: `CFO_ENABLED` (ya encendido en prod desde rebanada 1 de escenarios) + `RUN_SCHEDULER`.

## Qué hace esta pieza (una vez viva)
Cada **lunes 7:00 América/Bogotá**, el worker corre un job que le pide a FABS (el mismo
`servicio.consultar` que ya usás por Telegram — caja hoy, rumbo, IVA del cuatrimestre,
gasto vs. mes pasado, todo con evidencia) que arme el paquete de la semana. El resultado
**NO se difunde solo**: se guarda como borrador y se te envía a vos (el "revisor",
`VIGILANTE_REVISOR_TELEGRAM_ID`) por Telegram con el texto:
> 📋 Borrador del paquete del lunes … Respondé 'publicar' para difundirlo al comité.

Vos revisás el borrador. Si respondés **"publicar"** (solo vos, ese exacto texto),
FABS lo reenvía TAL CUAL a todos los vinculados del piloto (comité) y audita el evento.
Si no respondés nada, el borrador se queda guardado — nadie más lo ve. Un solo paquete
por semana (si ya existe el de esta semana, el job no regenera otro).

## Regla de seguridad (por qué algunos pasos los haces TÚ y no el agente)
Igual que en el go-live de Telegram (`GO-LIVE-TELEGRAM.md`): ningún agente teclea
**secretos** (API keys, tokens, tu contraseña/MFA). Los pasos 🔴 son tuyos, a mano;
Claude-in-Chrome solo ayuda en los 🟢.

## Precondición: el worker `compas-jobs` HOY NO EXISTE en Render
`render.yaml` lo tiene **comentado a propósito** (se difirió cuando no había jobs
todavía — ver `docs/RUNBOOK-INFRA.md` línea 55, ítem sin marcar). Ahora que el paquete
del lunes es el primer job real, hay que crearlo. Esto es un servicio nuevo con costo
(~$7 USD/mes, plan Starter — Render no ofrece Free para workers), así que es una
**decisión tuya**, no algo que un agente deba destrabar solo.

### Paso 0. 🔴 TÚ — decide y crea el worker en Render
1. En `render.yaml` (repo, rama que vaya a `main`) descomenta el bloque `# type: worker
   / name: compas-jobs` (líneas ~50-82). Puedo prepararte el commit si me das el OK.
2. En Render → **New → Background Worker** (o deja que el Blueprint lo cree al hacer
   push de ese `render.yaml`) → confirmá:
   - **Plan: Starter** (nunca Free — los workers no duermen y necesitás que corra el lunes
     a las 7:00 en punto).
   - **1 sola instancia, siempre** — jamás escalar horizontal (dos schedulers duplicarían
     el paquete/otros jobs futuros).
   - `rootDir: backend`, `startCommand: python -m app.jobs.scheduler` (ya viene así en
     el blueprint).

## Rutas
| Qué | Ruta |
|---|---|
| Render (envs del worker) | dashboard.render.com → servicio **compas-jobs** → **Environment** |
| Render (envs de la API, ya configuradas) | dashboard.render.com → servicio **compas-api** → **Environment** |
| Logs del worker (para confirmar que corrió el lunes) | dashboard.render.com → **compas-jobs** → **Logs** |
| Telegram (donde llega el borrador y donde respondés "publicar") | tu chat con el bot FABS |

## Precondiciones
- **El worker `compas-jobs` existe y corre** (Paso 0).
- **El piloto de Telegram ya está vivo** (`GO-LIVE-TELEGRAM.md` completo): vos y el
  comité ya están vinculados (`telegram_id ↔ user_id`), el bot responde por Telegram.
- **Tu `telegram_id`** (el mismo número que usaste al vincularte en el go-live de
  Telegram — si no lo tenés a mano, escribile cualquier texto al bot desde una cuenta
  no vinculada y te lo va a mostrar).

---

## Pasos (en orden)

### Paso 0. 🔴 TÚ — crea el worker (ver arriba)

### Paso 1. 🔴 TÚ — Render `compas-jobs` → Environment → agrega las variables
| Key | Value |
|---|---|
| `RUN_SCHEDULER` | `true` — **SOLO aquí, nunca en `compas-api`** (regla innegociable #6 de `CLAUDE.md`) |
| `CFO_ENABLED` | `true` — el job es un no-op silencioso si esto está apagado |
| `ANTHROPIC_API_KEY` | la misma que ya usás en `compas-api` para el piloto de Telegram |
| `TELEGRAM_BOT_TOKEN` | el mismo token del bot que ya usás en `compas-api` |
| `VIGILANTE_REVISOR_TELEGRAM_ID` | **tu** `telegram_id` (el número, sin comillas — solo vos recibís el borrador y solo vos podés responder "publicar") |

También necesita las mismas variables de infraestructura que la API (`MONGODB_URI_COMPAS`,
`MONGODB_URI_AUDIT`, `APP_ENV`, `TZ=America/Bogota` — el job depende de esta TZ para
disparar el lunes a las 7:00 en punto, no a otra hora). Ya vienen declaradas en el
bloque `render.yaml` que descomentaste en el Paso 0; solo cargá los valores (`sync: false`
= los pega Render, no van al repo).

Guarda → Render redespliega el worker (~2-3 min).

### Paso 2. 🟡 Verificación (sin esperar al lunes)
No hace falta esperar al lunes para confirmar que el worker arrancó bien:
1. Abrí los **Logs** de `compas-jobs` en Render. Deberías ver algo como
   `compas-jobs arriba (... jobs registrados). TZ=America/Bogota` sin excepciones.
2. Confirmá que el job quedó registrado con `id="vigilante_paquete_lunes"`, cron
   `lunes 7:00`. Si el worker se reinicia varias veces seguidas (crash loop), avisame —
   revisamos las envs juntos antes de dejarlo correr solo.
3. **No hay un botón para "correrlo ahora"** a propósito (evita duplicar el paquete de
   una semana real); el próximo lunes 7:00 es la primera corrida real.

### Paso 3. ✅ El lunes 7:00
1. El worker corre el job, arma el paquete (vía FABS/`consultar`, con evidencia) y te lo
   envía por Telegram como borrador.
2. Lo leés. Si está bien, respondé **"publicar"** (tal cual, sin comillas) desde tu
   chat con el bot.
3. FABS reenvía el mismo texto del borrador (nunca lo recalcula ni vuelve a llamar al
   LLM) a todos los vinculados del comité y te confirma "✅ Paquete publicado al comité
   (N destinatarios)".
4. Si no respondés nada, no pasa nada — el borrador queda guardado, nadie más lo ve.

### Qué pasa si algo falla (fail-soft, por diseño)
- **`VIGILANTE_REVISOR_TELEGRAM_ID` sin configurar:** el job igual genera y guarda el
  paquete (queda en `estado='borrador'`), pero no te llega ningún mensaje — revisá los
  logs del worker si un lunes no recibiste nada.
- **El job revienta por cualquier motivo** (ej. Anthropic caído): queda en el log del
  worker, no tumba el proceso — el próximo lunes lo vuelve a intentar.
- **Ya existe un paquete de esta semana** (ej. el worker se reinició y el cron re-disparó):
  el job no regenera ni reenvía otro — un paquete por semana.
- **`CFO_ENABLED=false`:** el job es un no-op total (ni siquiera llama a FABS). Útil si
  necesitás apagar el piloto sin tocar el worker.

## Qué NO hace todavía esta pieza (piezas siguientes del Vigilante)
- Alerta proactiva por umbral de caja (cuando el rumbo cruza el piso) — pendiente.
- Cierre mensual asistido — pendiente.
- No hay endpoint ni pantalla en COMPAS para leer el historial de paquetes — solo Telegram.

---

## Alerta de caja

> El mismo worker **`compas-jobs`** corre la segunda pieza del Vigilante: una alerta proactiva
> diaria (8:00 América/Bogotá) cuando la caja proyectada cruza el umbral crítico (`caja_minima`)
> o se acerca (umbral de atención `UMBRAL_ATENCION`). Complementa el paquete del lunes (que es
> semanal, determinista, sin LLM) con vigilancia continua de la salud de caja.

### Qué hace esta pieza (una vez viva)
Cada **día 8:00 América/Bogotá**, el worker corre un job que:
1. Calcula la proyección REAL desde hoy (E1+D2 del motor, vía `rumbo_caja`).
2. Verifica si la caja real en los últimos bancos reportados + la caja proyectada hasta el horizonte (default 6 meses) cruza:
   - **Umbral crítico (`caja_minima`):** genera alerta severidad CRÍTICA.
   - **Umbral de atención (`UMBRAL_ATENCION`):** genera alerta severidad ATENCIÓN.
3. Si hay una alerta nueva (no duplicada de días anteriores):
   - La guarda como borrador con el mismo patrón que el paquete del lunes.
   - Te la envía a vos (el revisor) por Telegram: **"⚠️ Alerta de caja: [severidad]…"**
4. Vos revisás. Si respondés **"publicar alerta"** (tal cual, ese texto), FABS la reenvía al comité y audita el evento.

**Nota:** la alerta _real_ depende de que los bancos reporten el saldo diario. Si no hay datos
bancarios frescos, el job abstiene (no publica alerta falsa) — anotará en el log que espera
datos.

### Configuración (Paso 1 de GO-LIVE-VIGILANTE.md se aplica aquí también)
En Render → **compas-jobs** → **Environment**:

| Key | Value |
|---|---|
| `ALERTA_CAJA_ACTIVA` | `{"activa": true}` — por defecto OFF. Encenderla activa el job diario. |
| `ALERTA_CAJA_HORIZONTE_MESES` | (Opcional) `{"meses": 6}` — cuán lejos adelante proyectar (default 6 meses). |

### Umbrales — dónde se editan
Los dos umbrales (crítico y atención) **no se configuran aquí** — se editan en la pantalla **Supuestos**
de COMPAS como una fila más, igual que ahora:
- **`caja_minima`** (umbral crítico, ej. $50M).
- **`UMBRAL_ATENCION`** (umbral de atención, ej. $100M, > crítico).

El job lee esos valores cada ejecución (no precisa restart del worker si los cambiás).

### Qué pasa si algo falla
- **`ALERTA_CAJA_ACTIVA` sin configurar / `"activa": false`:** el job es un no-op (ni siquiera corre la proyección).
- **Sin datos bancarios frescos:** el job se abstiene — documentado en logs, no dispara alerta fantasma.
- **Proyección falla:** fail-soft; audita sin bloquear el worker.
- **Ya existe una alerta de la misma severidad hoy:** el job no regenera otra — una alerta por día por severidad.
- **Revisor no responde:** alerta queda en `estado='borrador'`, nadie más la ve hasta que vos respondas "publicar alerta".

## Prompt para Claude-in-Chrome (verificar salud del worker, sin tocar secretos)
```
Estás controlando mi Chrome real. REGLA DURA: no teclees NUNCA secretos (API keys,
tokens, contraseñas, códigos MFA). Si un paso los necesita, DETENTE y pedime que lo
haga yo.

TAREA — verificar que el worker compas-jobs está sano:
1. Abrí dashboard.render.com, entrá al servicio compas-jobs → Logs.
2. Decime si ves la línea "compas-jobs arriba" sin excepciones justo después del
   último deploy, y si hay algún error/crash-loop reciente.
3. NO edites ninguna variable de entorno vos mismo — si hace falta cambiar algo,
   decime cuál y lo hago yo.
```

---
*Escrito 2026-08-30 (Task 5, cierre SDD de `feat/fabs-vigilante-paquete-lunes`). Depende
de ops (Paso 0: crear el worker + envs) para correr en vivo — el merge a `main` no
necesita nada de esto (fakes cubren todo en tests).*
