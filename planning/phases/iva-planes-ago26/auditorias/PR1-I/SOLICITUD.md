# SOLICITUD DE AUDITORÍA — iva-planes-ago26 I-PR1: auditoría RETROACTIVA de los 5 merges con gate-waiver del 2026-08-11 (PRs #90–#94)

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-08-11
**Plan padre:** (retroactiva — los 5 merges se hicieron con GATE-WAIVER y GO explícito del CEO, registrados en la hoja Gates del tracker; esta ronda salda la deuda de auditoría)
**Rama / PR:** main / #90, #91, #92, #93, #94

## Qué hace
Cinco entregables mergeados a `main` el 2026-08-11, todos con GO explícito del CEO y suite completa verde en cada merge:

1. **PR #90 — Import masivo del Excel DIAN al módulo IVA** (commit `66518ce`, merge `601fe37`). `POST /facturas/cargar-excel`: parser `excel_dian.py` con contrato de columnas explícito (regla 7: fail-loud, encabezados listados esperado vs encontrado), calibrado contra el export real del portal (528 filas, 0 errores). Un solo camino de escritura con la ingesta PDF (`persistir_factura_ingesta`: dedup CUFE + `factura.creada` fail-closed saga O1). Tipos no soportados (NC/POS), emitidas por RODDOS y receptor ajeno se rechazan con motivo. Frontend: `CargaPanel` acepta `.xlsx` (mismo componente de resultado; el motivo del backend manda).
2. **PR #91 — Auteco con dos NITs** (`51961e8`). Auteco factura con `860024781` (histórico) y `890900317` (AUTOTECNICA COLOMBIANA S.A.S., verificado contra la factura real E670165520 que cuadra AL PESO con el Excel DIAN). `NIT_AUTECO` pasa a `{"nits": [...]}` con compatibilidad hacia atrás (`{"nit": "..."}`); la auto-deducción compara por pertenencia al conjunto (`_nits_config` → frozenset).
3. **PR #92 — Saldo a favor declarado en la liquidación** (`1a7e7ad`). Clave `SALDO_FAVOR_IVA_DECLARADO` (`{"aplica_desde", "valor"}`): la cifra oficial de la declaración DIAN anterior a los datos de COMPAS entra como `saldo_favor_previo` del período configurado y **REEMPLAZA** el arrastre derivado (sumar sería doble conteo). Aplica en `GET /facturas/liquidacion` y en los egresos IVA de la proyección. Ausente o ilegible → no aplica (R5).
4. **PR #93 — Segundo plan de pago por modelo (78/52)** (`589c7e4`). `ModeloMoto` gana `plan2_plazo_semanas`/`plan2_cuota_semanal`/`peso_plan1` (fracción 0..1, por modelo). Capa ADITIVA: `_modelo_a_lineas` expande cada modelo en una línea de motor por plan con `mix = participación × peso`; **motor.py CERO diffs**, golden master intacto. Validaciones fail-closed (plan 2 incompleto / peso fuera de 0..1 / peso < 1 sin plan 2 → 422); `quitar_plan2` vuelve a un solo plan; el fingerprint del cache de sensibilidad incluye los campos nuevos. UI: tabla con ambos planes + sección en el diálogo de edición.
5. **PR #94 — El tornado mide la misma pista que la pantalla** (`f011ea5`). Bug reportado por el CEO ("todo en $0"): `sensibilidad_vigente` corría el motor CRUDO sin E1 (anclaje) ni D2 (reconciliación) → con caja inicial alta el piso quedaba clavado en el mes 0 y todos los deltas daban $0. Fix: las 14 corridas pasan por la misma tubería `motor → E1 → D2` (orden de precedencia de `_resultado_con`) y el cache incluye `_fingerprint_capas` (cierres/facturas de obligación invalidan).

## Cambios de valores esperados (verificados al peso)

