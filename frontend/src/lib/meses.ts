// frontend/src/lib/meses.ts
//
// Ciclo mensual (Spec §1.3/§2.4). Los montos SIEMPRE como string (regla 1); el
// backend los valida y deriva el saldo del mes anterior (F-14) — el front solo
// pide el saldo inicial cuando NO hay historia (primer mes).

import { apiJson } from "@/lib/api";

export interface SaldoBanco {
  banco: string;
  saldo: string;
  fecha_reporte: string;
}

export interface Mes {
  id: string;
  mes: string; // YYYY-MM-01
  estado: "sugerido" | "propuesto" | "definido" | "en_ejecucion" | "cerrado";
  saldo_inicial_caja: string;
  saldos_banco: SaldoBanco[];
  ingresos_esperados_semana: string | null;
}

export const BANCOS = ["bancolombia", "bbva", "global66"] as const;

export async function listarMeses(): Promise<{ items: Mes[] }> {
  return apiJson("/meses");
}

export interface AbrirMesInput {
  mes: string;
  saldo_inicial_caja?: string | null; // solo primer mes de la historia
  saldos_banco: SaldoBanco[];
}

export async function abrirMes(input: AbrirMesInput): Promise<Mes> {
  return apiJson("/meses", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}
