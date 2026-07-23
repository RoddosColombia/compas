# SOLICITUD DE AUDITORÍA — sprint5-pagos-semana · I-PR1: C9 Pagos de la semana (código)

**Para:** Kimi (auditoría RETROACTIVA — construido bajo GO del CEO 2026-07-23 con Kimi
ausente hasta 25-jul) · **Umbral:** ≥ 9.0 · **Fecha:** 2026-07-23
**Objeto:** PR `feat/c9-pagos-semana` (gate de CÓDIGO). Construido con TDD tras el GO
PLAN-I; incorpora las decisiones D1-D6 del PLAN.
**Docs contrato:** CLAUDE.md reglas 1, 2, 3, 4, 8, 9, 11; Spec §1.5; PLAN-I
sprint5-pagos-semana. **Base:** `main` con C1+C3+C4.
**Alcance:** SOLO "Pagos de la semana" (PagoPlaneado + CRUD + veredicto). Matriz de
deudas (C10), matching automático, SnapshotCaja/job y dashboard quedan FUERA (D6).

## Qué hace el PR

**`PagoPlaneado`** (entidad nueva, strict): concepto, acreedor, monto (>0),
fecha_programada, rubro_id (EGRESO activo, D1), mes_id, estado
(pendiente/pagado/cancelado), pagado_tx_id. DOMAIN_DOCUMENTS 8→9.

**API** (`/meses/{mes}/pagos-planeados` + `/pagos-planeados/{id}`):
- `POST` crear (`pagos:gestionar`): valida mes no cerrado (regla 4), rubro EGRESO
  activo (D1), fecha ≥ día 1. Emite `pago_planeado.creado`. O1 fail-closed.
- `PATCH /{id}` editar: solo `pendiente` (409 si no); revalida rubro (D1). O1.
- `POST /{id}/cancelar`: baja lógica. `pago_planeado.cancelado`. O1.
- `POST /{id}/marcar-pagado` (D5): enlaza a una Transaccion existente (egreso, mismo
  mes, no cerrado) en **TRANSACCIÓN MULTI-DOC (regla 8)** — pago→pagado+pagado_tx_id
  y tx.pago_planeado_id — con revalidación TOCTOU en sesión y saga O1. Reusa
  `pago_planeado.editado` {estado: pendiente→pagado} (economía, sin evento extra).
- `GET /meses/{mes}/pagos-planeados` + `GET /meses/{mes}/pagos-semana` (`dashboard:leer`).

**Veredicto `GET /meses/{mes}/pagos-semana`** (D4, compute-only): `caja_hoy` reusa
`_caja_libro` (la MISMA caja de la Vista Control), `total_semana` = Σ pagos
pendientes en `[hoy, hoy+7d]` (D2 rodante), `caja_proyectada = caja_hoy −
total_semana`, `veredicto` alcanza/no_alcanza. `vencidos` (fecha < hoy) aparte (D3).

**CR-S7:** catálogo 37→**40** (`pago_planeado.creado/editado/cancelado`) + capacidad
`pagos:gestionar` = {financiero, admin}.

## Puntos a auditar con lupa

1. D1 — coherencia de tipo del rubro (egreso activo) al crear y editar.
2. D4 — `pagos-semana` reusa `_caja_libro` sin recalcular (una sola verdad de caja);
   cero cambios en `_conciliar`/cierre/motor.
3. `marcar-pagado` — transacción multi-doc (pago + tx) con revalidación en sesión
   (TOCTOU) + saga O1; regla 4 (mes cerrado → 409); la tx solo gana el FK (§2.2).
4. D2 — ventana `[hoy, hoy+7d]` (strings YYYY-MM-DD); D3 vencidos aparte (nada se
   suma dos veces).
5. Regla 1: monto string en API (strict rechaza number); Decimal end-to-end.

## Evidencia local (EVIDENCIA.md)

Diff real de dominio/servicio/router + deltas de catálogo/permisos/DOMAIN_DOCUMENTS,
y los 2 archivos de test. `pytest -q` verde (guardas+CRUD+veredicto mongomock; los
real-mongo de marcar-pagado corren en el CI del PR). `ruff check`/`format` limpios.
Greps del protocolo: 0.

## Pregunta al auditor

¿La implementación de C9/S5-01 (PagoPlaneado + CRUD con D1, veredicto reusando
`_caja_libro`, marcar-pagado multi-doc con O1, CR-S7) implementa fielmente el PLAN
sin tocar semántica financiera, para mergear a `main`?
