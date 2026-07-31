// frontend/src/components/iva/TitularIva.tsx
//
// Titular de /iva (spec de diseño §3①) — la CONCLUSIÓN del período, no una etiqueta.
// Cuatro variantes; la del §2 (recibidas sin decidir deducibilidad) tiene PRECEDENCIA:
// mientras existan, la liquidación es PROVISIONAL y el titular ADVIERTE antes de dar
// la cifra (nunca datos parciales con autoridad de completos). La variante "sin
// facturas" es el estado vacío accionable de la pantalla (§6), no este componente.
//
// Cero aritmética de dinero (regla 1): los montos vienen del backend; el front solo
// formatea y COMPARA (decimal.js-light solo para comparar, §5). `critico` no se usa:
// pagar IVA es normal (§7). La compuerta sigue apagada → línea de honestidad fija.

import type { FacturaRow } from "@/lib/facturas";
import type { LiquidacionIva, Periodicidad } from "@/lib/iva";
import { formatCOP, parseMonto } from "@/lib/money";

const MESES_ABBR = [
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

function mesesPorPeriodo(p: Periodicidad): number {
  return p === "cuatrimestral" ? 4 : 2;
}

function rango(idx: number, p: Periodicidad): string {
  const meses = mesesPorPeriodo(p);
  return `${MESES_ABBR[(idx - 1) * meses]}–${MESES_ABBR[idx * meses - 1]}`;
}

function plural(n: number, uno: string, varios: string): string {
  return `${n} ${n === 1 ? uno : varios}`;
}

export function TitularIva({
  liquidacion,
  facturas,
  hoy = new Date(),
}: {
  liquidacion: LiquidacionIva;
  facturas: FacturaRow[];
  /** Inyectable para pruebas deterministas; por defecto, ahora. */
  hoy?: Date;
}) {
  const p = liquidacion.periodicidad;
  const meses = mesesPorPeriodo(p);
  const anio = hoy.getFullYear();
  const idx = Math.floor(hoy.getMonth() / meses) + 1;
  const etiqueta = `${anio}-${p === "cuatrimestral" ? "C" : "B"}${idx}`;
  const nombrePeriodo = p === "cuatrimestral" ? "cuatrimestre" : "bimestre";
  const NombrePeriodo = p === "cuatrimestral" ? "Cuatrimestre" : "Bimestre";

  const actual =
    liquidacion.periodos.find((x) => x.etiqueta === etiqueta) ?? null;
  const enPeriodo = facturas.filter((f) => f.periodo === etiqueta).length;
  const sinDecidir = facturas.filter(
    (f) => f.activo && f.tipo === "compra" && !f.deducible_decidido,
  ).length;

  let titulo: string;
  let tono: "neutro" | "positivo" | "atencion";
  if (sinDecidir > 0) {
    // §2: advertir ANTES del número — la cifra aún no es confiable
    titulo = `Faltan ${plural(sinDecidir, "factura", "facturas")} por revisar para que la cifra de IVA sea confiable`;
    tono = "atencion";
  } else if (actual && parseMonto(actual.saldo_favor_nuevo).gt(0)) {
    titulo = `Quedas con saldo a favor de ${formatCOP(actual.saldo_favor_nuevo)}`;
    tono = "positivo";
  } else if (actual) {
    titulo = `Este ${nombrePeriodo} pagarías ${formatCOP(actual.neto_a_pagar)} a la DIAN`;
    tono = "neutro";
  } else {
    // hay facturas, pero ninguna de este período: honesto, no una cifra en cero
    titulo = `Este ${nombrePeriodo} aún no tiene facturas cargadas`;
    tono = "neutro";
  }

  const colorTitulo =
    tono === "positivo"
      ? "text-positivo"
      : tono === "atencion"
        ? "text-atencion"
        : "text-ink";

  return (
    <div className="flex flex-col gap-1">
      <h2
        className={`font-display text-cifra-sm font-semibold sm:text-cifra-lg ${colorTitulo}`}
      >
        {titulo}
      </h2>
      {/* Completitud — SIEMPRE visible (sin la cláusula "última carga", retirada
          por el CEO: no se agrega creado_en). */}
      <p className="font-sans text-apoyo text-ink-soft">
        {NombrePeriodo} {rango(idx, p)} {anio} ·{" "}
        {plural(enPeriodo, "factura cargada", "facturas cargadas")}
      </p>
      {/* Honestidad de alcance: la compuerta sigue apagada (CR-E2-COMPUERTA / O-1) */}
      <p className="font-sans text-apoyo text-ink-faint">
        Esta liquidación es informativa: todavía no está incorporada a la
        proyección de caja.
      </p>
    </div>
  );
}