| Caso | Antes | Después |
|---|---|---|
| Liquidación may–ago 2026 (prod) con 479 recibidas deducibles | descontable $0 · a pagar $150.651.484 | descontable $181.158.441 · neto $0 · favor $30.506.957 |
| + saldo declarado $28.950.000 (PR #92) | favor $30.506.957 | favor previo $28.950.000 · neto $0 · **favor $59.456.957** |
| 9 facturas Auteco (PDF real) vs Excel DIAN | 0 coincidencias (NIT equivocado en config) | **9/9 CUADRAN AL PESO** (IVA idéntico factura a factura, Σ $170.710.393) |
| Tornado (prod, mes_inicio 2026-08) | piso "base" $704.722.003 · TODOS los deltas $0 | piso $492.513.306 (= mínimo real, feb-2027) · deltas reales (colocación ±10% → +$150,4M/−$178,6M) |
| Modelo partido en dos planes IDÉNTICOS (candado) | n/a | cuotas iniciales EXACTAS; recaudo ≤0.5%/mes (colocación semanal entera del motor certificado) |

## Semántica preservada (NO cambia en estos PRs)
- **motor.py: CERO diffs en los 5 PRs.** Golden master (0.042 COP vs artefacto) verde en cada merge.
- Sin plan 2, `_modelo_a_lineas` produce UNA línea idéntica a la histórica (candado en test).
- La forma vieja `{"nit": "..."}` de NIT_AUTECO sigue funcionando (compat probada).
- Ingesta PDF intacta (mismo `persistir_factura_ingesta`, tests previos verdes).
- Liquidación sin `SALDO_FAVOR_IVA_DECLARADO` configurado = bit a bit la de antes.
- Histórico inmutable, Decimal en todo el dinero, montos string en API, auditoría fail-closed saga O1 en toda mutación (facturas, modelos, deducibilidad en lote).

## Puntos a auditar con lupa
1. **PR #92 — semántica de REEMPLAZO del arrastre**: el declarado sustituye (no suma) el saldo derivado de períodos anteriores al llegar a su período; si el período de `aplica_desde` no tiene facturas, fluye al primer período posterior con datos; los períodos ANTERIORES no cambian. ¿Hay algún camino donde se doble-cuente o se pierda?
2. **PR #93 — expansión de líneas vs contratos internos del motor**: el modelo 0 absorbe el resto del split (`_split_por_mix`) y `apache_por_mes` ancla su override al ÍNDICE 1 de la lista. Verificamos que NINGÚN camino de producción alimenta `apache_por_mes` (solo fixtures del golden). ¿De acuerdo con que la expansión no rompe ningún contrato vivo, y con documentar el riesgo del índice 1 si algún día se usa?
3. **PR #94 — el tornado con capas**: los meses anclados (E1) no responden a las variaciones (el pasado es del libro). ¿Es la lectura correcta del tornado o debería excluirse el tramo anclado del cálculo del piso?
4. **PR #90 — regla 7 en el parser Excel**: fila ilegible = error de ESA fila con motivo (lote parcial); dedup por CUFE contra la base. ¿Algún vector de interpretación silenciosa que se nos escape (montos es-CO, fechas dd-mm-yyyy)?
5. **PR #91 — `_nits_config`**: ¿la coerción `str(n) for n in nits if n` deja pasar algún NIT malformado que deba rechazarse fail-loud?

## Evidencia local
- pytest (última suite tras #94): **966 passed / 95 skipped** (los skipped requieren Mongo real; suites intermedias: 934 → 938 → 948 → 966, verdes en cada merge).
- ruff: limpio · build frontend (`tsc -b` + vite): verde · vitest: **257 passed**.
- Verificaciones EN PRODUCCIÓN tras cada despliegue: liquidación may–ago con el liquidador real (favor $59.456.957); catálogo de modelos (Raider/Apache con plan 52 al 70/30, Sport solo 78); tornado con deltas reales (piso $492.513.306).
- Reglas innegociables: Decimal/string en API (regla 1), Pydantic strict (regla 3), auditoría append-only fail-closed (reglas 4/11 — eventos existentes, ninguno nuevo), parsers fail-loud (regla 7), RBAC por dependencia (regla 9).

## Cumplimiento del DoD / reglas de CLAUDE.md
- Gate-waiver de los 5 merges registrado en la hoja Gates del tracker con el GO del CEO (procedimiento [[ceo-go-autoriza-fase-sin-kimi]]); esta SOLICITUD salda la auditoría retroactiva comprometida.
- TDD estricto en los 5 PRs (tests primero en rojo, documentado en cada PR).
- Tracker actualizado por tarea (C2P-EXCEL-DIAN, AUTECO-2NITS, SALDO-FAVOR-DECLARADO, PLAN-52, FIX-TORNADO).
