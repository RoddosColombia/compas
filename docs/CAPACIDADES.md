# CAPACIDADES.md — registro de capacidades derivado del código

| | |
|---|---|
| **Método** | COMPAS 2.0, Fase 0 (crítico) · deliverable F0-1 |
| **Generado** | 2026-08-27 · spec-miner sobre `backend/app/` y `frontend/src/` |
| **Regla** | Cada veredicto se apoya en **archivos que existen** (módulo, tests, ruta de front, carpeta de gate), NO en lo que digan los planes. Sin evidencia → `pendiente`. |
| **Propósito** | Cierra el **riesgo no técnico** de la Fundacional §7: *«el plan describe como pendiente cosas que ya están en el código»*. Este registro es **vista del código**, no fuente. |

> **Hallazgo principal.** `.planning/PROJECT.md` marcaba **C7, C8, C10 y C11 como «❌ FALTA»**. El código dice lo contrario: **C7** (motor + solvers + valles + escenarios + golden-master), **C8** (preservación durable vía S3 Object Lock — no GridFS), **C10** (obligaciones factura a factura con fecha exacta de pago) y **C11** (IVA cuatrimestral completo) **están implementados y con tests**. La única capacidad realmente incompleta es **C9** (backend listo, sin pantalla). El plan estaba desfasado del código — justo lo que la Fundacional pide cerrar.

---

## Resumen

| Cap | Nombre | Veredicto | Falta para «completo» |
|-----|--------|-----------|------------------------|
| **C1** | Categorías administrables | ✅ implementado | — |
| **C2** | Carga diaria de movimientos (parsers 3 bancos) | ✅ implementado | — |
| **C3** | Auto-clasificación por reglas administrables | ✅ implementado | — |
| **C4** | Ajuste de caja + conciliación por cuenta | ✅ implementado | — |
| **C5** | Control por categoría **y** por cuenta | ✅ implementado | — |
| **C6** | Presupuesto inteligente (sugerido→acotar→aprobar) | ✅ implementado | — |
| **C7** | Proyección de caja + motor de ventas/recaudo | ✅ implementado | (es la base de las historias 2.0 RF-F2..F5) |
| **C8** | Preservación durable del original de cada carga | ✅ implementado | (vía S3 Object Lock; sin GridFS) |
| **C9** | Pagos pendientes / Pagos de la semana | ⚠️ **parcial** | **pantalla frontend** (backend + endpoints + tests OK) |
| **C10** | Fecha exacta de pago a proveedores + cronograma de deudas | ✅ implementado | **carpeta de gate propia** (D2 sin `auditorias/`) |
| **C11** | Seguimiento de IVA (Auteco + cuatrimestral) | ✅ implementado | — |
| — | **CFO / FABS** (agente) | presente, *fuera* de C1–C11 | flag `CFO_ENABLED`; workstream paralelo auditado |

Conteo de tests aproximado (`grep def test_`); los parametrizados expanden en runtime.

---

## Detalle por capacidad

### C1 — Categorías administrables · ✅ implementado
- **Módulo:** `backend/app/rubros/{router,service}.py`, `backend/app/domain/rubro.py` (`Rubro`, enums `RubroGrupo/TipoFlujo/TipoRubro`, `es_sistema`), `domain/rubros_neutros.py`. API `/api/v1/rubros`: `GET`, `POST`, `PATCH /{id}`, `POST /{id}/desactivar` (RBAC `rubros:gestionar` + `verify_origin`).
- **Tests:** `test_domain_rubro.py` (~19), `test_rubros_endpoints.py` (~31), `test_rubros_neutros.py` (~3).
- **Front:** `/categorias` → `pages/CategoriasPage.tsx` (+ test); `lib/rubros.ts`; nav `lib/navegacion.ts`.
- **Gate:** `planning/phases/sprint4-categorias/auditorias/` (PLAN-I, PR1-I).

