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

const MESES = [
  "ene", "feb", "mar", "abr", "may", "jun",
  "jul", "ago", "sep", "oct", "nov", "dic",
];

/** Formatea una fecha `YYYY-MM-DD` como `dd-mmm-aaaa` (ej: 18-jul-2026). */
export function formatFecha(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${d}-${MESES[Number(m) - 1]}-${y}`;
}
