# CR-E2-EDITAR — Editar deducibilidad/origen de una factura (evento de auditoría)

**Sprint:** E2 · **PR:** PR2 (pantalla de IVA) · **Fecha:** 2026-07-30
**Solicita/aprueba:** Andrés San Juan (CEO) · **Ejecuta:** Claude Code
**Estado:** **APROBADO (GO del CEO 2026-07-30)** con el refinamiento del lote (§ Cambio
autorizado). Se codifica en el PASO 1 de PR2, **después** de que #46 mergee.

> **Nota de gobierno (M-3):** el *registro único de CR* aún no existe. Este CR se identifica
> por contenido (`CR-E2-EDITAR`), convención `CR-<sprint>` de `CR-D1`/`CR-D2`/`CR-E2-COMPUERTA`.
> **No abre una serie numérica nueva.** Se reconcilia en el registro único cuando se cree.

## Motivo (R3)

La pantalla de IVA (PR2) necesita **marcar la deducibilidad** de facturas recibidas —
individual y en lote— porque en la ingesta `deducible` entra en `false` por defecto y sin
esa decisión el IVA descontable queda subestimado (el riesgo que gobierna toda la pantalla,
spec de diseño §2). También permite corregir el **origen** de una factura `sin_clasificar`.

**Marcar deducibilidad CAMBIA el IVA a pagar** → debe quedar en el `audit_log` con autor
(regla 4: append-only; regla 3: el log solo crece con CR).

El catálogo cerrado (`backend/app/audit/events.py`, 58 eventos) tiene para esta `Factura`
(C11 IVA) solo `factura.creada` y `factura.anulada`. **No hay evento reutilizable** para una
edición: `factura_emitida.editada` existe pero es de **otra** entidad (el registro de
facturas EMITIDAS de ventas, no la `Factura` del liquidador de IVA — así está anotado en el
propio catálogo). Reusarlo sería un préstamo semántico que envejece mal.

## Cambio autorizado

Agregar **UN (1)** evento nuevo al catálogo:

```
factura_actualizada = "factura.actualizada"
```

- Cubre los dos campos editables del PATCH (`deducible`, `origen`). Uno solo, no dos:
  la acción es "se editó un campo permitido de una factura"; el detalle va en la metadata.
- **Metadata** (sin PII — ni nombre ni NIT del tercero, Ley 1581 / A17):
  `{ "campos": ["deducible"], "deducible": {"antes": false, "despues": true},
     "numero": "<numero>", "cufe": "<cufe|null>", "via": "individual|lote" }`
  (solo se incluyen las claves de los campos que cambiaron).
- **Emisión:** un evento POR FACTURA modificada (mismo patrón que `saldo_banco.reportado`
  de CR-S6: un evento por entidad tocada). El endpoint en lote emite N eventos, uno por id
  que cambió de verdad (si el valor no cambia, no se emite ni se cuenta como cambio).
- **Fail-closed POR FACTURA, no por lote (refinamiento del CEO 2026-07-30):** en el lote,
  cada factura es su propia saga: mutar → emitir → si el emit de ESA factura falla, se
  **revierte el cambio DE ESA factura** y su `id` sale con **error** en el resultado; las
  demás **continúan**. Nunca un cambio de deducibilidad sin su evento, y nunca un lote
  entero perdido por uno. (En el PATCH individual, el fallo del emit revierte y responde
  error, como `factura.creada`/`factura.anulada`.)

Conteo del catálogo: **58 → 59**.

## Qué NO cambia

- **La factura sigue siendo inmutable en lo fiscal:** el PATCH acepta SOLO `deducible` y
  `origen`. Montos, fechas, tipo, tercero, CUFE → intocables (se anula y se vuelve a cargar).
- `deducible` en una factura de **venta** → 422 (solo aplica a compras).
- `motor.py`: cero diffs. La liquidación se recalcula sola al leer `deducible` actualizado;
  la compuerta sigue apagada (D-12), así que la proyección no se mueve.
- No se inventan más eventos. Un solo miembro nuevo.

## Reversa

Quitar el miembro `factura_actualizada` del catálogo y los dos endpoints PATCH. El
`audit_log` es append-only: los eventos ya emitidos se conservan (son historia), no se borran.

## Auditoría de este CR

Va al paquete de auditoría de PR2 (Kimi). Sin GO del CEO, el PASO 1 no se codifica.
