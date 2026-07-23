# SOLICITUD DE AUDITORÍA — sprint5-pagos-semana · I-PLAN: C9/S5-01 Pagos de la semana

**Para:** Kimi (auditoría RETROACTIVA — Kimi ausente hasta 25-jul; el CEO dio GO de
fase 2026-07-23 para construir, este PLAN se audita al volver) · **Umbral:** ≥ 9.0
· **Fecha:** 2026-07-23
**Docs contrato:** `docs/COMPAS_NORTE.md`, `.planning/PROJECT.md` (C9, S5-01),
`docs/modelo/MODELO.md` (hoja **Pagos semana**: "Pagos de la próxima semana vs Caja
disponible hoy"), Spec §1.5 (`pago_planeado_id` ya existe en Transaccion), §2.4;
CR-S7 (declarado abajo); CLAUDE.md reglas 1, 2, 3, 4, 7, 9, 11.
**Base:** `main` con C1+C3+C4 y deuda S4 saldada. **Nivel:** PLAN (pre-código).
**Alcance ACOTADO (decisión CEO):** SOLO "Pagos de la semana" — registrar pagos
programados + el veredicto "¿alcanza la caja?". **FUERA de alcance** (fases aparte):
la matriz de deudas/cronograma de proveedores (es **C10**), el matching automático
movimiento↔pago, `SnapshotCaja`/job diario y el dashboard Inicio.

> Norte: C4 ya entrega la **caja disponible hoy**. La decisión que sigue es
> **"¿alcanza para los pagos de esta semana, y cómo queda la caja después?"** — la
> hoja *Pagos semana* del Excel. Es predicción/decisión de caja (norte), no registro.

## Qué se propone

**1. Entidad `PagoPlaneado`** (NUEVA, Pydantic strict):
- `concepto` String(300), `acreedor` String(200) — dato OPERATIVO que digita el
  usuario en la app (persistente en Mongo, NO semilla, NO en repo: no es la PII de
  seeds que prohíbe MODELO/Ley 1581).
- `monto` Money (>0), `fecha_programada` 'YYYY-MM-DD', `rubro_id` (categoría de
  egreso que impactará; opcional pero recomendado para calzar con presupuesto),
  `mes_id` (mes al que pertenece), `estado` = `pendiente|pagado|cancelado`,
  `pagado_tx_id` (Transaccion que lo saldó, si estado=pagado), `creado_por`,
  `creado_at`. Índices: `(mes_id, fecha_programada)`, `(estado)`.
- **Solo EGRESO** (un pago es salida de caja); no hay pagos planeados de ingreso
  (los ingresos esperados ya viven en `ingresos_esperados_semana` del MesControl).

**2. CRUD `/api/v1/pagos-planeados`** (`pagos:gestionar`, CR-S7):
- `POST` — crea un pago pendiente; valida `monto>0`, `rubro_id` existe/activo/es
  EGRESO (D1, misma coherencia de tipos que C3), `fecha_programada` ≥ día 1 del mes
  del `mes_id`, mes NO cerrado (regla 4). Emite `pago_planeado.creado`.
- `PATCH /{id}` — editar concepto/acreedor/monto/fecha/rubro mientras `pendiente`;
  un pago `pagado`/`cancelado` es inmutable (409). Emite `pago_planeado.editado`.
- `POST /{id}/cancelar` — baja lógica (estado=cancelado). Emite
  `pago_planeado.cancelado`.
- `POST /{id}/marcar-pagado` — enlaza a una Transaccion EXISTENTE (egreso, mismo
  mes, no cerrado) → estado=pagado + `pagado_tx_id` + set `pago_planeado_id` en la
  tx (transacción multi-doc, regla 8, con saga O1). Emite `pago_planeado.editado`
  {estado: pendiente→pagado}. **El matching AUTOMÁTICO queda fuera** (manual explícito).
- `GET` (`dashboard:leer`) — filtros `mes`/`estado`.
- Auditoría **fail-closed O1** con compensación (estándar C1/B-5).

**3. Vista veredicto — `GET /api/v1/meses/{mes}/pagos-semana`** (`dashboard:leer`,
compute-only, sin estado/evento):
- Ventana: pagos `pendiente` con `fecha_programada ∈ [hoy(Bogotá), hoy+7d]` (D2).
- `caja_hoy` = caja disponible (misma fuente que la Vista Control: `_caja_libro`
  saldo_inicial + Σ signo(tx) excl. 'Ajuste de conciliación' — reusada, sin cambios).
- `total_semana` = Σ montos de esos pagos; `caja_proyectada` = `caja_hoy −
  total_semana`; `veredicto` = `alcanza` si `caja_proyectada ≥ 0` else `no_alcanza`
  (semáforo verde/rojo). Devuelve el detalle de pagos + estos totales.
- **D3:** también un bloque `vencidos` = pendientes con `fecha_programada < hoy`
  (informativo, fail-loud: pagos que debieron hacerse y siguen pendientes).

**CR-S7 (declarado):** catálogo 37→**40** (`pago_planeado.creado`,
`pago_planeado.editado`, `pago_planeado.cancelado`) + capacidad
**`pagos:gestionar`** = {financiero, admin} (§4.1 por CR; simetría con rubros:/
reglas:/caja:). `marcar-pagado` reusa `pago_planeado.editado` (economía B-3: sin
evento extra). Tests de completitud y guardián actualizados.

## Decisiones declaradas (auditar)

- **D1 — coherencia de tipo:** `PagoPlaneado.rubro_id` debe ser un rubro EGRESO
  activo (un pago no calza contra un rubro de ingreso). Igual patrón que C3.
- **D2 — ventana de "la semana":** `[hoy, hoy+7d]` en América/Bogotá (regla 2),
  comparación de strings YYYY-MM-DD. ¿7 días naturales o hasta el próximo lunes?
  Propongo 7 días naturales rodantes (simple, coincide con "próxima semana" del
  Excel). ¿De acuerdo?
- **D3 — vencidos visibles:** los pendientes con fecha pasada se listan aparte
  (fail-loud), no se ocultan ni se suman a la semana. ¿Suficiente, o los quieres
  dentro del total "a pagar ya"?
- **D4 — caja_hoy reusa `_caja_libro`** (la fuente certificada de la Vista Control),
  NO recalcula. Cero cambios en conciliación/cierre/motor. ¿De acuerdo?
- **D5 — marcar-pagado es manual y enlaza una tx existente** (no crea la tx ni la
  concilia). El matching automático (heurística monto/fecha/acreedor) se difiere:
  no es predicción de caja y añade complejidad sin datos reales aún. ¿De acuerdo?
- **D6 — sin `SnapshotCaja`/job ni dashboard Inicio en esta fase** (eran parte del
  S5-01 original; los separo porque el veredicto no los necesita y el snapshot es
  infra de proyección que corresponde a C7). ¿De acuerdo con el recorte?

## Semántica preservada

Dinero/tiempo intactos: `PagoPlaneado` es una intención de pago, NO un movimiento
bancario — no toca `Transaccion`, dedup, motor §1.4.1, `_conciliar`, `_caja_libro`
ni la caja (solo la LEE). `marcar-pagado` solo enlaza (set `pago_planeado_id`), no
altera fecha/valor/banco de la tx (§2.2). Histórico inmutable: mes cerrado no admite
pagos nuevos ni marcado (409). Decimal end-to-end (string en API). Pydantic strict.
Catálogo cerrado: solo CR-S7.

## Puntos a auditar con lupa

1. D1 — coherencia de tipo del rubro (egreso activo) al crear/editar.
2. D4 — reuso EXACTO de `_caja_libro` (misma caja que la Vista Control; una sola
   verdad de "caja disponible").
3. `marcar-pagado` — transacción multi-doc (pago + tx) + saga O1; regla 4 (mes
   cerrado → 409); inmutabilidad de la tx (solo se añade el FK).
4. Ventana D2 y bloque de vencidos D3 (nada se suma dos veces ni se oculta).
5. CR-S7: +3 eventos y capacidad — ¿o exiges un evento propio para marcar-pagado?

## Pregunta al auditor

¿El diseño de C9/S5-01 acotado (PagoPlaneado + CRUD con coherencia de tipo, veredicto
`pagos-semana` reusando `_caja_libro`, marcar-pagado manual multi-doc, CR-S7) es
correcto para construir con TDD? En particular D2, D5 y el recorte D6.
