# RESPUESTA KIMI — sprint6-ajuste-caja · I-PLAN: C4 ajuste diario de caja

**Veredicto: APROBADO — 9.3 / 10. GO para construir con TDD.** · Fecha: 2026-07-23

---

COMPAS — Auditoría I-PLAN Sprint 6: C4 Ajuste diario de caja disponible
Auditor: Kimi (auditor técnico senior independiente) · Fecha: 2026-07-23
Objeto: SOLICITUD(27).md + PAQUETE(27).pdf — sprint6-ajuste-caja · I-PLAN C4 (PLAN, pre-código)
Base: main con C1+C3 en prod + deuda S4 saldada (I-PR1 GO 9.5, merge dea4a16). Contrato: COMPAS_NORTE, PROJECT (C4), MODELO (Control/Pagos semana), Spec §1.3 (saldos_banco), §2.4, CR-S6 declarado. Umbral ≥ 9.0.

Veredicto: APROBADO — 9.3 / 10. GO para construir con TDD.

La pieza cierra el hueco real que el norte exige ("las DOS únicas entradas diarias": movimientos + valor de la caja disponible) y lo hace con cero cambios en la superficie crítica certificada — alimenta la estructura que la conciliación y el cierre ya consumen. Las 6 decisiones declaradas son correctas. 1 Baja (B-1): el upsert read-modify-write tiene la misma clase de carrera que el TOCTOU ya cerrado; hay una forma atómica más elegante.

## 1. Decisiones (D1/D2/D6 eran la pregunta explícita)
- **D1** upsert in-place, NO colección nueva: DE ACUERDO ✔. Serie histórica en audit_log basta. Exigencia verificable: la metadata del evento DEBE traer valores y fechas, anterior Y nuevo.
- **D2** ventana [mc.mes, hoy] + no-retroceso por banco: DE ACUERDO, cubre edge cases ✔ (corrección mismo día, banco nuevo a mitad de mes, día 1, fecha heredada < mc.mes en el dato de apertura, fecha futura → 422).
- **D6** PATCH sin Idempotency-Key: DE ACUERDO ✔.

## 2. Resto
- **D3** solo en_ejecucion → 409 ✔ (test parametrizado sugerido/propuesto/cerrado exigido).
- **D4** conciliación en la respuesta ✔ (idéntica en forma al GET, misma función = misma verdad).
- **D5** un evento por banco ✔; nombre `saldo_banco.reportado` conforme.
- **CR-S6** capacidad nueva `caja:reportar` (no reusar cargas:gestionar): granularidad por dominio ✔. `saldo_inicial.editado` NO aplica aquí ✔.
- Efecto F-14 positivo ✔ (arrastre usa último reporte fresco; el cierre re-ancla a R_M igual).
- Guardas/orden 401/403→404→409→422(banco)→422(saldo)→D2 ✔. Regla 1 + strict ✔.

## 3. B-1 (Baja — carrera del upsert)
Read-modify-write sobre documento compartido: dos PATCH concurrentes (bancos distintos) → el segundo pisa al primero (lost update). Baja (no Media) porque es fail-visible (la respuesta muestra los saldos resultantes) y corregible. **Exijo control, recomendación en orden:**
1. **(preferida) Update atómico posicional por banco** — sin transacción ni re-lectura:
   - banco existente → `update_one({mes, "saldos_banco.banco": b}, {$set: {"saldos_banco.$": nuevo}})`
   - banco nuevo → `$push` con filtro `{"saldos_banco.banco": {$ne: b}}` (si matchea 0 → ya existe → reintentar posicional). Ambos atómicos a nivel documento.
   - La compensación O1 pasa a ser POR BANCO (restaurar el SaldoBanco previo posicional / `$pull` del agregado) en vez de restaurar la lista entera.
2. Alternativa: patrón S4-06 (re-leer + revalidar dentro de transacción) — válido pero más pesado para un solo documento.
- **Test exigido** (patrón TOCTOU de S4-06): dos PATCH concurrentes sobre bancos distintos → ambos saldos presentes al final.

## 4. Tests que el gate de código (I-PR1) esperará
- Upsert: reemplaza saldo+fecha del banco; agrega banco nuevo; no incluidos intactos.
- Guardas: 404 · 409 parametrizado (sugerido/propuesto/cerrado) · 422 banco desconocido · 422 manual · 422 saldo no decimal.
- D2: fecha < día 1 → 422 · fecha futura → 422 · día 1 OK · corrección mismo día OK · retroceso → 422 · banco nuevo con fecha en ventana OK.
- D4: la respuesta trae la conciliación actualizada idéntica al GET.
- Auditoría: un evento por banco con metadata {banco, saldo anterior→nuevo, fecha anterior→nueva}; 2 bancos → 2 eventos; O1 emit caído → restauración + propaga.
- B-1: concurrencia de dos PATCH (estilo S4-06) o evidencia de atomicidad posicional.
- RBAC: `caja:reportar` — consulta/directivo → 403; financiero/admin OK; GET conciliación intacto para los 4 roles; guardián + completitud catálogo 37.
- D6: reintento mismo body → mismo estado + evento anterior == nuevo.
- Regla 1: saldo string en API (strict rechaza number); Decimal end-to-end.

Camino: construir con TDD incorporando B-1 → I-PR1 con esos tests → merge. Sin re-auditoría de plan.

Kimi — auditor técnico senior independiente. Veredicto: GO — 9.3/10.
