# SOLICITUD DE AUDITORÍA — CICLO-MENSUAL RETRO-I: retro-gate SUP-2 → ciclo mensual (el ítem 7 de tu etapa75)

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-08-24
**Contrato padre:** `docs/COMPAS_Ciclo_Mensual.md` (aprobado por el CEO 2026-08-23) · roadmap `docs/COMPAS_CICLO_ROADMAP.md`
**Rango auditado:** commits `0f391e8` (SUP-2) → `d604556` (main hoy) — PRs #97 #98 #99 #100 #102
**Carácter:** RETROACTIVO. Todo esto está mergeado y desplegado bajo gate-waiver GO CEO
(Kimi en SISMO); es exactamente la acumulación de waivers que tu etapa75 señaló. Este
paquete es el pago de esa deuda: pedimos el juicio adversarial completo, con la
disposición a revertir lo que no pase.

## Qué hace (las evoluciones del motor y sus capas, en orden)

1. **SUP-2 (#97)** — 4 variables clavadas pasan a editables: mora/recuperación por
   escenario extremo (salen de `PRESETS_ESCENARIO`), rezago de recuperación
   (`meses_rezago_recuperacion`, v9.1: la mora del mes m−1 se recupera en m), prefondeo
   del IVA (`pct_prefondeo_iva`) y fondo AVAL (`pct_aval_recaudo`, egreso nuevo =
   % del recaudo de crédito). `motor.py`: `neto_por_mora(..., mora_a_recuperar)` +
   serie `aval`.
2. **SUP-3 (#98)** — el IVA de ventas FUTURAS entra a la liquidación:
   `app/iva/proyectado.py` convierte la colocación proyectada en `FacturaIva`
   sintéticas para el liquidador EXISTENTE. Candado: un mes con dato real no se
   proyecta.
3. **SUP-4 (#99)** — carga semanal del cronograma de SISMO → serie semanal de la
   cartera ya originada (sin persistir las ~9.900 cuotas). *(Parcialmente supersedido
   por el ciclo mensual: ver 5.)*
4. **SUP-5/SUP-6 (#100)** — cada mes expone `mora/recuperacion/default` (antes
   viajaban sumadas en `neto`); la respuesta publica los supuestos EFECTIVOS del
   escenario; y la mora/default/provisión caen SOLO sobre las cuotas semanales
   (`mora_sobre_recaudo` — la cuota inicial es de contado; tu propio hallazgo,
   corregido antes de tu etapa75).
5. **CICLO MENSUAL P1–P7 (#100)** — el contrato del CEO hecho código:
   - **P1 candado aritmético:** `caja(m)=caja(m−1)+flujo(m)` · `flujo=neto+egresos` ·
     `neto=inicial+semanales+ajuste` · `ajuste=mora+recup+default`, verificado en los
     144 meses × 3 escenarios × 3 capas (motor → E1 anclaje → D2 reconciliación).
   - **P2 arranque heredado:** la proyección arranca del efectivo real del cierre
     anterior (`MesControl.saldo_inicial_caja` + tránsito Wava = la MISMA definición
     que `caja_inicial_total` de la pantalla del ciclo, con test que compara ambas).
     `caja_inicial` queda como semilla/override.
   - **P3 el primer mes acumula su flujo:** quita la convención del artefacto
     ("primer mes: caja fija"). `primer_mes_acumula_flujo` en el motor +
     `primer_mes_acumula` en `reacumular`, propagado a E1/D2/D1.
   - **P4 mes en curso = objetivo:** la Regla A / D-08 queda SOLO para meses cerrados
     (un mes en ejecución muestra su PRESUPUESTO); la carga semanal DEJA de escribir
     la meta (pisaba el dato del CEO: 70 → 35).
   - **P5 cronograma del mes completo:** el mes en curso cuenta sus cuotas por el
     monto pactado (pagadas incluidas); regla de NO-SOLAPE (la serie se corta al
     cierre del mes anterior; los créditos del mes en curso los proyecta el motor).
   - **P6 termómetro:** colocaciones/ingreso/gasto reales AL LADO de la curva, sin
     tocarla (candado en test: con o sin realidad cargada, la serie es idéntica).
   - **P7 sugerencia de gasto:** promedio del CONCEPTO `gastos_fijos` (mapeo de E1)
     de los 3 meses cerrados; SUGIERE, nunca escribe.
6. **Ítems 0 y 4 de tu etapa75 (#102)** — el aval entra al bucket Gasto del frontend
   (`egreso.ts`) con candado de reconciliación; columna «Caja al cerrar» + desglose
   Inicia/Flujo/Cierra + tarjeta «arranca con X · cerraría en Y».

## Cambios de valores esperados (verificados al peso, agosto-2026 en PROD)

| Caso | Antes | Después | Causa |
|---|---|---|---|
| Caja de arranque | 704.722.003 (tecleado) | 665.715.578 (cierre real jul) | P2 |
| Egresos ago | −240.209.500 | −240.755.741,68 | P1: aval recuperado (+546.241,68) |
| Ingreso neto ago (serie vieja) | 105.324.084,52 | 170.380.010,16 | SUP-6 + P4 (meta 60) |
| Candado en PROD hoy | caja fija ≠ suma | 665.715.578 − 70.532.363,52 = **595.183.214,48** = caja | P3 |
| Regla A mes en curso | ejec + max(0, def−ejec) | el presupuesto | P4 (supersede D-08) |
| Rampa mes en curso | remanente (35) | dato del CEO (60) | P4 (supersede SUP-4) |

*(Ops pendiente, declarada: la serie de la cartera en PROD sigue siendo la truncada
pre-P5 — falta que el CEO re-suba el cronograma. Con la serie del mes completo el
neto de agosto da 252.783.377,70, verificado en dry-run read-only.)*

## Semántica preservada

- **GOLDEN MASTER bit a bit:** cada cambio del motor entró como parámetro cuyo
  DEFAULT reproduce el artefacto (`meses_rezago_recuperacion=0`, `pct_aval_recaudo=0`,
  `mora_sobre_recaudo=False`, `primer_mes_acumula_flujo=False`, `crec_pct_mensual_2=None`,
  `iva_egreso_por_mes=None`, series de cartera=None). `test_golden_master` valida al
  peso (0,042 COP) contra `simular()` del artefacto — verde en cada pieza y hoy.
- Histórico inmutable, Decimal/COP-2, TZ Bogotá, Pydantic strict, audit append-only.
- D1 regla de oro (`ajustes=[] ⇒ base bit a bit`) y B1 de E1 (`anclas={} ⇒ base`).

## Puntos a auditar con lupa

1. **P3 × las tres capas:** `reacumular(primer_mes_acumula)` deriva el arranque de la
   propia serie (`caja[0] − flujo[0]`). ¿Hay algún camino donde una capa re-acumule
   con el flag y otra sin él (doble conteo o congelamiento del primer mes)? Revisar
   los 6 call-sites en `proyeccion/service.py` y el de COCK-09 (que ahora arranca el
   forecast el mes SIGUIENTE al ancla).
2. **Regla de NO-SOLAPE de P5:** créditos sin cuota 0 se asumen preexistentes.
   ¿Un crédito del mes en curso cuyo desembolso no venga en el export se contaría
   dos veces (serie + motor)?
3. **P4 fail-safe `_es_anclable`:** un mes en ejecución SIN presupuesto no se ancla
   (cae al motor). ¿Correcto, o debería anclar gasto 0 explícito?
4. **SUP-3:** la exclusión de meses con dato real (`VENTAS-YYYY-MM` + CERRADO).
   ¿Alguna ventana donde el IVA proyectado y el real coexistan?
5. **El rezago de recuperación (SUP-2)** interactúa con `mora_sobre_recaudo` (SUP-6):
   la recuperación de m usa la mora de m−1, que ya se calculó sobre la base nueva.
   ¿Coherente en el mes de transición del flag?
6. **Gobernanza:** tu observación de etapa75 queda aceptada — después de este retro,
   ninguna evolución más del motor sin gate previo (waiver solo para excepciones).

## Evidencia local (corrida HOY, sobre main)

- pytest focalizado del alcance: **118 passed / 0 failed** (golden + candado +
  SUP-2/3/4/5/6 + P2–P7); suite completa backend: **1220 passed / 0 failed**.
- frontend: **293 passed** + `npm run build` verde + biome limpio.
- ruff check + format: limpios. Reglas innegociables verificadas.
- PROD read-only (hoy): flags vigentes y candado al peso — ver EVIDENCIA.md §3.

## Solicitud adicional (bloqueo de los ítems 1 y 3 de tu cola)

El CEO no tiene el archivo **etapa73** al que refieren tus ítems 1 (invariante #4,
piso) y 3 (Docs #5/#6). Para no adivinar su contenido: **re-enuncia en tu respuesta
esos ítems completos** (qué invariante, qué documentos), y los ejecutamos contra tu
texto, no contra una interpretación.
