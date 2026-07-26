// frontend/src/lib/iva.ts
//
// C11: cliente de la liquidación de IVA (GET /api/v1/facturas/liquidacion). El backend
// liquida (generado − descontable con arrastre de saldo a favor) según la periodicidad
// configurable (cuatrimestral por defecto; bimestral cuando la DIAN lo exija). Montos
// como string (regla 1) → formatCOP; NUNCA Number sobre un monto. El front solo presenta.

import { apiJson } from "@/lib/api";

export type Periodicidad = "cuatrimestral" | "bimestral";

export interface PeriodoIva {
  anio: number;
  periodo: number; // índice del período (1..3 cuatrimestral | 1..6 bimestral)
  etiqueta: string; // '2026-C1' | '2026-B1'
  generado: string;
  descontable: string;
  saldo: string;
  saldo_favor_previo: string;
  neto_a_pagar: string;
  saldo_favor_nuevo: string;
}

export interface LiquidacionIva {
  periodicidad: Periodicidad;
  periodos: PeriodoIva[];
}

export const PERIODICIDAD_LABEL: Record<Periodicidad, string> = {
  cuatrimestral: "Cuatrimestral",
  bimestral: "Bimestral",
};

export async function obtenerLiquidacionIva(): Promise<LiquidacionIva> {
  return apiJson("/facturas/liquidacion");
}