### C2 — Carga diaria de movimientos · ✅ implementado
- **Módulo:** `backend/app/parsers/bank_parsers.py` (`parse_bancolombia/bbva/global66` + `detectar_banco`), `app/cargas/{router,service,mapper,storage,flujo_deudas}.py`, `domain/{carga,bancos}.py`, `transacciones/service.py` (dedup/anular/dividir). Subida `POST /api/v1/cargas` (valida .xlsx/.xls, rechaza .xlsm, límite 10 MB, dedup, transacción multi-doc).
- **Tests:** `test_bank_parsers.py` (~21), `test_carga.py` (~24), `test_cargas_endpoint.py`, `test_transaccion*.py`, `test_flujo_deudas.py`, + real-mongo.
- **Front:** `/cargas` → `pages/CargasPage.tsx`; `/flujo-diario` → `pages/FlujoDiarioPage.tsx`; `lib/cargas.ts`.
- **Gate:** `planning/phases/sprint1-parsers/auditorias/`, `sprint2-cargas/auditorias/`.

### C3 — Auto-clasificación por reglas · ✅ implementado
- **Módulo:** `backend/app/reglas/{router,service}.py`, `domain/regla_clasificacion.py`. **Se aplica dentro de la carga** (`cargas/service.py` llama `reglas_activas_por_tipo()` + `elegir_regla()` por movimiento; sin match → «Por clasificar», `regla_id=None`). Regla aprendida al reclasificar a mano. API `/api/v1/reglas-clasificacion` (`GET/POST/PATCH/desactivar/aprobar/aplicar-pendientes`).
- **Tests:** `test_domain_regla.py` (~10), `test_reglas_endpoints.py` (~31), `test_transacciones_clasificar.py`, `test_cr_wava*.py`.
- **Front:** `/reglas` → `pages/ReglasPage.tsx`; `lib/reglas.ts`.
- **Gate:** `planning/phases/sprint5-autoclasificacion/auditorias/`.

### C4 — Ajuste de caja + conciliación por cuenta · ✅ implementado
- **Módulo:** `backend/app/caja/{router,service,diaria}.py` (`PATCH /meses/{mes}/saldos`, upsert atómico por banco, evento `saldo_banco.reportado`), `app/cierre/{service,router,transito}.py` (`conciliacion`: `calculado(b)=reportado(b)+Σ posteriores`; genera «Ajuste de conciliación» en M+1). *(El saldo disponible en vivo — `caja/service.saldo_disponible` — reusa esta conciliación.)*
- **Tests:** `test_caja_saldos_guards.py`, `test_caja_saldos_realmongo.py`, `test_cierre_conciliacion.py`, `test_reconciliacion*.py`, `test_saldo_inicial.py`.
- **Front:** `/caja` → `pages/CajaPage.tsx` (+ `components/caja/ReporteCajaCard.tsx`); conciliación también en `/control`.
- **Gate:** `planning/phases/sprint6-ajuste-caja/auditorias/`, `sprint4-cierre-conciliacion/auditorias/`.

### C5 — Control por categoría y por cuenta · ✅ implementado
- **Módulo:** `backend/app/control/{router,service}.py` — `GET /meses/{mes}/control` (por rubro + semáforo) y `GET /meses/{mes}/control/por-cuenta` (matriz rubro×banco, reconciliada con la Vista Control; importa `_caja_libro` de `cierre/service.py`).
- **Tests:** `test_control.py`, `test_control_por_cuenta.py`.
- **Front:** `/control` → `pages/ControlPage.tsx` (selector categoría | cuenta | decisiones); `lib/control.ts`.
- **Gate:** `planning/phases/sprint4-vista-control/auditorias/`.

