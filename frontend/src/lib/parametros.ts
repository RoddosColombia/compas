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
] as const;

export const PARAMS_INT = [
  "motos_base",
  "horizonte_meses",
  "plazo_auteco_dias",
  "base_auteco_dias",
  "mes_inicio_deuda",
  "meses_deuda",
] as const;

type MoneyKey = (typeof PARAMS_MONEY)[number];
type IntKey = (typeof PARAMS_INT)[number];

export type Parametros = { id: string; vigente_desde: string } & {
  [K in MoneyKey]: string;
} & { [K in IntKey]: number } & { modificado_por: string };

export type ParametrosInput = { vigente_desde: string } & {
  [K in MoneyKey]: string;
} & { [K in IntKey]: number };

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
