// frontend/src/lib/techo.ts
//
// D2 Pieza 0 (arrastre de D1) — cruce de la tarjeta de techo contra el mes en ejecución.
//
// RECONCILIACIÓN §0/§7 (documentada): el `techo` de D1 es el gasto mensual sostenible
// EXTRA sobre la base, no un cupo total. Comparar el ejecutado TOTAL del mes (~$125 M)
// contra ese techo, como sugiere la letra del §0, marcaría siempre crítico. Lo honesto:
// medir el gasto POR ENCIMA del presupuesto aprobado del mes (`ejecutado − definido`)
// contra el techo (ambos son "extra"), y proyectar ese sobre-gasto al cierre con el
// ritmo del calendario (fórmula literal del §0: ejecutado ÷ % de mes transcurrido).
// Montos como string (regla 1); los % no son montos → number.

import { parseMonto } from "@/lib/money";
import Decimal from "decimal.js-light";

const CERO = new Decimal(0);

export type EstadoTecho = "positivo" | "atencion" | "critico";

export interface CruceTecho {
  sobreActual: string; // gasto ya por encima del presupuesto aprobado
  disponibleTecho: string; // techo − sobre actual (headroom sostenible restante)
  pctConsumido: number | null; // sobre actual / techo; null si el techo es 0
  ritmoSobre: string; // proyección del sobre-gasto al cierre del mes (ritmo actual)
  excede: boolean; // el ritmo proyectado supera el techo
  exceso: string; // en cuánto lo supera (0 si no)
  estado: EstadoTecho;
}

export function cruceTecho(
  ejecutado: string,
  definido: string,
  techo: string,
  pctMes: number, // 0..100 (pctMesTranscurrido)
): CruceTecho {
  const eje = parseMonto(ejecutado);
  const def = parseMonto(definido);
  const t = parseMonto(techo);

  const sobreRaw = eje.minus(def);
  const sobre = sobreRaw.isNegative() ? CERO : sobreRaw;

  // ritmo: proyecta el sobre-gasto al 100% del mes al paso actual del calendario.
  const ritmo = pctMes > 0 ? sobre.times(100).div(pctMes) : sobre;

  const disponible = t.minus(sobre);
  const pctConsumido = t.isZero()
    ? null
    : sobre.div(t).times(100).toDecimalPlaces(1).toNumber();

  const excede = ritmo.greaterThan(t);
  const exceso = excede ? ritmo.minus(t) : CERO;

  const estado: EstadoTecho = sobre.isZero()
    ? "positivo"
    : excede
      ? "critico"
      : "atencion";

  return {
    sobreActual: sobre.toFixed(2),
    disponibleTecho: disponible.toFixed(2),
    pctConsumido,
    ritmoSobre: ritmo.toFixed(2),
    excede,
    exceso: exceso.toFixed(2),
    estado,
  };
}