### C6 — Presupuesto inteligente · ✅ implementado
- **Módulo:** `backend/app/presupuesto/{motor,service,router}.py` — `calcular_sugerido_historico` (fórmula §1.4.1: `prom_3m + tendencia + prom_3m×crec_pct`), `generar_sugerido`, `acotar_linea` (saga atómica, `sugerido→propuesto`), `aprobar_presupuesto` (transacción multi-doc, del mes siguiente). Máquina de estados `sugerido/propuesto/ejecución/cerrado`.
- **Tests:** `test_motor_sugerido.py`, `test_presupuesto_generar.py`, `test_presupuesto_acotar_aprobar.py`, + real-mongo.
- **Front:** `/meses/:mes/presupuesto` → `pages/PresupuestoMesPage.tsx`; `lib/presupuesto.ts`.
- **Gate:** `planning/phases/sprint3-motor/auditorias/`, `sprint3-acotar-aprobar/auditorias/`.

### C7 — Proyección de caja + motor · ✅ implementado *(cimiento de las historias 2.0)*
- **Módulo:** `backend/app/proyeccion/` — `motor.py` (`proyectar()`, ventas/colocación, recaudo por cohortes, cartera activa/añada, presets de escenario mora/recuperación/default, `caja_minima` = umbral), `solvers.py` (`techo_gasto`, `goal_seek`, `punto_de_quiebre`), `solver_unidades.py`, `valles.py`, `impactos.py`, `kpis.py`, `service.py`, `ejecucion/` (anclaje). API `/proyeccion`: `GET ""`, `POST /preview|/impactos|/resolver|/simular-plazo`, `GET /valles|/operacion|/sensibilidad|/comparar`.
- **Tests:** **`test_golden_master.py` + `golden/golden_simular.json` (paridad 176 meses al peso)**, `test_proyeccion_motor.py`, `test_proyeccion_preview.py`, `test_proyeccion_sensibilidad.py`, `test_proyeccion_endpoints.py`.
- **Front:** `/proyeccion` → `pages/ProyeccionPage.tsx`; `/escenarios` → `pages/ScenariosPage.tsx`; `components/charts/` (CashCurve, ScenariosChart, ComposicionCaja); `lib/proyeccion.ts`.
- **Gate:** `planning/phases/{sprint3-motor,cockpit-proyeccion,e1-anclaje-ejecucion}/auditorias/`.
- **Nota 2.0:** las historias RF-F2..F5 son **capas** sobre este motor. El **candado** (F0-2 / `docs/CANDADO_MOTOR.md`) protege su paridad.

### C8 — Preservación durable del original · ✅ implementado *(S3 Object Lock, no GridFS)*
- **Módulo:** `backend/app/cargas/storage.py` — original en `s3://{bucket}/originales/{hash}{ext}` en bucket **Object Lock COMPLIANCE**; `subir_original(...)` corre **antes** de cualquier insert; sin `S3_BUCKET` (prod) ni `dir_originales` (dev) → rechaza (fail-closed). **`grep gridfs` = 0 hits.**
- **Tests:** `test_cargas_storage.py`, `test_carga.py`.
- **Front:** n/a (concern de backend; la UI es la subida en `/cargas`).
- **Gate:** `planning/phases/sprint2-cargas/auditorias/`.

### C9 — Pagos pendientes / Pagos de la semana · ⚠️ parcial
- **Módulo:** `backend/app/pagos/{router,service}.py` (`GET /meses/{mes}/pagos-semana` veredicto D4 reusando `_caja_libro`; CRUD `pagos-planeados`, `marcar-pagado` multi-doc), `domain/pago_planeado.py`. **Backend completo.**
- **Tests:** `test_pagos_semana.py`, `test_pagos_marcar_realmongo.py`.
- **Front:** **ninguna** — no hay ruta `/pagos` ni componente que consuma los endpoints. **← lo que falta.**
- **Gate:** `planning/phases/sprint5-pagos-semana/auditorias/` (PLAN-I, PR1-I).

