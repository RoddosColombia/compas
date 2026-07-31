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

import { formatMesCorto, parseMonto } from "@/lib/money";
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

export interface CompromisoAuteco {
  mes: string; // 'YYYY-MM' del próximo compromiso
  monto: Decimal; // lote + fondeo de ese mes (magnitud positiva)
  mesesDistancia: number; // 0 = este mes, 1 = el siguiente, …
  real: boolean; // el mes cae en la ventana reconciliada (factura registrada)
}

/** V1.1 ítem 6: el PRÓXIMO compromiso Auteco (no la suma de los dos primeros meses,
 * que daba "$0" cuando ambos eran paramétricos). Recorre la ventana y devuelve el
 * primer mes con Auteco > 0, con su distancia en meses; `null` si no hay ninguno. */
export function proximoCompromisoAuteco(
  meses: MesProyeccion[],
  ventanaRec: [string, string] | null,
): CompromisoAuteco | null {
  for (let i = 0; i < meses.length; i++) {
    const monto = autecoDeMes(meses[i]);
    if (monto.greaterThan(0)) {
      const mes = meses[i].mes;
      const real =
        ventanaRec !== null && mes >= ventanaRec[0] && mes <= ventanaRec[1];
      return { mes, monto, mesesDistancia: i, real };
    }
  }
  return null;
}

// ── Agregación del gráfico (§2/§5): mensual, trimestral o anual según el nº de
// meses, para que el eje X no se sature en horizontes largos. Los buckets se SUMAN
// por período; la caja es la del ÚLTIMO mes del período (es un stock, no un flujo). ──

export type Periodicidad = "mes" | "trimestre" | "anio";

export interface PuntoComposicion {
  etiqueta: string; // "oct-26" | "T4-26" | "2028"
  // Los montos se ACUMULAN en Decimal (regla 1): son cifras que se muestran, no
  // geometría. El gráfico deriva el number solo para las barras (con .toNumber()).
  ingreso: Decimal;
  costo: Decimal;
  gasto: Decimal;
  flujo: Decimal;
  caja: Decimal; // caja al cierre del período
  auteco: Decimal; // lote + fondeo del período (magnitud) — porción Auteco del costo
  // V1.1 discriminación (ítems 1-2): NO re-mapea nada, son sumas de presentación.
  recaudo: Decimal; // ingreso: cuotas semanales del crédito (recaudo_credito)
  inicial: Decimal; // ingreso: cuota inicial (cuotas_iniciales)
  nueva: Decimal; // costo de moto nueva (costo_nueva + adelanto); auteco + nueva == costo
  real: boolean; // algún mes del período cae en la ventana reconciliada
}

/** Costo de moto nueva del mes (alistamiento + adelanto), magnitud POSITIVA. Con la
 * porción Auteco (`autecoDeMes`) reconstruye el bucket costo: auteco + nueva == costo. */
export function nuevaDeMes(m: MesProyeccion): Decimal {
  return parseMonto(m.costo_nueva).plus(m.adelanto).negated();
}

/** Periodicidad recomendada por longitud de la ventana. */
export function periodicidadPara(nMeses: number): Periodicidad {
  if (nMeses <= 24) return "mes";
  if (nMeses <= 96) return "trimestre";
  return "anio";
}

function claveEtiqueta(mes: string, modo: Periodicidad): [string, string] {
  const [y, m] = mes.split("-");
  if (modo === "anio") return [y, y];
  if (modo === "trimestre") {
    const q = Math.floor((Number(m) - 1) / 3) + 1;
    return [`${y}-Q${q}`, `T${q}-${y.slice(2)}`];
  }
  return [mes, formatMesCorto(mes)];
}

/** Normaliza la serie mensual a puntos del gráfico, agregando por período cuando la
 * ventana es larga. Con `modo` omitido se elige por longitud (periodicidadPara). */
export function puntosComposicion(
  meses: MesProyeccion[],
  ventanaRec: [string, string] | null,
  modo: Periodicidad = periodicidadPara(meses.length),
): PuntoComposicion[] {
  const out: PuntoComposicion[] = [];
  let claveActual: string | null = null;
  for (const m of meses) {
    const [clave, etiqueta] = claveEtiqueta(m.mes, modo);
    const b = bucketsMes(m);
    const real =
      ventanaRec !== null && m.mes >= ventanaRec[0] && m.mes <= ventanaRec[1];
    if (clave !== claveActual) {
      out.push({
        etiqueta,
        ingreso: b.ingreso,
        costo: b.costo,
        gasto: b.gasto,
        flujo: b.flujo,
        caja: parseMonto(m.caja),
        auteco: autecoDeMes(m),
        recaudo: parseMonto(m.recaudo_credito),
        inicial: parseMonto(m.cuotas_iniciales),
        nueva: nuevaDeMes(m),
        real,
      });
      claveActual = clave;
    } else {
      const p = out[out.length - 1];
      p.ingreso = p.ingreso.plus(b.ingreso);
      p.costo = p.costo.plus(b.costo);
      p.gasto = p.gasto.plus(b.gasto);
      p.flujo = p.flujo.plus(b.flujo);
      p.caja = parseMonto(m.caja); // último mes del período
      p.auteco = p.auteco.plus(autecoDeMes(m));
      p.recaudo = p.recaudo.plus(m.recaudo_credito);
      p.inicial = p.inicial.plus(m.cuotas_iniciales);
      p.nueva = p.nueva.plus(nuevaDeMes(m));
      p.real = p.real || real;
    }
  }
  return out;
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
