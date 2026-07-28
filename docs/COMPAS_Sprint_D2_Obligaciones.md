# Sprint D2 — Obligaciones genéricas, facturas por plazo y metas de ingreso

**Fecha:** 2026-07-27 · **Prerequisito:** D1 en producción (✅ `95acf9c`) · **Antes del kickoff:** este documento en `docs/` (regla §9)
**Reglas que gobiernan (plan maestro §2):** `motor.py` **cero diffs** — reutilizar sus funciones puras POR IMPORT es legítimo y deseable; modificarlas no. Golden-master como gate. TDD, un commit por pieza, simular nunca escribe, expand-contract si hay migración.

---

## 0. Pieza 0 — Arrastre de D1: techo × gasto ejecutado del mes (brief §4.7 completo)

La tarjeta "Techo de gasto mensual sostenido" (D1) gana su mitad operativa: cruce contra el **mes en ejecución** de la Cabina usando la Vista Control existente (`control.service` — ⚠ VERIFICAR shape exacto):

- Muestra: gasto ejecutado del mes en curso · disponible frente al techo · % consumido · estado `atencion/critico` cuando el ritmo proyectado del mes (ejecutado ÷ % de mes transcurrido — reutilizar `pctMesTranscurrido` de C2) excede el techo, **indicando en cuánto**.
- Parámetros visibles y editables en la propia tarjeta (colchón, horizonte de análisis) — auditable, no caja negra (ya venía de D1; se conserva).
- Sin mes en ejecución → contexto honesto ("sin mes en ejecución — el cruce se activa con el ciclo").
- Tests: con fixture de Vista Control, el % y el estado disparan en los umbrales; sin mes activo no revienta.

**Esta pieza sale primero y puede desplegarse sola si el resto del sprint se alarga.**

## 1. Objetivo del sprint

Que ninguna deuda ni cuenta por pagar sea un caso especial: **Obligación** como entidad configurable de dos naturalezas, con registro factura a factura y el plazo como palanca de decisión. Además, el ingreso proyectado como **meta** visible en Presupuesto. Es el §7 del brief completo.

**Prueba de terminado (una sola):** Andrés registra una factura Auteco de $180 M con fecha 15-ago y plazo 150 días; el pago aparece solo en ene-27 en flujo y proyección, con el interés del 1,6 % mensual sobre los 60 días excedentes como **concepto separado**; el techo y los valles se ajustan; cambia el plazo a 90 y ve el pago moverse a nov-26 y el interés desaparecer; simula "150 días en todas" y la app le dice cuánta caja libera antes del valle y cuánto cuesta en intereses — todo sin que `motor.py` cambie.

## 2. Modelo de datos

```
Obligacion = {
  nombre, acreedor,
  naturaleza: "cuotas" | "facturacion",
  activo, creado_por, ...auditoría
  # naturaleza=cuotas:
  monto_total, n_cuotas, periodicidad, tasa_mensual, fecha_inicio, meses_gracia
  # naturaleza=facturacion (términos como ATRIBUTOS, no constantes):
  plazo_base_dias, plazo_max_dias, tasa_excedente_mensual
}
FacturaObligacion = { obligacion_id, fecha_factura, valor, plazo_elegido_dias, nota?, activo }
```

- CRUD auditado — **CR-D2** para los eventos nuevos (`obligacion.creada/editada/eliminada`, `factura_obligacion.registrada/anulada` — regla 11, declarar antes de construir, patrón CR-D1).
- Semilla: **Auteco** como obligación `facturacion` (90/150/1,6 % — desde los parámetros vigentes). La **deuda de inversores queda DENTRO del motor por ahora** (migrarla a obligación tipo `cuotas` cambia la configuración del motor vigente: es decisión del CEO con impacto visible, post-D2 — se deja anotado, no se hace).

## 3. Cálculo (reutilizar por IMPORT, jamás reconstruir)

- **Cuotas:** calendario generado (fecha_inicio + gracia + periodicidad × n_cuotas), capital e interés por cuota, Decimal.
- **Facturación:** por factura — `fecha_pago = fecha_factura + plazo_elegido`; `interés = valor × tasa_excedente × (días_excedentes/30)` donde `días_excedentes = max(0, plazo_elegido − plazo_base)`. Capital e interés como conceptos SEPARADOS, asignados al mes de pago.
- **Candado de paridad con la lógica existente** (criterio del brief: "produce los mismos resultados que antes"): test que reproduce el comportamiento de `inventario_auteco_mensual` (importada de `motor.py`, sin tocarla) para el caso equivalente global — mismo plazo/base/tasa sobre un lote mensual — y verifica que la calculadora por-factura, agregada al mes, da lo mismo al peso. Si la semántica difiere en algo (p. ej. el redondeo de `meses_interes = (plazo−base)//30` del motor vs. días exactos), **adoptar la del motor** y documentarlo: fuente única de verdad.

