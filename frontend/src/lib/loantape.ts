// frontend/src/lib/loantape.ts
//
// Aging SISMO-V3: lectura de la mora por tramo (GET /loantape/aging) y carga del
// LoanTape semanal (POST /loantape/carga, multipart). El backend deriva el aging del
// último corte; el front solo presenta. Montos como string (regla 1) -> formatCOP.

import { ApiError, apiFetch, apiJson } from "@/lib/api";

export interface TramoAging {
  tramo: string; // al_dia | 1_30 | 31_60 | 61_90 | 90_mas
  etiqueta: string;
  n_creditos: number;
  saldo_en_mora: string;
}

export interface Aging {
  fecha_corte: string | null; // null si no hay LoanTape cargado
  tramos: TramoAging[];
}

export function obtenerAging(): Promise<Aging> {
  return apiJson("/loantape/aging");
}

export async function cargarLoantape(
  archivo: File,
): Promise<{ cargados: number }> {
  const fd = new FormData();
  fd.append("archivo", archivo);
  const r = await apiFetch("/loantape/carga", { method: "POST", body: fd });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) {
    const detail =
      typeof body.detail === "string"
        ? body.detail
        : "Error cargando el LoanTape";
    throw new ApiError(r.status, detail);
  }
  return body as { cargados: number };
}
