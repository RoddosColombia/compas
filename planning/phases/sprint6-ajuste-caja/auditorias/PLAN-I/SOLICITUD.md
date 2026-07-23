# SOLICITUD DE AUDITORÍA — sprint6-ajuste-caja · I-PLAN: C4 ajuste diario de caja disponible

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-07-23
**Docs contrato:** `docs/COMPAS_NORTE.md`, `.planning/PROJECT.md` (C4 y "Lo ÚNICO que se carga a diario" #2), `docs/modelo/MODELO.md` (hoja Control / Pagos semana), Spec §1.3 (`saldos_banco`), §2.4; CR-S6 (declarado abajo); CLAUDE.md reglas 1, 2, 3, 4, 7, 9, 11.
**Base:** `main` con C1+C3 en prod y la deuda S4-00/S4-06 saldada (tu GO 9.5, merge dea4a16). **Nivel:** PLAN (pre-código).
**Alcance:** SOLO C4 backend (reporte diario de saldos por banco + conciliación al instante). La pantalla frontend va aparte sin gate. C5 (vista categoría×cuenta) y C7 en PLANes aparte.

> Contexto de norte: las DOS únicas entradas diarias del sistema son (1) los
> movimientos del banco y (2) **el valor de la caja disponible** "para ajustar/
> corregir constantemente y que la información siempre cuadre" (PROJECT.md).
> La (1) existe (C2/C3). La (2) NO: `saldos_banco` solo se fija UNA vez al abrir
> el mes (`POST /meses`) y no hay forma de actualizarlo — la conciliación
> (certificada en sprint4-cierre) queda congelada al dato de apertura todo el mes.

## Qué se propone

**1. `PATCH /api/v1/meses/{mes}/saldos`** — reporte/ajuste diario de saldos por banco.
- Body strict: `{"saldos": [{"banco", "saldo" (string, regla 1), "fecha_reporte"}]}`,
  1..N bancos por llamada. **UPSERT sobre `mc.saldos_banco`** por banco: reemplaza
  el `SaldoBanco` del banco (saldo + fecha_reporte) o lo agrega si no estaba
  (p. ej. cuenta nueva a mitad de mes). Los bancos NO incluidos no se tocan.
- Guardas (orden): 401/403 (`caja:reportar`, CR-S6) → 404 mes no existe → **409 mes
  no está `en_ejecucion`** (los saldos de apertura se fijan en `POST /meses`; un mes
  cerrado es inmutable, regla 4) → 422 banco desconocido o `manual` (§1.3, como la
  apertura) → 422 saldo no decimal → guardas de fecha (D2).
- Escritura: **un solo documento** (`mc.save()`), sin transacción multi-doc (regla 8
  no aplica: no hay segundo documento). Auditoría **fail-closed O1 con compensación**
  (estándar B-5 de C1): si el `emit` falla, se restaura la lista `saldos_banco`
  previa (capturada antes de mutar) y se propaga.
- Respuesta: los `saldos_banco` resultantes **+ la conciliación del mes calculada al
  instante** (D4) — el momento "¿cuadra?" que pide el norte.

**2. Conciliación diaria** — sin cambios de código: `GET /meses/{mes}/conciliacion`
(compute-only, certificada) ya calcula `calculado(b) = reportado(b) @ fecha_reporte
+ Σ signo(movimientos posteriores)`. Fue diseñada exactamente para consumir reportes
frescos; C4 solo le da la entrada diaria que le faltaba.

**3. Efecto colateral declarado (positivo) sobre F-14:** la apertura del mes
siguiente deriva `saldo_inicial = Σ saldos_banco` del mes anterior. Con C4 ese
arrastre usa el ÚLTIMO reporte del CEO en vez del dato de apertura (un mes viejo).
El cierre re-ancla a `R_M` después de todos modos (M-2) — C4 no cambia esa lógica,
solo mejora el dato provisional.

**CR-S6 (declarado):** catálogo 36→**37** (+`saldo_banco.reportado`, metadata
`{banco, saldo_anterior→saldo_nuevo, fecha_reporte_anterior→nueva}` — un evento POR
BANCO tocado, no por llamada: rastro forense por cuenta) + capacidad
**`caja:reportar`** = {financiero, admin} (§4.1 por CR; mismo actor de la carga
diaria 8:30). Tests de completitud y guardián actualizados. Nota: el evento
`saldo_inicial.editado` (v1.1) NO se usa aquí — está reservado al override de
`saldo_inicial_caja` vía `ciclo:config` + step-up (incremento futuro); esto es otra
cosa (saldos REPORTADOS por banco, no el ancla del libro).

## Decisiones declaradas (auditar)

- **D1 — representación: upsert sobre `mc.saldos_banco` (último reporte por banco),
  NO colección nueva `saldos_diarios`.** La conciliación y el cierre certificados ya
  leen esa estructura (cero cambios en superficie crítica); la SERIE histórica de
  reportes queda en `audit_log` (append-only, un evento por banco con
  anterior→nuevo). Alternativa descartada: colección snapshot fecha×banco — más
  alcance, obliga a tocar `_conciliar`, y la serie para C7 se decidirá en el PLAN de
  C7 con sus drivers reales. ¿De acuerdo?
- **D2 — guardas de `fecha_reporte`:** formato `YYYY-MM-DD` estricto (regla 2) y
  `mc.mes ≤ fecha_reporte ≤ hoy(Bogotá)` — no se reporta el futuro ni antes del mes
  (un reporte fechado antes del día 1 contaría TODO el mes como "posterior").
  Además **no-retroceso por banco**: `fecha_reporte ≥ la vigente` de ese banco
  (misma fecha = corrección del día, permitida; retroceder → 422 fail-loud, regla
  7 — retrasar la fecha cambiaría en silencio qué movimientos cuentan como
  posteriores). ¿De acuerdo?
- **D3 — solo `en_ejecucion` (409 en otros estados).** El reporte diario es del mes
  OPERANDO. `sugerido/propuesto/definido` son meses futuros en preparación (su saldo
  llega por apertura/arrastre); `cerrado` es regla 4.
- **D4 — la respuesta incluye la conciliación** (compute-only, reusa `_conciliar`
  sin cambios). Acopla la lectura al write, pero ES el propósito de C4 ("que la
  info siempre cuadre" al instante de reportar). Alternativa: respuesta mínima y que
  el frontend llame al GET — dos requests para el flujo diario único. ¿De acuerdo?
- **D5 — un evento de auditoría POR BANCO tocado** (no por llamada): el forense por
  cuenta pide poder seguir la serie de UN banco; una llamada típica trae 1 banco
  (Global66 hoy). Máx 3 eventos/llamada — sin problema de ruido (≠ D3 de C3).
- **D6 — PATCH sin Idempotency-Key:** el upsert es idempotente por naturaleza
  (mismo body → mismo estado final); la convención de Idempotency-Key aplica a POST
  sensibles. El reintento duplicaría eventos de auditoría solo si cambió algo
  (anterior≠nuevo la primera vez; el reintento registra anterior==nuevo — rastro
  veraz, no corrupción). ¿De acuerdo?

## Semántica preservada

Dinero/tiempo intactos: C4 NO toca movimientos, motor §1.4.1, `_conciliar`,
`_caja_libro`, cierre, reapertura ni Vista Control — solo alimenta con dato fresco
la estructura que ya consumen. Decimal end-to-end (string en API, regla 1). Pydantic
strict. Histórico inmutable (D3). Catálogo cerrado: solo CR-S6 (+1 = 37). RBAC por
`require_permission` (regla 9); navbar derivado de capabilities sin cambios de
mecanismo.

## Puntos a auditar con lupa

1. D1 — ¿upsert in-place es suficiente o exiges serie persistida fuera de audit_log?
2. D2 — la ventana `[mc.mes, hoy]` + no-retroceso por banco: ¿cubre los edge cases
   (corrección mismo día, banco nuevo a mitad de mes, reporte del día 1)?
3. O1 — compensación de un solo documento (restaurar lista previa): ¿basta, o ves
   una carrera entre captura del previo y el save que exija releer?
4. CR-S6 — nombre del evento (`saldo_banco.reportado`) y capacidad `caja:reportar`
   {financiero, admin}: ¿o reusar `cargas:gestionar` (mismo actor) y ahorrar la
   capacidad nueva?
5. D4 — conciliación en la respuesta del PATCH: ¿acoplamiento aceptable?

## Evidencia

Sin código aún (PLAN). Base: main verde (CI 7/7 en dea4a16), C1+C3 en prod, deuda
de auditoría en cero (tu certificado I-PR1 sprint4-deuda 9.5). La conciliación por
banco que C4 alimenta es la que certificaste en sprint4-cierre (GO PLAN R 9.4).

## Pregunta al auditor

¿El diseño de C4 (reporte diario upsert sobre `saldos_banco` con guardas de fecha,
conciliación al instante reusando `_conciliar` sin cambios, O1 fail-closed
mono-documento, CR-S6 +1 evento por banco + `caja:reportar`) es correcto para
construir con TDD? En particular D1, D2 y D6.
