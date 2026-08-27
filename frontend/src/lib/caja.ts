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

// ── FIX-F: editar el saldo inicial de caja de un mes en ejecución ────────────
// PATCH /meses/{mes}/saldo-inicial (ciclo:config + step-up MFA en el backend). Cambio
// sensible de dinero → exige motivo; queda auditado (saldo_inicial.editado + saga O1).
export interface SaldoInicialResultado {
  mes: string;
  estado: string;
  saldo_inicial_caja: string;
}

export async function editarSaldoInicial(
  mes: string, // YYYY-MM
  saldoInicialCaja: string,
  motivo: string,
): Promise<SaldoInicialResultado> {
  return apiJson(`/meses/${mes}/saldo-inicial`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ saldo_inicial_caja: saldoInicialCaja, motivo }),
  });
}

// ── Flujo de caja DIARIO (GET /api/v1/caja/diaria) ──────────────────────────
// Evolución día a día del dinero para administrar el flujo de caja. Lee las
// transacciones reales (no depende del motor ni del ciclo presupuestal). Montos
// como string (regla 1) → formatCOP; el front solo presenta.

export interface DiaCaja {
  fecha: string; // YYYY-MM-DD
  ingresos: string;
  egresos: string;
  flujo: string; // ingresos - egresos del día
  caja: string; // saldo corriendo
  n: number; // nº de movimientos del día
}

export interface CajaDiaria {
  desde: string;
  hasta: string;
  caja_inicial: string;
  total_ingresos: string;
  total_egresos: string;
  flujo_neto: string;
  caja_final: string;
  dias: DiaCaja[];
}

export function obtenerCajaDiaria(params: {
  desde: string;
  hasta: string;
  cajaInicial?: string;
}): Promise<CajaDiaria> {
  const q = new URLSearchParams({
    desde: params.desde,
    hasta: params.hasta,
    caja_inicial: params.cajaInicial ?? "0",
  });
  return apiJson(`/caja/diaria?${q.toString()}`);
}

// Saldo disponible EN VIVO (CEO 2026-08-24): el número fijo que se actualiza cada vez
// que se cargan movimientos. Lectura pura; montos como string (regla 1). El backend
// reusa la conciliación del cierre (misma verdad) y agrega la frescura.

export interface SaldoBancoVivo {
  banco: string;
  saldo: string; // == calculado de la conciliación
  reportado: string;
  ultimo_movimiento: string | null; // 'YYYY-MM-DD'
  dias_sin_registrar: number | null;
}

export interface Frescura {
  ultimo_movimiento: string | null;
  dias: number | null;
  estado: "al_dia" | "atrasado" | "sin_movimientos";
}

export interface SaldoDisponible {
  disponible: boolean;
  motivo?: string; // 'sin_mes_en_ejecucion' cuando disponible=false
  mes?: string;
  corte?: string;
  saldo_en_banco?: string;
  transito_wava?: string;
  total?: string;
  por_banco?: SaldoBancoVivo[];
  sin_dato?: string[];
  frescura?: Frescura;
}

export function obtenerSaldoDisponible(): Promise<SaldoDisponible> {
  return apiJson("/caja/disponible");
}
