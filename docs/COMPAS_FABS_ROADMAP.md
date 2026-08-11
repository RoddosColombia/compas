# FABS — Roadmap de desarrollo (artefacto vivo)

> **Qué es:** el artefacto de control ÚNICO del avance de FABS (agente CFO de RODDOS).
> Muestra la evolución fase a fase en el tiempo, no solo la foto de hoy. **Manda sobre
> cualquier presentación o correo:** si algo lo contradice, gana este archivo.
>
> **Mecánica de actualización (regla del CEO 2026-08-10):** se actualiza **tan pronto
> cierra cada desarrollo** (no al final del incremento). Cada cambio queda **fechado** en
> el Registro de cambios (§4). Responsable de revisarlo: Claude, en cada cierre de pieza.
>
> **Gobierno:** FABS es un módulo interno de COMPAS (`backend/app/cfo/`) detrás del flag
> `CFO_ENABLED` (apagado). Todo lo que toca lectura/cálculo de plata va con gate Kimi.
> Decisiones fundacionales en memoria `fabs-fundacion-decisiones` y en los specs de
> `docs/superpowers/specs/`. Reglas innegociables: las de `CLAUDE.md`.

## 1. Norte de FABS (una línea)

Analista financiero de IA que responde con **cifras reales y trazables** desde COMPAS,
vigila la caja y prepara el Comité de Pagos — **sin ejecutar operaciones y sin inventar
ni una cifra** (el modelo nunca calcula; COMPAS calcula, FABS narra con evidencia).

## 2. Fases / incrementos

Estado: ⬜ Pendiente · 🟡 En curso · ✅ Hecho · 🔒 Bloqueado

| # | Incremento | Qué entrega | Gate | Estado |
|---|---|---|---|---|
| **1** | **Cimiento determinista** (sin LLM) | `app/cfo/calc` (3 conceptos: caja hoy · runway · IVA cuatrimestre, cada cifra con evidencia) + arnés de goldens (`cfo/goldens`) + salvaguarda S1 + flag `CFO_ENABLED`. Motor COMPAS cero diffs. | Kimi (lee cifras de plata) | ✅ Hecho (rama `feat/fabs-inc1`; falta merge a main tras gate) |
| **2** | **Loop del agente + cifra→evidencia** | Loop con SDK Anthropic (temp 0.1, límites), verificador cifra→evidencia invocado antes de publicar, endpoint `/api/v1/cfo` bajo flag, salida tipada. Primeros eventos `cfo.*` (CR). | Kimi (crítico) + CR eventos | ⬜ Pendiente |
| **3** | **Canal Telegram + piloto Q&A** | Webhook Telegram en compas-api, vínculo `telegram_id↔user_id`, hilos por usuario (`cfo_hilos`, sin TTL naïve), observabilidad. Piloto pregunta-respuesta (CEO/CGO/CFO). | G2 (núcleo confiable) | ⬜ Pendiente |
| **4** | **Vigilante + Comité de Pagos** | Jobs `cfo_*` en el Worker (alertas por umbral, paquete del lunes 7:00, cierre mensual comentado) — borrador con liberación humana. | G3 (piloto→operación) | ⬜ Pendiente |
| **5** | **Chat embebido en COMPAS** | Panel de chat en la app (SSE), mismo hilo por usuario que Telegram, RBAC de COMPAS. | — | ⬜ Pendiente |
| **6** | **Evolución** (post-estabilización) | Provisión de IVA como tesorería, proyecciones de escenario conversacionales, Teams, reporte inversionistas. | — | ⬜ Pendiente |

## 3. Gates y prerrequisitos

| Gate | Cuándo | Debe cumplirse |
|---|---|---|
| Kimi (por incremento crítico) | antes de cada merge que toque cálculo/lectura de plata | nota ≥ 9.0 + GO CEO; si Kimi ausente, gate-waiver del CEO + auditoría retroactiva |
| G2 — núcleo confiable | cierre incremento 3 | evals ≥ objetivos; 0 cifras sin evidencia; 0 fallos de parseo; determinismo verificado |
| G3 — piloto→operación | ventana 4-5 semanas (incremento 4) | 2 lunes de Comité reales sin corrección de cifras + 1 cierre validado por Fabián; ≤3 correcciones, ninguna >0,5% del flujo |

