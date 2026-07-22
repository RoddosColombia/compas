# SOLICITUD DE AUDITORÍA — sprint4-vista-control · I-PLAN: Vista Control (presupuesto vs ejecutado vs disponible)

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-07-22
**Docs contrato:** Spec §0.1 (tolerancias), §1.4 (PresupuestoLinea), §2.2, §2.4/§4.1 (RBAC lectura); PRD M2; CLAUDE.md reglas 1, 2, 3, 9. Spec §17: **todo cálculo financiero en backend**.
**Base:** `main` con cierre+conciliación mergeado (GO I-PR1 9.4, merge `9c62966`). **Nivel:** PLAN (pre-código).
**Alcance del gate:** el **endpoint de cálculo backend** (`% ejecutado`, disponible, semáforo) — la parte sensible que anunciaste auditar. El frontend de presentación (tabla + chips, tema RODDOS) es follow-up **sin gate** (como S3-04).

> En Sprint 3/4 anunciaste que auditarías el **% ejecutado** en Sprint 4. Esta pieza lo entrega como cálculo puro de Decimal en backend, para el demo G3.

## Qué se propone

**`GET /meses/{mes}/control`** (RBAC `dashboard:leer` — todos los roles leen). Solo meses en `en_ejecucion` o `cerrado` (tienen presupuesto aprobado); otro estado → 409 accionable. Respuesta (montos Decimal→**string**, regla 1):

1. **Por rubro** (de la línea `PresupuestoLinea` vigente del mes), agrupado en los **5 grupos** (rubro.grupo), ordenado por `rubro.orden`:
   - `definido` = `monto_definido` de la línea vigente.
   - `ejecutado` = Σ `valor` de las Transaccion de **EGRESO** del rubro en el mes.
   - `disponible` = `definido − ejecutado` (puede ser negativo si hay sobre-ejecución).
   - `pct_ejecutado` = `ejecutado / definido × 100` (Decimal, cuantizado 2 dec HALF_EVEN).
   - `semaforo` (calculado en backend, Spec §17): **verde `pct ≤ 90`** · **amarillo `90 < pct ≤ 100`** · **rojo `pct > 100`** (umbrales fijos, decisión CEO).
2. **Subtotal por grupo** y **total** (Σ definido, Σ ejecutado, Σ disponible).
3. **Línea de caja** del mes: `saldo_inicial_caja + Σ ingresos − Σ egresos`, EXCLUYENDO el rubro de sistema 'Ajuste de conciliación' (misma regla anti-doble-conteo del cierre).

## Decisiones declaradas (auditar)

1. **Semáforo (no está en el contrato):** verde ≤90, amarillo 90–100, rojo >100, sobre `pct_ejecutado`. Umbrales FIJOS (no configurables — decisión CEO). **Bordes con `definido == 0`:** si `ejecutado > 0` → rojo (gasto sin presupuesto); si `ejecutado == 0` → verde; `pct_ejecutado` se reporta como `null` (no se divide por cero, no se adivina — regla 7).
2. **Solo lectura:** sin escrituras, sin transacciones, sin eventos de auditoría (es una vista). No toca reglas 4/5/8. El único cálculo con dinero es agregación de datos ya persistidos.
3. **Ejecutado = solo egresos** del rubro en el mes (los rubros presupuestables son de egreso; el sugerido §1.4.1 se calculó sobre egresos). Rubros de sistema ('Por clasificar', 'Ajuste de conciliación', 'Recaudo') NO aparecen (no tienen línea de presupuesto).
4. **`$group`** para el ejecutado por rubro (1 agregación, como en el motor — RNF dashboard); equivalente a sumar las transacciones de egreso por rubro del mes.

## Semántica preservada (NO cambia)
Nada existente se modifica: solo se agrega un router de lectura. Motor/acotar/aprobar/cierre intactos. Dinero Decimal/string, Bogotá, Pydantic strict. Sin eventos nuevos (es lectura).

## Puntos a auditar con lupa
1. **Aritmética Decimal** de `pct_ejecutado` y `disponible` (cuantización, negativos, string en API).
2. **Bordes del semáforo** (definido=0, pct exactamente 90 y 100).
3. **Exclusión** de rubros de sistema y del 'Ajuste de conciliación' en la caja (anti-doble-conteo).
4. **Guarda de estado:** solo `en_ejecucion`/`cerrado`; RBAC `dashboard:leer`.
5. **Equivalencia `$group`** con la suma directa.

## Evidencia
- Sin código aún (PLAN). `main` con Sprint 3 + cierre completos; 298 tests verdes + 34 real-mongo en CI; deploy sano.

## Pregunta al auditor
¿El cálculo de Vista Control (% ejecutado, disponible, semáforo con esos umbrales y bordes, caja con exclusión del ajuste) es correcto para construir con TDD, o hay un riesgo a resolver en el PLAN? En particular, ¿los bordes del semáforo con `definido == 0` y la definición de `ejecutado` (solo egresos)?
