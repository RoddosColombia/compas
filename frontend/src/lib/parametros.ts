// frontend/src/lib/parametros.ts
//
// CR-COCK: cliente de los drivers del motor (/api/v1/parametros-proyeccion).
// GET para todos (dashboard:leer); PUT con proyeccion:gestionar (lo autoriza el
// backend). Montos como STRING (regla 1). El PUT versiona por vigente_desde.

import { ApiError, apiJson } from "@/lib/api";

// Campos monetarios/tasas (string decimal) e íntegros (number). Se listan aquí
// para que el formulario y el guardado compartan una sola definición.
export const PARAMS_MONEY = [
  "caja_inicial",
  "caja_minima",
  "crec_pct_mensual",
  "adelanto_auteco",
  "tasa_auteco",
  "gastos_fijos",
  "gps_moto",
  "costo_moto_nueva",
  "deuda",
  "tasa_deuda",
  "pct_mora",
  "pct_recuperacion",
  "pct_default",
  "pct_provision",
  // SUP-2: fracción del pago de IVA que se prefondea + fondo AVAL (% del recaudo)
  "pct_prefondeo_iva",
  "pct_aval_recaudo",
] as const;

export const PARAMS_INT = [
  "motos_base",
  "horizonte_meses",
  "plazo_auteco_dias",
  "base_auteco_dias",
  "mes_inicio_deuda",
  "meses_deuda",
  // SUP-2: meses de rezago de la recuperación de mora (0 = el mismo mes)
  "meses_rezago_recuperacion",
] as const;

type MoneyKey = (typeof PARAMS_MONEY)[number];
type IntKey = (typeof PARAMS_INT)[number];

// CR-002: componente del desglose de "Costos de alistamiento por moto vendida".
export interface ComponenteAlistamiento {
  nombre: string;
  valor: string; // monto COP como string (regla 1)
  activo: boolean;
  orden: number;
}

export type CamposParametros = { [K in MoneyKey]: string } & {
  [K in IntKey]: number;
} & { componentes_alistamiento: ComponenteAlistamiento[] | null } & {
  /** FIX-L: rampa de colocación por mes (YYYY-MM → unidades enteras ≥0). Default {}. */
  rampa_unidades: Record<string, number>;
  /**
   * SUP-1: segundo tramo de crecimiento. `crec_mes_corte = 18` → los meses 1..18
   * crecen con `crec_pct_mensual` y del 19 en adelante con `crec_pct_mensual_2`.
   * Van JUNTOS; null/null = un solo tramo (comportamiento histórico).
   */
  crec_pct_mensual_2: string | null;
  crec_mes_corte: number | null;
  /**
   * SUP-2: mora y recuperación de los escenarios EXTREMOS (el base son
   * `pct_mora`/`pct_recuperacion`). `null` = sin editar → se conserva el delta en
   * puntos de SUP-1 sobre el preset del escenario.
   */
  pct_mora_pesimista: string | null;
  pct_recuperacion_pesimista: string | null;
  pct_mora_optimista: string | null;
  pct_recuperacion_optimista: string | null;
};

export type Parametros = {
  id: string;
  vigente_desde: string;
  modificado_por: string;
} & CamposParametros;

export type ParametrosInput = {
  vigente_desde: string;
  /** C3: por qué el cambio — viaja a la metadata del audit log (≤300). */
  nota?: string;
} & CamposParametros;

/** Devuelve los parámetros vigentes, o `null` si aún no hay configuración (404). */
export async function obtenerParametros(): Promise<Parametros | null> {
  try {
    return await apiJson<Parametros>("/parametros-proyeccion");
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

export async function guardarParametros(
  input: ParametrosInput,
): Promise<Parametros> {
  return apiJson("/parametros-proyeccion", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

// ── C3 §5.1 — preview compute-only: el impacto ANTES de guardar ──────────────

export async function previewProyeccion(
  parametros: CamposParametros,
  opts: {
    escenario?: string;
    horizonteMeses?: number;
    mesInicio?: string;
  } = {},
): Promise<import("@/lib/proyeccion").Proyeccion> {
  const q = new URLSearchParams();
  if (opts.escenario) q.set("escenario", opts.escenario);
  if (opts.horizonteMeses)
    q.set("horizonte_meses", String(opts.horizonteMeses));
  if (opts.mesInicio) q.set("mes_inicio", opts.mesInicio);
  const qs = q.toString();
  return apiJson(`/proyeccion/preview${qs ? `?${qs}` : ""}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ parametros }),
  });
}

// ── C3 §5.2 — sensibilidad del umbral (tornado) ──────────────────────────────

export interface VariableSensibilidad {
  variable: string;
  etiqueta: string;
  variacion: string;
  piso_base: string;
  piso_mas: string;
  piso_menos: string;
}

export interface Sensibilidad {
  escenario: string;
  horizonte_meses: number;
  piso_base: string;
  variables: VariableSensibilidad[];
}

export async function obtenerSensibilidad(): Promise<Sensibilidad> {
  return apiJson("/proyeccion/sensibilidad");
}
