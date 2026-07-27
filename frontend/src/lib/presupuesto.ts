// frontend/src/lib/presupuesto.ts
//
// Ciclo presupuestal (Spec §1.4, F-06/F-07): sugerido → acotar → aprobar.
// Montos SIEMPRE string (regla 1). `crec_pct` viaja como fracción en string
// ("0.15" = 15 %). Aprobar exige Idempotency-Key (replay seguro §1.12).

import { apiJson } from "@/lib/api";

export interface LineaPresupuesto {
  id: string;
  rubro_id: string;
  version: number;
  monto_sugerido: string;
  prom_3m: string;
  tendencia_mes: string;
  crec_pct: string;
  compromisos_programados: string;
  monto_definido: string | null;
  historia_incompleta: boolean;
  modo_calculo: "historico" | "ventas";
  vigente: boolean;
}

export interface PresupuestoMes {
  mes: string; // YYYY-MM
  lineas: LineaPresupuesto[];
}

export async function generarSugerido(
  mes: string, // YYYY-MM
  crecPct: string, // "0.15"
): Promise<PresupuestoMes> {
  return apiJson(`/meses/${mes}/sugerido`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ crec_pct: crecPct }),
  });
}

export async function listarPresupuesto(mes: string): Promise<PresupuestoMes> {
  return apiJson(`/meses/${mes}/presupuesto`);
}

export async function acotarLinea(
  mes: string,
  rubroId: string,
  montoDefinido: string,
  comentario?: string,
): Promise<LineaPresupuesto> {
  return apiJson(`/meses/${mes}/presupuesto/${rubroId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      monto_definido: montoDefinido,
      ...(comentario ? { comentario } : {}),
    }),
  });
}

export interface ResultadoAprobar {
  mes: string;
  estado: string; // "en_ejecucion"
  lineas: number;
}

export async function aprobarPresupuesto(
  mes: string,
  idempotencyKey: string, // crypto.randomUUID() — UNA por intento de aprobación
): Promise<ResultadoAprobar> {
  return apiJson(`/meses/${mes}/presupuesto/aprobar`, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
  });
}
