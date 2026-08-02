# ROADMAP DE DESARROLLO COMPAS — v2 consolidado

**Fecha:** 2026-08-02 · **Arquitecto:** Kimi · **Desarrollador:** Claude Code
**Reemplaza:** plan maestro etapa48 Parte II (queda integrado aquí con todo lo decidido desde entonces).

> **Referencia única del programa a partir de hoy.**

**Regla de oro:** gates Kimi ≥9 pre-merge en todo PR; waiver formalmente abolido (urgencias solo con
waiver escrito + retro ≤7 días); TDD rojo→verde siempre; `motor.py` cero diffs; golden sin regenerar.

## §0 — Estado al día (snapshot)

- **FIX-A al 80%** en rama `fix/a-nucleo-dinero`: A-1 (guard es_sistema P0), A-3 (no-finitos), A-2
  (MANUAL fuera de conciliación + `manual_neto`/`aviso_manual`), A-4 saga O1 + replay determinista —
  verdes, disclosures limpios. Restan: **A-4 parte 2** (marca huérfana) y **A-6** (TOCTOU
  presupuesto/saldos/apertura).
- **Julio 2026 SIN cerrar aún.** Archivo de carga listo y verificado contra el parser real
  (`Global66_MovimientosCuentaCOP_2026-07.xlsx`, 565 movimientos, cuadre exacto vs Control: egresos
  $372.200.786,62; banco ≈ $665.715.578; Wava tránsito **$37.280.415 = $Y de la NOTA**).
- Bloqueo de la carga resuelto por decisión CEO: nada de puente efímero — se construye **PR-S3**
  (preservación durable S3/Object Lock), exigencia del propio NORTE.

## §1 — Secuencia maestra (orden, estado, gate)

