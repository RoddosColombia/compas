// frontend/src/lib/money.ts
//
// Regla 1 de CLAUDE.md (dinero) — patrón fijado ANTES de que exista una sola
// cifra en la UI:
//   • Los montos llegan de la API como STRING decimal (Spec §0.2).
//   • NUNCA se usa `Number` sobre un monto: se manejan con decimal.js-light.
//   • El formato de presentación es SOLO con Intl.NumberFormat('es-CO').
//   • Todo cálculo financiero vive en el backend; el frontend presenta.
//
// Formato objetivo: $ 1.234.567,89 (STACK §3, F-12).

import Decimal from "decimal.js-light";

// COP se registra con 2 decimales.
Decimal.config({ precision: 30, rounding: Decimal.ROUND_HALF_UP });

/** Convierte un monto-string de la API a Decimal. Rechaza `number` por tipo. */
export function parseMonto(value: string): Decimal {
  return new Decimal(value);
}

const copFormatter = new Intl.NumberFormat("es-CO", {
  style: "currency",
  currency: "COP",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/**
 * Formatea un monto (string de la API o Decimal) como pesos colombianos.
 * Ej: "1234567.89" -> "$ 1.234.567,89".
 */
export function formatCOP(value: string | Decimal): string {
  const dec = value instanceof Decimal ? value : new Decimal(value);
  // Intl formatea sobre number solo para PRESENTACIÓN, nunca para cálculo.
  return copFormatter.format(dec.toNumber());
}

// ── F1: formato numérico es-CO por contexto (política §3 del sistema) ──
// KPI/protagonista = abreviado 1 decimal; delta = signo + flecha; el valor
// EXACTO nunca desaparece (va en title= del componente que lo muestre).

const compactFormatter = (d: number) =>
  new Intl.NumberFormat("es-CO", {
    minimumFractionDigits: 0,
    maximumFractionDigits: d,
  });

/**
 * Abrevia COP para cifras protagonistas: completo → M → mil M. 1 decimal, es-CO.
 * Umbral de "mil M" en ≥ 1e10 (no 1e9): así "$ 1.284 M" (1.284e9) y
 * "$ 95,9 mil M" (95,9e9) salen como en la tabla del sistema de diseño —
 * la tabla manda sobre el sketch de código del spec (contradicción resuelta
 * a favor del ejemplo visible; pendiente "mil M" vs "MM" con el CEO).
 */
export function formatCOPCompact(value: string | Decimal): string {
  const dec = value instanceof Decimal ? value : new Decimal(value);
  const abs = dec.abs();
  const signo = dec.isNegative() ? "-" : "";
  // Intl SOLO presentación (como formatCOP); el redondeo fino lo hace Decimal.
  if (abs.greaterThanOrEqualTo(1e10)) {
    return `${signo}$ ${compactFormatter(1).format(abs.div(1e9).toDecimalPlaces(1).toNumber())} mil M`;
  }
  if (abs.greaterThanOrEqualTo(1e6)) {
    return `${signo}$ ${compactFormatter(1).format(abs.div(1e6).toDecimalPlaces(1).toNumber())} M`;
  }
  return `${signo}$ ${compactFormatter(0).format(abs.toDecimalPlaces(0).toNumber())}`;
}

export interface Delta {
  texto: string;
  direccion: "sube" | "baja" | "igual";
}

/** Delta con signo y flecha para comparaciones de KPI: "▲ +$ 12,9 M". */
export function formatDelta(value: string | Decimal): Delta {
  const dec = value instanceof Decimal ? value : new Decimal(value);
  if (dec.isZero()) return { texto: "— sin cambio", direccion: "igual" };
  const compacto = formatCOPCompact(dec.abs());
  return dec.isNegative()
    ? { texto: `▼ -${compacto}`, direccion: "baja" }
    : { texto: `▲ +${compacto}`, direccion: "sube" };
}

const MESES = [
  "ene",
  "feb",
  "mar",
  "abr",
  "may",
  "jun",
  "jul",
  "ago",
  "sep",
  "oct",
  "nov",
  "dic",
];

/** Formatea una fecha `YYYY-MM-DD` como `dd-mmm-aaaa` (ej: 18-jul-2026). */
export function formatFecha(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${d}-${MESES[Number(m) - 1]}-${y}`;
}

/** Formatea un mes `YYYY-MM` como `mmm-aa` (ej: may-27) — ejes y anotaciones. */
export function formatMesCorto(mes: string): string {
  const [y, m] = mes.split("-");
  return `${MESES[Number(m) - 1]}-${y.slice(2)}`;
}
