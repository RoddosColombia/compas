# SOLICITUD DE AUDITORÍA — sprint4-deuda · I-PR1: cierre de deuda S4-00 + S4-06 (código)

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-07-22
**Objeto:** PR #26 `fix/deuda-s4-transacciones` (gate de CÓDIGO). Son TUS Bajas diferidas, implementadas con tu prescripción exacta — sin plan previo porque el diseño ya lo fijaste tú en los certificados de acotar/aprobar (S4-00) y cierre (S4-06 B-2/B-3).
**Docs contrato:** CLAUDE.md reglas 4, 8; Spec §2.2/§2.4; tus certificados I-PR1 sprint3-acotar-aprobar y sprint4-cierre-conciliacion.
**Base:** `main` con C1+C3 completas. **Alcance:** SOLO la deuda; cero cambios de semántica financiera (0 líneas en motor/conciliación/montos/eventos/permisos).

## Qué hace el PR (+~340/−~180; diff completo en EVIDENCIA.md)

### S4-00 — `acotar_linea` transaccional (tu prescripción: "envolver ln.save + mc.save en with_transaction como ya hacen aprobar_presupuesto y confirmar_cierre")
- Línea + transición de mes en **una transacción multi-doc**; la ventana de inconsistencia (caída entre los dos `save`) desaparece. La compensación O1 (emit falla) también es transaccional, simétrica a la reversión de aprobar.
- Consecuencia de test declarada: mongomock no soporta sesiones → los happy-path de acotar migran a **`test_presupuesto_acotar_realmongo.py`** (patrón ya certificado de aprobar), con un test NUEVO: `test_acotar_abort_datos_rollback_total` — falla la escritura del mes → la línea tampoco queda (el caso exacto que motivó tu Baja). Las guardas (403/409/404/422, que retornan antes de la transacción) permanecen en mongomock.

### S4-06/B-2 — TOCTOU (tu prescripción: "releer mc/siguiente con session= dentro de _cerrar y revalidar estado ahí, abortar si cambió")
- `_cerrar`: relee `mc` y `siguiente` DENTRO de la sesión; si `mc` ya no está `en_ejecucion` o `siguiente` quedó `cerrado` → `CierreError` 409 (aborta la transacción). 
- `_reabrir`: simétrico (mc debe seguir `cerrado`; siguiente no puede haberse cerrado — LIFO), declarado como extensión de tu B-2 (mismo riesgo, mismo patrón).
- 2 tests real-mongo que SIMULAN el proceso concurrente (hook en `_conciliar` que muta el estado por colección cruda entre las guardas y la transacción): `test_toctou_estado_cambiado_aborta_cierre` y `test_toctou_siguiente_cerrado_aborta_cierre` — verifican 409 + cero artefactos (sin ajuste, ancla intacta, sin evento `mes.cerrado`).

### S4-06/B-3 — test de step-up (tu prescripción: "test que fija que POST /reabrir exige step-up")
- `test_reabrir_admin_sin_step_up_403`: admin autenticado SIN MFA reciente → 403 con "Step-up" y el mes intacto. El `require_step_up` del router (que ya existía) queda blindado contra regresión.

## Puntos a auditar con lupa

1. S4-00: el estado previo para la compensación se captura ANTES de mutar; `cambio_mes` se evalúa antes de la transacción y se usa consistentemente en ambas (aplicar y revertir).
2. B-2: el re-read usa `session=` (lectura dentro de la transacción); los objetos `mc`/`siguiente` en memoria solo se escriben si la revalidación pasó. `with_transaction` propaga `CierreError` (no es TransientTransactionError → no reintenta).
3. Cero polizontes: `git diff` no toca motor §1.4.1, `_conciliar`, montos, catálogo (36) ni permisos.
4. Los tests TOCTOU verifican la NO-mutación (sin doble ajuste, sin re-ancla, sin evento).

## Evidencia local (EVIDENCIA.md)

`pytest -q`: **411 passed, 46 skipped** (los 46 = real-mongo → CI del PR #26: acotar transaccional 4, TOCTOU 2, y el resto del set). `ruff check/format`: limpios. Greps: 0. B-3 corre en mongomock: verde local.

## Pregunta al auditor

¿El cierre de S4-00/S4-06 implementa fielmente tus prescripciones (atomicidad del acotar, revalidación en sesión del cierre/reapertura, step-up blindado) sin tocar semántica financiera, para mergear a `main`?
