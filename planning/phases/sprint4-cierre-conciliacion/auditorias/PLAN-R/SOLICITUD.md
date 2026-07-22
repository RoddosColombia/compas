# SOLICITUD DE AUDITORÍA — sprint4-cierre-conciliacion · R-PLAN: cierre + conciliación (ronda R)

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-07-21
**Docs contrato:** Spec §1.3, §1.10, §2.2 (F-09, inmutabilidad §2.2.2, nit-9), §2.4; CLAUDE.md reglas 1,2,3,4,5,8,9,11
**Antecedente:** I-PLAN NO-GO 8.5. Esta ronda incorpora **M-1..M-4** (los 4 hallazgos), sin re-diseño. **Nivel:** PLAN (pre-código).

> "El plan está a una pasada de precisión aritmética del verde." Esta ronda cierra la matemática (M-2), corrige el ciclo de estados (M-1), el ancla por banco (M-3) y la reversión inmutable (M-4).

## Cambios de esta ronda (resolución de hallazgos)

### M-1 — La aprobación deja el mes en `en_ejecucion`
`aprobar_presupuesto` (Sprint 3) pasa a fijar `estado = en_ejecucion` (no `definido`), conservando `definido_por`/`definido_at` + evento `presupuesto.definido` como registro de la aprobación (US-02: "el mes pasa a en_ejecucion"). **Resuelve D1 sin evento nuevo.** El valor `definido` del enum queda como estado transitorio interno (nunca en reposo). Impacto: se actualiza el test de Sprint 3 (aprobación → `en_ejecucion`). El cierre exige mes en `en_ejecucion` (camino forward normal); la reapertura devuelve a `en_ejecucion`.

### M-2 — Aritmética del ancla (F-14) cerrada + regla anti-doble-conteo
Dentro de la **transacción multi-doc del cierre de M**:
1. **Re-anclar** `saldo_inicial_caja(M+1) := R_M` (consolidado reportado de M al cierre), guardando el valor previo en `M.cierre_info.ancla_anterior_siguiente` para la reversión (M-4). Sancionado por §1.3 ("al cerrar… se fija = saldo bancario consolidado reportado").
2. Crear la **Transaccion 'Ajuste de conciliación'**: `valor = |R_M − C_M|`, `tipo_flujo` = ingreso si `R_M > C_M` (el banco tiene más que el libro) / egreso si `R_M < C_M`; fecha = día-1 de M+1, `mes_id` = M+1, rubro de sistema, `banco='manual'`, `id_banco='MAN-'+ULID` (regla 5), metadata `{origen:'cierre', mes_cerrado: M, diferencia}`.
3. **Regla anti-doble-conteo (declarada):** la caja **disponible** de un mes se computa como `saldo_inicial_caja` (ya anclado al reportado) `+ Σ ingresos − Σ egresos` **EXCLUYENDO las transacciones del rubro de sistema 'Ajuste de conciliación'**. El ajuste vive en el **ledger acumulado** (reconciliación libro↔banco, auditable en su rubro) pero NO en la disponible operativa (que ya arranca del ancla reportada) → nunca se cuenta dos veces.

**Prueba numérica (irá como test):**
- M abre con `saldo_inicial_M = 100`. En M: ingresos 50, egresos 30 → `C_M = 100 + 50 − 30 = 120` (calculado del libro).
- Banco al cierre de M: `R_M = 118` (deriva −2, p.ej. una comisión no capturada). M+1 se había abierto provisional con `R_open = 119`.
- Cierre de M: re-ancla `saldo_inicial(M+1) := 118` (previo 119 guardado). Ajuste = `|118 − 120| = 2`, **egreso** (libro sobreestimó), fecha día-1 M+1.
- **Ledger acumulado:** `100 + (50 − 30) + (−2) = 118 = R_M` ✓ (el ajuste reconcilia el libro con el banco en la frontera M/M+1).
- **Disponible M+1:** arranca en `118 = R_M` (el ajuste NO entra) ✓ — sin doble conteo.

### M-3 — Conciliación por banco con ancla por banco + "sin dato"
Por banco b, saldo **calculado** = `saldo_reportado(b) @ fecha_reporte(b) + Σ movimientos de b con fecha > fecha_reporte(b)` (dentro del mes). El **consolidado** `R_M = Σ_b` de esos saldos por banco. Banco **sin** `saldos_banco` reportado → **"sin dato"** (regla 7): se excluye del consolidado y se reporta como advertencia; **jamás** se compara contra 0. La conciliación devuelve por banco {reportado, calculado, diferencia | "sin dato"} + consolidada + `dentro_de_umbral`.

### M-4 — Reapertura por CONTRA-ASIENTO (inmutabilidad §2.2.2)
La reapertura NO borra el ajuste. Dentro de la transacción de reapertura: crea un **contra-asiento** (mismo |valor|, `tipo_flujo` invertido, fecha día-1 M+1, rubro de sistema, metadata `{revierte: id_ajuste_original}`) + **restaura** `saldo_inicial_caja(M+1) := M.cierre_info.ancla_anterior_siguiente` + `estado M → en_ejecucion` + `mes.reabierto`. Un re-cierre recomputa y crea un ajuste nuevo (los contra-asientos dejan el neto del rubro en 0 para ese ciclo). Requiere M+1 editable (no cerrado) y step-up MFA (Admin).

## Lo demás del plan (sin cambio respecto a I)
Cierre operativo (compute-only, `ciclo:cierre_operativo`) · Confirmar cierre (multi-doc, `ciclo:confirmar_cierre` solo Admin, Idempotency-Key, saga O1 para `mes.cerrado`) · reintento `TransientTransactionError` · umbral ≤ absorbe / > bloquea (D3) · M+1 debe estar abierto (D2) · seed `UMBRAL_DIF_BANCO_CIERRE`. Histórico inmutable (regla 4): el ajuste y el contra-asiento se crean en M+1 (editable), nunca en M.

## Nuevo campo de modelo
`MesControl.cierre_info: {ancla_anterior_siguiente: Money, diferencia: Money, ajuste_tx_id: str} | None` — set en el cierre, leído en la reapertura. Pydantic strict.

## Puntos a auditar con lupa
1. **Regla anti-doble-conteo (M-2):** ¿el ajuste EXCLUIDO de la disponible pero presente en el ledger acumulado es la lectura correcta de §1.3 + nit-9? La prueba numérica cuadra a 118 por ambas vías.
2. **Re-anclaje dentro de la transacción del cierre** (M+1 saldo_inicial := R_M) + guardado del previo para la reversión.
3. **Contra-asiento (M-4)** vs delete — inmutabilidad respetada.
4. **Ancla por banco + "sin dato" (M-3).**
5. **M-1:** aprobación → en_ejecucion sin evento nuevo; test de Sprint 3 actualizado.

## Evidencia
- Sin código aún (PLAN ronda R). `main` con Sprint 3 completo, CI verde.

## Pregunta al auditor
¿La aritmética del ancla (M-2, con la regla anti-doble-conteo y el ejemplo que cuadra a 118), el ancla por banco (M-3), el contra-asiento en reapertura (M-4) y la aprobación→en_ejecucion (M-1) están correctos para construir con TDD?
