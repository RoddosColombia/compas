# SOLICITUD DE AUDITORÍA — sprint4-cierre-conciliacion · I-PLAN: cierre de mes + conciliación por banco

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-07-21
**Docs contrato:** Spec §1.3 (MesControl), §1.10 (Configuracion/UMBRAL_DIF_BANCO_CIERRE), §2.2 (multi-doc F-09, mes cerrado inmutable, ajuste día-1 nit-9), §2.4 (autoridad: cierre operativo / confirmar cierre / reabrir); CLAUDE.md reglas 1,2,3,4,5,8,9,11
**Base:** `main` con acotar+aprobar mergeado (GO I-PR1 9.5, merge `885d32e`). **Nivel:** PLAN (pre-código).
**Alcance (decidido por el CEO):** pieza **A+B** de Sprint 4 — cierre + conciliación + **reapertura** (D3 entra). Vista Control (C), tardías (D) y CR-001 (E) son piezas siguientes.

> En Sprint 3 anunciaste que en Sprint 4 auditarías el **% ejecutado, la conciliación por banco y las tardías (F-08)**. Esta pieza cubre la **conciliación por banco** y el **cierre multi-doc**; las tardías vienen en la pieza D (dependen de que el cierre exista).

## Qué se propone

1. **Cierre operativo** — `POST /meses/{mes}/cierre/conciliacion` (RBAC `ciclo:cierre_operativo`, Financiero+Admin). **Compute-only** (sin cambio de estado, sin evento): por banco, saldo **calculado** (`saldo_inicial_caja` + Σ ingresos − Σ egresos del mes, en Decimal) vs **reportado** (`MesControl.saldos_banco`) → **diferencia** por banco y consolidada. Compara |diferencia consolidada| contra `UMBRAL_DIF_BANCO_CIERRE` (Configuracion, §1.10). Devuelve el reporte + `dentro_de_umbral`. Es el checklist previo.

2. **Confirmar cierre** — `POST /meses/{mes}/cierre/confirmar` (RBAC `ciclo:confirmar_cierre`, **solo Admin**, header **Idempotency-Key**). **TRANSACCIÓN MULTI-DOC (regla 8/F-09):**
   - MesControl M `estado → cerrado` (+ `cerrado_por`/`cerrado_at`). Congelar cifras lo impone el estado `cerrado` (`assert_editable` ya rechaza escrituras, regla 4).
   - Crea la **Transaccion 'Ajuste de conciliación'**: rubro de sistema homónimo, **fecha = día-1 de M+1**, `mes_id` = M+1, `valor = |diferencia|`, `tipo_flujo` = ingreso si reportado>calculado (falta plata en libro) / egreso si reportado<calculado, `banco='manual'`, `id_banco='MAN-'+ULID` (regla 5). Así el libro de M+1 abre conciliado con el consolidado reportado (F-14, evita deriva acumulativa).
   - Emite `mes.cerrado`. Auditoría por conexión dedicada → **saga O1** (capturar previo → transacción → emitir; si el emit falla, compensación). Reintento `TransientTransactionError` por `with_transaction`.

3. **Reapertura** — `POST /meses/{mes}/reabrir` (RBAC `ciclo:reabrir`, **solo Admin + step-up MFA** de Sprint 0b). `cerrado → en_ejecucion`, emite `mes.reabierto`. Transacción multi-doc: revierte el **Ajuste de conciliación** que el cierre creó en M+1 (borrado dentro de la transacción) para no dejar un ajuste huérfano; un re-cierre lo recomputa. M+1 debe seguir editable (no cerrado).

4. **Seed:** asegurar `UMBRAL_DIF_BANCO_CIERRE` con valor inicial en la migración idempotente (si falta).

## Decisiones declaradas (auditar con lupa)

1. **D1 — `en_ejecucion` sin evento nuevo:** el catálogo cerrado (regla 11) no tiene evento para `definido→en_ejecucion`, y §2.4 no lista una acción de activación. El cierre acepta mes en `definido` **o** `en_ejecucion`; NO introduzco una transición auditada nueva. La reapertura deja el mes en `en_ejecucion`. ¿De acuerdo, o exiges una activación explícita (con CR para el evento)?
2. **D2 — Orden real:** cerrar M **exige M+1 ya abierto** (flujo contable real: se cierra el mes anterior con el actual activo) → el ajuste aterriza en M+1. Si M+1 no está abierto → error accionable, no se cierra. ¿Aceptable?
3. **D3 — Umbral:** |diferencia| ≤ umbral → se absorbe con el ajuste al confirmar; |diferencia| > umbral → **bloquea** confirmar + alerta (probable error de datos, no deriva contable). ¿Correcto el gate, o el ajuste debe absorber siempre y el umbral solo alertar?
4. **D4 — Reapertura / re-cierre:** al reabrir, se **revierte el ajuste** en M+1 dentro de la transacción; un re-cierre recomputa la diferencia y crea uno nuevo (nunca dos ajustes del mismo cierre). ¿Correcto, o el ajuste debe conservarse y versionarse?
5. **D5 — Signo y `tipo_flujo` del ajuste:** reportado>calculado → ingreso (el banco tiene más de lo que el libro registró); reportado<calculado → egreso. ¿Coincide con tu lectura de F-14?

## Semántica preservada (NO cambia)
- Motor/acotar/aprobar intactos; índice `{vigente:true}` intacto.
- Histórico inmutable (regla 4): `assert_editable` ya rechaza escrituras en `cerrado`; el ajuste se crea en M+1 (editable), nunca en M.
- Dinero Decimal/string; fechas Bogotá día-1; Pydantic strict; dedup `MAN-`+ULID (regla 5) para el ajuste.
- Catálogo de eventos cerrado: solo `mes.cerrado`/`mes.reabierto`/`saldo_inicial.editado` (ya existen). Sin inventar eventos.
- `abrir_mes` (Sprint 3, certificado) sin cambios: sigue derivando `saldo_inicial_caja` del consolidado del predecesor (F-14).

## Puntos a auditar con lupa
1. **Transacción multi-doc del cierre** (M cerrado + ajuste en M+1) atómica, con saga de auditoría en sus 2 puntos de fallo (igual patrón que aprobar) y convergencia por Idempotency-Key.
2. **Ubicación del ajuste:** en M+1 (día-1, mes_id de M+1), NUNCA en M cerrado (no violar regla 4).
3. **Reapertura:** reversión del ajuste dentro de la transacción + step-up MFA + que M+1 siga editable.
4. **Conciliación:** el saldo calculado por banco (Decimal, solo transacciones del mes) y el gate de umbral.
5. **RBAC §2.4:** operativo Financiero/Admin; confirmar solo Admin; reabrir Admin+MFA.

## Evidencia
- Sin código aún (auditoría de PLAN). `main` con Sprint 3 completo: 286 tests verdes + 27 real-mongo en CI; deploy sano.

## Pregunta al auditor
¿El diseño del cierre multi-doc (con el ajuste en M+1), la conciliación con gate de umbral, la saga de auditoría y la reapertura con reversión del ajuste + MFA son correctos para construir con TDD, o hay un riesgo a resolver en el PLAN antes de escribir código? En especial, ¿las decisiones D2 (M+1 debe estar abierto) y D4 (reversión del ajuste al reabrir)?