**Prerrequisitos / dependencias externas:**
- **Datos frescos (Liz):** cargas al día (movs+caja diario, cartera mensual, facturas).
- **Golden set completo (Fabián):** los 240+60 casos con respuesta a mano — incremento ≥3 (el incremento 1 trae solo el arnés + semilla).
- **LoanTape (SISMO-V3):** para cartera fina; hoy `loantape_creditos` vacía. Ligado a CR-PTS6F.
- **Sunset del CFO legado de SISMO-V2** (D1): higiene previa; el flag de FABS no apaga al legado.
- **Presupuesto operativo:** $30 USD/mes (aplica desde el incremento 2, cuando entra el LLM).

## 4. Registro de cambios (fechado, append-only)

| Fecha | Incremento | Qué cerró / cambió | Evidencia |
|---|---|---|---|
| 2026-08-10 | 1 | Spec del incremento 1 aprobado por el CEO | `docs/superpowers/specs/2026-08-10-fabs-cimiento-determinista-design.md` (commit 898d3c9) |
| 2026-08-10 | 1 | Plan de implementación escrito + roadmap creado | `docs/superpowers/plans/2026-08-10-fabs-cimiento-determinista.md` |
| 2026-08-11 | 1 | **Incremento 1 CONSTRUIDO** (SDD, 11 tasks, subagente+review por tarea). `app/cfo/`: evidencia · flag · 3 conceptos · refactor DRY `liquidacion_iva()` · modelo/runner/semilla de goldens · guard S1. Suite COMPAS **940 passed / 95 skipped**, flag apagado ⇒ idéntico; `motor.py` cero diffs. | rama `feat/fabs-inc1`, commits `63f8ef3..bbe2c3b` |
| 2026-08-11 | 1 | Semilla real de goldens desde PROD (snapshot): caja_hoy 704.722.003 · runway abstención · IVA C2-2026 36.204.698,10 (DIAN 10-sep) | `app/cfo/goldens/semilla.py` (`bbe2c3b`) |

## 5. Estado de datos / decisiones abiertas del CEO

- **Alegra:** CERO en esta fase (revisión 2027 si se requiere).
- **Fuera de alcance permanente:** CXC socios, interés presuntivo, devengado/P&L, labores contables (COMPAS/FABS NO son ERP).
- **Fórmulas faltantes** (si las hubiera): se construyen EN COMPAS (aditivas, motor intocable), FABS las consume (D5).
- **Pendientes del CEO:** rotación del token Alegra filtrado en SISMO-V2 (higiene de seguridad); GO al CR-PTS6F (cartera de apertura); merge de `feat/fabs-inc1` a main tras el gate.

## 6. Refinamientos conocidos (para incrementos siguientes)

- **`caja_hoy` — semántica de anclaje (inc2):** hoy corre `caja_diaria` desde el `vigente_desde` de los parámetros vigentes. Como esos parámetros se re-guardan seguido (vigente_desde = fecha reciente) y no hay movimientos cargados en esa ventana, en PROD devolvió la `caja_inicial` cruda (704.722.003) con `ref="sin-movimientos"`, no la caja corrida real. Refinar en inc2: anclar desde el último mes CERRADO (o desde el primer movimiento del mes en curso) para reflejar la caja real a la fecha de corte. La abstención honesta y la evidencia ya funcionan; es un ajuste de fuente, no de contrato.
- **`proximo_pago` lee reloj dentro de módulo "compute-only"** (`app/iva/liquidacion.py`, preexistente, reubicado en el refactor DRY): el reviewer final dictaminó que `dias` (días al vencimiento DIAN) es intrínsecamente relativo al reloj → `today_bogota()` es semánticamente correcto ahí; opcional pasar "hoy" como parámetro para determinismo pleno. NO bloquea.
- **`iva_cuatrimestre` asume periodicidad cuatrimestral** (`app/cfo/calc/iva.py` `_periodo_vigente_idx`, `(month-1)//4`): ignora `data["periodicidad"]` que ya trae. Hoy exposición CERO (RODDOS cuatrimestral, flag apagado, sin consumidor). **MUST-DO al inicio de inc2, ANTES de que el LLM consuma esta cifra:** derivar el índice de `data["periodicidad"]` o fail-closed (abstenerse) si `periodicidad != "cuatrimestral"` — para no publicar jamás una cifra/evidencia equivocada (regla #1).
- **`upsert_golden` es insert-si-ausente, no upsert real** (`app/cfo/datos/repositorios.py`): idempotente por `(concepto, nota)` sin índice único; si cambia un valor con la misma `nota`, re-sembrar no lo actualiza. Aceptable para siembra de una sola vez; revisar cuando Fabián cargue el set 240+60.

---
*Creado 2026-08-10. Este archivo se actualiza al cerrar cada pieza (no al final del incremento).*