## 4. Integración a la proyección — la pieza delicada (anti-doble-conteo)

El motor YA proyecta el pago Auteco paramétricamente (`pago_inventario`, `fondeo`). Meter las facturas reales encima sin reconciliar duplicaría el egreso. Regla de reconciliación (capa post-motor, mecánica de `impactos.py` — motor intacto):

- **Ventana cubierta por facturas reales** = meses cuyo lote facturado ya está registrado (de la fecha de la factura más vieja activa a la más nueva). En esos meses: se **neta** el `pago_inventario`+`fondeo` paramétrico del motor y se aplica el calendario real (capital + interés) en sus meses de pago verdaderos.
- **Fuera de la ventana:** la proyección paramétrica del motor sigue tal cual (la continuación "meses sin factura" del brief queda cubierta por el propio motor v1; el supuesto seleccionable último-valor/promedio-N se anota como D2.1 si el CEO lo pide con datos en la mano).
- La serie resultante alimenta TODO lo de D1: valles, techo, goal seek, escenarios — sin cambios en esas piezas (reciben otra serie, misma forma).
- **Tests de la reconciliación:** sin facturas registradas == proyección base bit a bit; con una factura, el mes paramétrico netea y el real aparece; el interés sale como concepto separado en la serialización; golden-master intacta.
- ⚠ VERIFICAR antes de construir: cómo mapear "mes del lote paramétrico" ↔ "facturas reales de ese lote" con los campos disponibles; si la correspondencia limpia no existe, la ventana se define por decisión documentada (p. ej. desde el primer mes con factura registrada) y se muestra en la UI ("proyección paramétrica" vs. "facturas reales" marcadas visualmente — requisito del brief).

## 5. El plazo como palanca (simulador de política)

En la página de Obligaciones (§7): selector "¿Y si tomo 90 / 120 / 150 días?" — por factura individual o como política para todas las activas — recalculando por la capa: **alivio de caja mes a mes antes del próximo valle vs. costo financiero total del aplazamiento**, lado a lado (formato F1: dos KpiTileV2 + mini curva comparativa reutilizando el patrón de D1). Compute-only; aplicar la política de verdad = editar las facturas, explícito.

## 6. Metas de ingreso (brief §4.2, versión meta — el motor sigue mandando el ingreso proyectado)

- Entidad simple `MetaIngreso = {mes, valor, lineas?: [{nombre, valor}]}`, CRUD auditado (mismo CR-D2), editable en Presupuesto.
- En la vista de Presupuesto/Control del mes: **meta de ingreso · ingreso real ejecutado · % de cumplimiento** (el real sale de las transacciones de ingreso del mes — ⚠ VERIFICAR fuente exacta en `control.service`), y comparación informativa contra el ingreso del motor para ese mes ("tu meta está 8 % sobre lo que el motor proyecta").
- Es INFORMATIVA: no alimenta el motor ni la caja proyectada. Su contrato ⓘ lo dice.

## 7. UI

- **Página "Obligaciones"** (menú Planeación y control): lista de obligaciones con estado; detalle con calendario generado (cuotas) o facturas registradas + próximos pagos (facturación); registro de factura (fecha, valor, plazo con validación `base ≤ plazo ≤ max`, interés calculado en vivo antes de guardar); el simulador del §5.
- En **Decisiones** (D1): los pagos de obligaciones aparecen en las causas de los valles con su etiqueta ("Factura Auteco 15-ago · pago ene-27") — extender `CONCEPTO_ETIQUETA`/causas si aplica.
- En **Presupuesto**: bloque de meta de ingreso (§6).
- Unidades humanas (lib/unidades), contratos ⓘ en todo campo, montos string regla 1 — como C3/D1.

## 8. Tests / criterio de terminado

1. Paridad con la lógica existente (§3) — el criterio literal del brief.
2. Reconciliación §4: sin facturas == base bit a bit; con facturas, ni un peso doble.
3. Prueba de terminado E2E del §1 completa por API.
4. Factura con plazo fuera de rango → 422 llano; plazo = base → interés $0.
5. Metas: % de cumplimiento correcto con fixture; no toca proyección.
6. Pieza 0: techo × ejecutado con sus umbrales.
7. `motor.py` cero diffs en toda la rama; golden-master verde; suites completas backend y frontend.

## 9. Orden de ejecución

Pieza 0 (desplegable sola) → CR-D2 + entidades + CRUD → calculadora con candado de paridad → reconciliación a la proyección → página Obligaciones + registro de facturas → simulador de política → metas de ingreso → aceptación E2E. Un commit por pieza; desviaciones al PR; tracker `D2-OBLIGACIONES`; tabla §7 del plan al cierre.

**Fuera de alcance:** migrar la deuda de inversores al nuevo modelo (decisión CEO post-D2), el supuesto seleccionable de meses sin factura (D2.1), detección de recurrentes (D3), alertas persistentes (F7), y cualquier cambio a `motor.py`.