| # | Ítem | Estado | Contenido/decisión | Gate |
|---|---|---|---|---|
| 1 | **PR-S3 preservación durable** | SIGUIENTE (½ día) | `cargas/storage.py` (boto3, cliente inyectable), cableado en `procesar_carga` (S3 si `s3_bucket` → `archivo_s3_key`; dir solo dev; rechazo M-04 si ninguna), boto3 pineado, tests con stub (sube original, fail-closed si put_object falla, M-04 intacto, dedup intacto, dev-dir OK). Infra CEO: bucket `compas-archivo` CON Object Lock (irreversible), retención COMPLIANCE 5 años, IAM mínimo, envs en Render. | Kimi |
| 2 | **Cierre de julio (operación CEO)** | tras PR-S3 + envs | Subir archivo en /cargas (esperado: 565 total · ~86 creadas / ~479 duplicadas · 0 errores) → reportar saldo Global66 al 31-jul (≈665.715.578) en /caja → "Verificar conciliación" en /mes → números a Kimi antes de confirmar → cerrar julio → abrir agosto (saldo derivado) → NOTA Wava con $37.280.415. | Kimi (checkpoint de números) |
| 3 | **FIX-A cierre (A-4 parte 2 + A-6) → PR → merge** | en curso, 80% | A-4.2: `_HUERFANA_MIN=5`, adquisición atómica `update_one({response_status:None, created_at<now−5min} → -1)`, re-ejecución convergente, 3 routers. A-6: re-read dentro de `with_transaction` en acotar/aprobar; `$push` posicional del ajuste; `reportar_saldos` con estado+no-retroceso vía `$elemMatch` en el mismo elemento; dedup banco en apertura. Candados de carrera `@requires_real_mongo` → CI `backend-real-mongo` verde obligatorio. | Kimi |
| 4 | **E1 anclaje proyección** | desarrollo paralelo YA | Spec v1.3 + adiciones Kimi; **merge solo después de FIX-A** (Acta §2.1); exclusión de rubros neutros **por rubro_id** (Ajuste + futuro Tránsito Wava); PASO 0 verifica cero txs a rubros de sistema. | Kimi |
| 5 | **Wava tránsito (Fase 2)** | tras gate E1 | CR-WAVA Opción B + P-1..P-5: exclusión recaudo **por rubro_id** en `ingreso_real`; body íntegro al `request_hash`; reversa en O1/reapertura + heredado derivado; remanente clampeado 0 con roll-forward + aviso; regla C3 con prioridad ganadora o manual. Lista blanca del guard ya incluye el rubro. Test de la trampa + 8 de Kimi. | Kimi |
| 6 | **FIX-B ingesta bancaria** | tras FIX-A | Tardías D-FIX-2 (`tardia=true` + evento) + huella Global66 con signo (reversas cross-archivo) + celda "0" + `patron_normalizado` stale + guard por fila + 500→422 + año heurístico + `regla_id=None` en reclasificación + `proponer_regla` prevalidado + F-02 atómico. | Kimi |
| 7 | **FIX-C facturas/IVA + waiver** | tras FIX-B | Dedup con filtro `activo` + migración de índices parciales `{activo:true}` con reporte de colisiones y foto antes/después (o no se crea) + confirmar `cufe_unico`; signos ≥0; compuerta doble generado (VENTAS- vs emitidas); CUFE 96 hex; fondo sin residuo; deducible-en-venta 422; iva-generado con rango; pagos tx única; loantape todo-o-nada + datetime Excel; mix Σ∈(0,1] con aviso ≠1; parámetros con bounds + `vigente_desde<=hoy`; obligaciones (422 fecha, valor>0, no inactiva, `mes_pago` fecha real); sensibilidad cache con hash cartera/IVA; unicidad real metas/escenarios; `mes_inicio/fin` con rango. | Kimi |
| 8 | **FIX-D frontend + QA** | tras FIX-C | Invalidaciones `["mes"]` en acotar/aprobar/tx/extracto; `queryClient.clear()` en logout/login; `hoyLocal()` compartido; RBAC-UI en /iva; validación input saldo; backlog QA 8/9/10/12. | ligero |
| 9 | **FIX-E auth/infra** | tras FIX-D | `app_env` default production; POST /auth/stepup; eventos `user.mfa_activado`/`user.mfa_reset` (catálogo 59→61 — va con CR en el registro único); throttle mfa/setup; trust IP tras proxy allowlist; índices auth en readiness; password max 72; version fuera de /health. | Kimi |
| 10 | **Batch UI** | tras FIX-E | D2 §7 página Auteco con D-FIX-3 (`pagada_desde: roddos\|tercero` — baja deuda, no caja) + /iva piezas 6–7 (bloque atención, cablear onRevisar + confirmación, anular por fila) + QA ítem 11. | ligero |
| 11 | **Foto PROD read-only (D-OPS-2)** | cuando CEO autorice | Cierra retro de ops de datos; verifica cierre julio real, compuerta, índices, cero txs a rubros de sistema. | Kimi |
| 12 | **Compuerta IVA ON** | tras FIX-A/B/C mergeados | O-1 desbloqueada por absorción (retro de código hecha en la auditoría etapa48) + foto residual de datos; test A14-invertido como regresión. | CEO (dato) + Kimi |
| 13 | **Registro único CR (M-3)** | Kimi, esta semana | `docs/COMPAS_REGISTRO_CR.md`: numeración única, absorción de las dos series + CR huérfanos (S7/COCK/Fidelidad/SISMO), reconciliación del conteo (59→61 tras FIX-E), errata docstrings (`audit/service.py:41`, header `events.py`), corrección CLAUDE.md "repo privado" (falso hoy). | Kimi (propio) |
| 14 | **E2.1 NC/ND/documento soporte** | cuando CEO active | Radar ya rechaza con motivo; lleva el fix CUFE de FIX-C. | Kimi |
| 15 | **Vigencia F4/D3/F6/F7 plan maestro** | Kimi, esta semana | Dictamen contra lo construido: qué sigue vigente, qué ya está, qué se retira. | Kimi (propio) |
| 16 | **G1 go-live (fin de construcción)** | al final | `autoDeploy:false` + tag `v*` + required reviewer + prueba adversarial; privatizar repo + rotar secretos (D-OPS-1 refinada); cobertura con `--cov-fail-under` (línea base tras FIX); CRR del bucket S3; cabeceras re-verificadas con Cloudflare/dominio. | CEO + Kimi |

## §2 — Decisiones vigentes (registradas)

- **D-FIX-1:** no hay caja física; tx manual = movimiento bancario omitido (línea `manual_neto`
  informativa; el ajuste nunca la toca).
- **D-FIX-2:** extracto tardío a mes cerrado entra como `tardia=true` + evento.
- **D-FIX-3:** pagos de tercero a Auteco ($28,5 M) bajan deuda, no caja (D2 §7).
- **D-OPS-1 (refinada):** repo público durante la construcción; privatizar + rotar todo al cerrar
  (condición G1); regla dura: cero secretos nuevos en el repo.
- **D-OPS-2:** foto PROD más adelante (retro de datos queda abierta; no bloquea compuerta).
- **Regla de merge:** E1 desarrolla en paralelo; merge solo tras FIX-A.
- **Contra-revisión institucionalizada:** todo gate Kimi admite contra-revisión de Claude Code antes de
  quedar final; autoridad del gate y waiver = CEO.
- **Exclusión por rubro_id** (Wava y E1), nunca por grupo; lista blanca del guard `es_sistema` =
  {Recaudo de cartera, Por clasificar, Tránsito Wava mes anterior} + deny-by-default.

## §3 — Régimen permanente

- **Candados de regresión:** los P0/P1 de la auditoría etapa48 → 14 candados permanentes en CI (los 7
  previos + 7 nuevos del paquete FIX).
- **Barrido de bugs** como el de etapa48 mensual (no solo por PR).
- **Cobertura** con umbral mínimo en CI tras aterrizar los FIX (línea base medida).
- **Toda migración:** fechada, idempotente, reversible, foto antes/después, reporte de colisiones, URI
  solo por env.
