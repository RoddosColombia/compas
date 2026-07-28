// frontend/src/lib/proyeccion.ts
//
// COCK-03: cliente del motor de proyección (GET /api/v1/proyeccion). Compute-only;
// el backend calcula todo (motor C7). El front solo presenta. Montos como string
// (regla 1) → formatCOP; NUNCA Number sobre un monto.

import { apiJson } from "@/lib/api";

export type Escenario = "pesimista" | "base" | "optimista";
export type EstadoMes = "ok" | "critico" | "negativo";

export interface MesProyeccion {
  mes: string; // 'YYYY-MM'
  motos: number;
  cartera: number;
  recaudo_credito: string; // Vía 1 (cuota-a-cuota)
  cuotas_iniciales: string; // Vía 2
  ingreso_bruto: string;
  neto: string;
  provision: string; // informativo (P&G/NIIF 9), NO en el flujo (caja veraz)
  gastos_fijos: string;
  gps: string;
  costo_nueva: string;
  adelanto: string;
  pago_inventario: string;
  fondeo: string;
  int_deuda: string;
  iva: string; // egreso de IVA neto en el mes DIAN (≤ 0); 0.00 fuera de ese mes
  egresos: string;
  flujo: string;
  caja: string;
  estado: EstadoMes;
}

// Fondo de provisión de IVA (P1.4): serie informativa mes a mes (NO es flujo del motor).
export interface FondoMes {
  mes: string; // 'YYYY-MM'
  reserva: string; // aporte al fondo ese mes
  pago: string; // salida del fondo (pago DIAN) ese mes
  saldo: string; // saldo acumulado del fondo
}

export interface Proyeccion {
  escenario: string;
  caja_minima: string; // el umbral (para la curva)
  fondo_provision: FondoMes[];
  piso_caja: string;
  mes_mas_ajustado: string;
  meses_bajo_minimo: number;
  caja_final: string;
  capital_requerido: string;
  runway_meses: string | null;
  meses: MesProyeccion[];
  // D2 §4 — reconciliación de obligaciones (Auteco real vs. paramétrico):
  // [desde, hasta] de los meses con facturas reales, o null si no hay facturas.
  ventana_reconciliada: [string, string] | null;
  // interés real de obligaciones por mes de pago (string COP positivo). Es el MISMO
  // interés que ya vive dentro de `fondeo` (Costo) — solo para mostrar, jamás sumar.
  interes_obligaciones: Record<string, string>;
}

export const ESCENARIO_LABEL: Record<Escenario, string> = {
  pesimista: "Pesimista",
  base: "Base",
  optimista: "Optimista",
};

export const ESTADO_LABEL: Record<EstadoMes, string> = {
  ok: "OK",
  critico: "Crítico",
  negativo: "Negativo",
};

export interface ProyeccionParams {
  escenario?: Escenario;
  horizonteMeses?: number;
  mesInicio?: string; // 'YYYY-MM'
}

export async function obtenerProyeccion(
  p: ProyeccionParams = {},
): Promise<Proyeccion> {
  const q = new URLSearchParams();
  if (p.escenario) q.set("escenario", p.escenario);
  if (p.horizonteMeses) q.set("horizonte_meses", String(p.horizonteMeses));
  if (p.mesInicio) q.set("mes_inicio", p.mesInicio);
  const qs = q.toString();
  return apiJson(`/proyeccion${qs ? `?${qs}` : ""}`);
}

// DASH-01: agregación operativa (Dashboards). Cartera activa desglosada por AÑADA
// (cohorte de colocación; 'previa' = los 111 créditos preexistentes) + colocación.
export interface AnadaCartera {
  anada: string; // 'YYYY-MM' | 'previa'
  activos: number;
}

export interface MesOperacion {
  mes: string; // 'YYYY-MM'
  colocacion: number;
  cartera: number;
  por_anada: AnadaCartera[];
}

export interface Operacion {
  escenario: string;
  meses: MesOperacion[];
}

export async function obtenerOperacion(
  p: ProyeccionParams = {},
): Promise<Operacion> {
  const q = new URLSearchParams();
  if (p.escenario) q.set("escenario", p.escenario);
  if (p.horizonteMeses) q.set("horizonte_meses", String(p.horizonteMeses));
  if (p.mesInicio) q.set("mes_inicio", p.mesInicio);
  const qs = q.toString();
  return apiJson(`/proyeccion/operacion${qs ? `?${qs}` : ""}`);
}

// COCK-09: actuals (caja real de bancos) vs proyección + rolling forecast.
export type AnclaModo = "cerrado" | "movimientos";

export interface Comparacion {
  escenario: string;
  ancla_modo: AnclaModo;
  ancla: { mes: string; caja_real: string } | null; // null si no hay mes ancla
  actuals: { mes: string; caja_real: string }[]; // tramo real (histórico)
  forecast: { mes: string; caja: string }[]; // proyección re-anclada
}

export interface ComparacionParams extends ProyeccionParams {
  ancla?: AnclaModo;
}

export async function obtenerComparacion(
  p: ComparacionParams = {},
): Promise<Comparacion> {
  const q = new URLSearchParams();
  if (p.escenario) q.set("escenario", p.escenario);
  if (p.ancla) q.set("ancla", p.ancla);
  if (p.horizonteMeses) q.set("horizonte_meses", String(p.horizonteMeses));
  if (p.mesInicio) q.set("mes_inicio", p.mesInicio);
  const qs = q.toString();
  return apiJson(`/proyeccion/comparar${qs ? `?${qs}` : ""}`);
}
