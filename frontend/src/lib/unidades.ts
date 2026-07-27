// frontend/src/lib/unidades.ts
//
// C3 §2 — conversión de unidades HUMANAS ↔ canónicas (regla 1). La superficie
// muestra porcentajes como porcentajes ("5" = 5 %), montos con separador de
// miles es-CO y meses como meses calendario; al backend SIEMPRE viajan los
// strings canónicos (fracción "0.05", monto "1200000", índice entero). Todo
// con decimal.js-light — jamás float — y con tests de ida y vuelta.

import Decimal from "decimal.js-light";

// ── Porcentajes: "5" (humano, %) ↔ "0.05" (canónico, fracción) ──────────────

export function pctAFraccion(pct: string): string {
  return new Decimal(pct.trim().replace(",", ".")).div(100).toString();
}

export function fraccionAPct(fraccion: string): string {
  return new Decimal(fraccion).times(100).toString();
}

/** Equivalente anual compuesto de una tasa mensual (fracción): "0.05" → "79.6".
 * Presentación de la advertencia "5 % mensual ≈ +80 % anual". */
export function pctAnualEquivalente(fraccionMensual: string): string {
  const m = new Decimal(fraccionMensual).plus(1);
  return m.toPower(12).minus(1).times(100).toDecimalPlaces(1).toString();
}

// ── Montos: "1.200.000" (humano es-CO) ↔ "1200000" (canónico) ────────────────

/** Acepta "1.200.000", "1200000" y decimales con coma ("1.200.000,50"). */
export function montoACanonico(humano: string): string {
  const limpio = humano.trim().replace(/\./g, "").replace(",", ".");
  return new Decimal(limpio).toString();
}

/** "1200000" → "1.200.000" (separador de miles es-CO mientras se escribe). */
export function montoAHumano(canonico: string): string {
  if (canonico.trim() === "") return "";
  const dec = new Decimal(canonico);
  // Intl SOLO presentación (regla 1)
  return new Intl.NumberFormat("es-CO", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(dec.toNumber());
}

// ── Meses: índice del motor ↔ mes calendario "YYYY-MM" ───────────────────────
// El índice es relativo al mes de inicio de la proyección (por defecto, el mes
// actual). La referencia es explícita para que la conversión sea determinista.

export function indiceAMes(indice: number, referencia: string): string {
  const [y, m] = referencia.split("-").map(Number);
  const total = y * 12 + (m - 1) + indice;
  const y2 = Math.floor(total / 12);
  const m2 = (total % 12) + 1;
  return `${y2}-${String(m2).padStart(2, "0")}`;
}

export function mesAIndice(mes: string, referencia: string): number {
  const [y, m] = mes.split("-").map(Number);
  const [yr, mr] = referencia.split("-").map(Number);
  return y * 12 + m - (yr * 12 + mr);
}

// ── Horizonte: "144 meses (12 años, jul-26 → jun-38)" ────────────────────────

const MESES_CORTOS = [
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

function mmmAa(mes: string): string {
  const [y, m] = mes.split("-");
  return `${MESES_CORTOS[Number(m) - 1]}-${y.slice(2)}`;
}

export function resumenHorizonte(meses: number, referencia: string): string {
  const fin = indiceAMes(meses - 1, referencia);
  const anos = meses / 12;
  const anosTxt = Number.isInteger(anos)
    ? `${anos} ${anos === 1 ? "año" : "años"}`
    : `${anos.toFixed(1)} años`;
  return `${anosTxt}, ${mmmAa(referencia)} → ${mmmAa(fin)}`;
}

/** ¿Es un número humano válido? (dígitos con separadores es-CO opcionales) */
export function esMontoHumanoValido(v: string): boolean {
  return /^\d{1,3}(\.\d{3})*(,\d{1,2})?$|^\d+([.,]\d{1,2})?$/.test(v.trim());
}

export function esPctValido(v: string): boolean {
  return /^\d+([.,]\d+)?$/.test(v.trim());
}
