// frontend/src/lib/caja.ts
//
// C4 ajuste diario de caja (CR-S6, GO Kimi PLAN 9.3): cliente del
// PATCH /api/v1/meses/{mes}/saldos. Reporta el saldo disponible por banco sobre el
// mes en ejecución y devuelve la conciliación al instante (D4). Montos SIEMPRE como
// string (regla 1); las guardas (D2 ventana + no-retroceso, D3 estado) viven en el
// backend — aquí solo se muestra su `detail`. Autoriza caja:reportar (regla 9).

import { apiJson } from "@/lib/api";
import type { SaldoBanco } from "@/lib/meses";

export interface ConciliacionBanco {
  banco: string;
  reportado: string;
  calculado: string;
}

export interface Conciliacion {
  mes: string;
  por_banco: ConciliacionBanco[];
  sin_dato: string[];
  consolidado_reportado: string;
  caja_libro: string;
  diferencia: string;
  umbral: string;
  dentro_de_umbral: boolean;
}

export interface ReporteSaldosResultado {
  mes: string;
  saldos_banco: SaldoBanco[];
  conciliacion: Conciliacion;
}

export interface SaldoReporteInput {
  banco: string;
  saldo: string; // string (regla 1)
  fecha_reporte: string; // YYYY-MM-DD
}

export async function reportarSaldos(
  mes: string, // YYYY-MM (la ruta lo normaliza al día 1)
  saldos: SaldoReporteInput[],
): Promise<ReporteSaldosResultado> {
  return apiJson(`/meses/${mes}/saldos`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ saldos }),
  });
}
