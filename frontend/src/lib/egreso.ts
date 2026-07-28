// frontend/src/lib/egreso.ts
//
// V1 "Ver el egreso" — reagrupa los campos por mes del motor en TRES buckets de
// negocio. NO es cálculo financiero nuevo: son sumas de presentación de campos
// que el backend ya calculó (regla 1 respetada; decimal.js-light, nunca Number).
//
// Mapeo APROBADO por el CEO (2026-07-27), no re-litigar:
//   Ingreso = neto
//   Costo   = pago_inventario + fondeo + costo_nueva + adelanto   (el fondeo
//             Auteco es costo de inventario, no gasto financiero)
//   Gasto   = gastos_fijos + gps + int_deuda + iva
// Los egresos llegan NEGATIVOS del motor; costo y gasto se exponen como magnitud
// POSITIVA (lo que sale). Invariante: ingreso − (costo + gasto) == flujo.

import Decimal from "decimal.js-light";

import { parseMonto } from "@/lib/money";
import type { MesProyeccion } from "@/lib/proyeccion";

const CERO = new Decimal(0);

export interface BucketsMes {
  ingreso: Decimal; // = neto (positivo)
  costo: Decimal; // magnitud positiva: lote Auteco + fondeo + alistamiento
  gasto: Decimal; // magnitud positiva: fijos + GPS + intereses deuda + IVA
  flujo: Decimal; // = flujo del motor (referencia del candado)
}

/** Los tres buckets del mes. `costo` y `gasto` son magnitudes positivas. */
export function bucketsMes(m: MesProyeccion): BucketsMes {
  const ingreso = parseMonto(m.neto);
  const costo = parseMonto(m.pago_inventario)
    .plus(m.fondeo)
    .plus(m.costo_nueva)
    .plus(m.adelanto)
    .negated();
  const gasto = parseMonto(m.gastos_fijos)
    .plus(m.gps)
    .plus(m.int_deuda)
    .plus(m.iva)
    .negated();
  return { ingreso, costo, gasto, flujo: parseMonto(m.flujo) };
}

/** Suma de los buckets sobre una ventana de meses (fila de totales). */
export function totales(meses: MesProyeccion[]): BucketsMes {
  return meses.reduce<BucketsMes>(
    (acc, m) => {
      const b = bucketsMes(m);
      return {
        ingreso: acc.ingreso.plus(b.ingreso),
        costo: acc.costo.plus(b.costo),
        gasto: acc.gasto.plus(b.gasto),
        flujo: acc.flujo.plus(b.flujo),
      };
    },
    { ingreso: CERO, costo: CERO, gasto: CERO, flujo: CERO },
  );
}

/** Porción Auteco del costo del mes (lote + fondeo), magnitud POSITIVA — para el
 * hover del gráfico ("de los cuales Auteco: $X"). El interés (fondeo) va incluido. */
export function autecoDeMes(m: MesProyeccion): Decimal {
  return parseMonto(m.pago_inventario).plus(m.fondeo).negated();
}

/**
 * Candado anti-doble-conteo: el interés real ya viaja DENTRO de `fondeo` (Costo).
 * `interes_obligaciones` lo expone solo para mostrarlo; debe cumplir
 * `interes_obligaciones[mes] == |fondeo[mes]|`. Los meses SIN entrada (fuera de la
 * ventana reconciliada, donde el fondeo es paramétrico) no aplican → true.
 */
export function interesConcuerda(
  m: MesProyeccion,
  interesObligaciones: Record<string, string>,
): boolean {
  const expuesto = interesObligaciones[m.mes];
  if (expuesto === undefined) return true;
  return parseMonto(expuesto).equals(parseMonto(m.fondeo).abs());
}
