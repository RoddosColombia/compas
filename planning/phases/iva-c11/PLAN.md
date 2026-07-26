# PLAN — IVA por cargue de facturas (C11, PR-2 del CR "Fidelidad de caja")

**Fase:** `iva-c11` · **Fecha:** 2026-07-25 · **Autor:** Claude Code
**Gate:** código CRÍTICO de dinero + calendario DIAN → **GO del CEO** habilita construir
(Kimi ausente; gate-waiver trazable + auditoría Kimi retroactiva).
**Docs contrato:** `docs/modelo/AUDITORIA-IVA-ARTIFACT-V2.md` §5-6 (diseño objetivo),
`docs/Calendario_DIAN_2026.md`, `COMPAS_NORTE.md`; CLAUDE.md reglas 1, 2, 3, 4, 11 +
**SKILL IVA (cuatrimestral, NUNCA bimestral; 19%; Auteco autorretenedor).**

## Problema (una oración)
El motor de proyección **no resta el IVA de la caja** → sobreestima el disponible; y
COMPAS no tiene forma de **cargar facturas** para liquidar el IVA real cuatrimestral.

## Objetivo
IVA **por cargue de facturas** (aproximado a la realidad, no por driver): cargar compras
(Auteco + otras deducibles) y ventas, liquidar el cuatrimestre (generado − descontable con
arrastre de saldo a favor), y **restar el IVA neto de la caja en la fecha DIAN real** —
cerrando la omisión IVA del motor (par de la cartera previa de PR-1).

## Alcance — 3 sub-PRs (cada uno TDD, cada uno su GO)

### PR-2a — Entidad `Factura` + liquidación cuatrimestral (backend) [P0.1, P0.3]
- **Entidad `Factura`** (Document, strict): `tipo` (venta|compra), `origen`
  (auteco|otra_compra|moto|repuesto|servicio…), `tercero_nombre`, `tercero_nit`, `fecha`
  (YYYY-MM-DD Bogotá), `base_gravable` (Money), `tarifa_iva` (Decimal; 0.19 / 0 exento),
  `iva_valor` (Money = base×tarifa, o extraído de total c/IVA vía 19/119), `total`,
  `deducible` (bool, para compras), `cuatrimestre` (derivado de fecha). Dedup coherente
  con regla 5. Baja lógica.
- **Servicio de carga** (CRUD, `iva:gestionar`) + **liquidación** (función pura, Decimal):
  ```
  generado_C    = Σ iva_valor (venta, fecha∈C)
  descontable_C = Σ iva_valor (compra ∧ deducible, fecha∈C)   ← incluye OTRAS compras, no solo Auteco
  saldo_C       = generado_C − descontable_C
  neto_a_pagar  = max(0, saldo_C − saldo_favor_arrastrado)
  nuevo_favor   = max(0, saldo_favor_arrastrado − saldo_C)
  ```
- Cuatrimestres ene-abr / may-ago / sep-dic (**cuatrimestral**, regla inamovible).

### PR-2b — Enchufar el IVA neto a la proyección de caja [P0.2] — el fix del motor
- Para cada cuatrimestre, egreso = `neto_a_pagar_C` en la **fecha DIAN real**
  (`CALENDARIO_DIAN`, dígito 2: 13-may-26 / 10-sep-26 / 14-ene-27), NO "día 15".
- Entra como **una fila más del flujo** en el mes de la fecha DIAN. El motor ya soporta
  overrides por mes (patrón de PR-3) → se inyecta un `iva_egreso_por_mes` a `proyectar()`.
- **Meses reales:** desde facturas cargadas. **Meses futuros:** generado/descontable
  proyectados desde el **motor C7** (unidades × precio/costo por modelo del catálogo
  `ModeloMoto`) — el **puente C11↔C7**. La golden ya prueba que ese driver funciona.

### PR-2c — Vista IVA del cockpit [P2.7] (sin gate, cálculo en backend)
Reemplaza el placeholder: curva IVA neto / próximo pago DIAN / saldo a favor / (fondo de
provisión si se aprueba P1). Consume el endpoint de liquidación.

## CR (declarar antes de construir — regla 11)
- **Entidad nueva** `Factura` (verificar: hoy NO existe en `domain/`).
- **Eventos:** el catálogo YA trae `factura.creada`, `iva.declarado`,
  `iva_generado.override`, `factura_emitida.creada/editada/anulada` (pre-declarados para
  C11). Reconciliar: reusar `factura.creada` para carga; `iva.declarado` para liquidación;
  evaluar si falta `factura.editada`/`factura.anulada` para compras (los `factura_emitida.*`
  son para ventas emitidas). Cambios mínimos, se confirman en PR-2a.
- **Capacidad nueva** `iva:gestionar` = {financiero, admin} (carga/edición de facturas y
  liquidación). La lectura de la vista IVA = `dashboard:leer`.

## Semántica / reglas innegociables
Dinero = Decimal, API string, cálculo SOLO en backend (regla 1). Bogotá, fechas
`YYYY-MM-DD`, cuatrimestre derivado (regla 2). Pydantic strict+forbid (regla 3). Histórico
inmutable; liquidación de cuatrimestre cerrado no se re-edita salvo factura tardía
(regla 4). **IVA CUATRIMESTRAL, tarifa 19%, Auteco (NIT 860024781) autorretenedor — su
IVA SÍ es descontable, pero NUNCA se le aplica ReteFuente** (SKILL IVA).

## En alcance — Fondo de provisión (P1.4, decisión CEO 2026-07-25)
Reserva mensual de tesorería para el pago cuatrimestral de IVA: acumula un % (o el
prorrateo del `neto_a_pagar_C`) mes a mes hasta la fecha DIAN, para que el pago no sea un
golpe seco a la caja. Se muestra como línea de fondo en la vista IVA y (a definir en 2b)
como reserva informativa en la proyección — el egreso real sigue cayendo en la fecha DIAN.

## Fuera de alcance de este PR (después)
Generado sobre repuestos/servicios (P1.5), simulador "¿cuánto IVA si vendo N motos?" en
Escenarios (P1.6), export a Excel (P2.8).

## Orden de construcción (TDD, red→green)
1. **PR-2a**: liquidación pura (sin Mongo) → red-green rápido; luego `Factura` + CRUD
   (mongomock; dedup/índice con real-mongo).
2. **PR-2b**: liquidación proyectada desde C7 + inyección del egreso IVA a `proyectar()`
   en la fecha DIAN; test de que la caja baja en el mes correcto.
3. **PR-2c**: vista IVA (Vitest+RTL).

## Decisión al CEO (D-A)
¿**GO** para construir PR-2 en este orden (2a liquidación+Factura → 2b egreso DIAN en la
proyección → 2c vista), con el alcance **P0 primero** (Factura + liquidación cuatrimestral
+ egreso en fecha DIAN real + otras compras deducibles) y P1/P2 como follow-ups? ¿O
prefieres incluir ya el **fondo de provisión** (P1.4) en este PR?