### C10 — Fecha exacta de pago a proveedores + cronograma de deudas · ✅ implementado
- **Módulo:** `backend/app/obligaciones/` — `calculadora.py` (`pago_factura`: mes exacto de pago = `fecha + plazo`, interés solo sobre exceso; `calendario_cuotas`), `service.py`/`router.py` (CRUD `Obligacion`+`FacturaObligacion`, `POST .../pagar`), `reconciliacion.py` (D2 §4: neteo anti-doble-conteo contra el Auteco paramétrico). Import de la hoja 'Flujo de pagos deudas' en `cargas/flujo_deudas.py`. `domain/obligacion.py`.
- **Tests:** `test_obligaciones.py`, `test_calculadora.py` (candado de paridad con el motor), `test_d2_aceptacion.py`, `test_reconciliacion.py`, `test_flujo_deudas.py`.
- **Front:** `/obligaciones` → `pages/ObligacionesPage.tsx`.
- **Gate:** ⚠️ **sin carpeta `auditorias/` propia** (D2 vive en `planning/phases/motor-fidelidad-caja/PLAN.md`, sin gate; `sprint4-deuda/auditorias/` audita otra cosa). *Candidato a gate Kimi retroactivo.*

### C11 — Seguimiento de IVA · ✅ implementado
- **Módulo:** `backend/app/iva/liquidacion.py` (`liquidar` con arrastre de saldo a favor; `Periodicidad` default **cuatrimestral**, bimestral opcional; `neto = max(0, saldo − saldo_favor_previo)`; `programar_egresos_iva`/`plan_fondo_provision` con `CALENDARIO_DIAN`), `iva/proyectado.py` (SUP-3), `app/facturas/` (`/facturas`: `GET /liquidacion`, `POST /cargar` [PDF DIAN], `POST /cargar-excel` [portal DIAN], `POST /iva-generado`, `PATCH /deducibilidad`; `extraccion.py`, `excel_dian.py`), `domain/factura.py`, `CALENDARIO_DIAN` en `domain/configuracion.py`.
- **Tests:** `test_iva_liquidacion.py`, `test_facturas*.py`, `test_extraccion_dian.py`, `test_sup3_iva_proyectado.py`, `test_fixk_auteco.py`.
- **Front:** `/iva` → `pages/IvaPage.tsx`; `lib/iva.ts`.
- **Gate:** `planning/phases/iva-c11/auditorias/PR1-I`, `iva-planes-ago26/auditorias/PR1-I`.

### CFO / FABS — agente (fuera de C1–C11, presente)
- **Módulo:** `backend/app/cfo/` — `router.py` (`POST /api/v1/cfo`, permiso `cfo:consultar`, montado solo si `CFO_ENABLED`), `agente/` (loop con tools), `calc/` (caja, iva, runway, escenario, evidencia — capa de cálculo pura), `telegram/` (webhook/bot), `datos/`, `goldens/`.
- **Tests:** `backend/tests/cfo/*` (calc, config, escenario_golden, goldens_*, aislamiento, agente/, telegram/).
- **Gate:** `planning/phases/{fabs,fabs-inc1,fabs-inc2}/auditorias/`.
- **Nota:** workstream **paralelo** al plan 2.0; consume las capacidades como lector. No se toca desde Fase 0.

---

## Deltas plan ↔ código (para actualizar `.planning/PROJECT.md`)

| Cap | PROJECT.md decía | Código dice | Acción |
|-----|------------------|-------------|--------|
| C7 | ❌ FALTA (el valor final) | ✅ motor + solvers + valles + golden-master | corregir a ✅ (con historias 2.0 encima) |
| C8 | ⚠️ por decidir GridFS vs S3 | ✅ S3 Object Lock (decidido y en código) | corregir a ✅ |
| C9 | ⚠️ backend ✅, falta pantalla | ⚠️ igual | confirmar: falta **solo** la pantalla |
| C10 | ❌ FALTA | ✅ implementado (sin gate propio) | corregir a ✅ + abrir gate Kimi retroactivo |
| C11 | ❌ FALTA | ✅ implementado y con gate | corregir a ✅ |

*Este documento se regenera corriendo spec-miner; no se edita a mano salvo estas notas de delta.*
