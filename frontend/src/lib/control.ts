// frontend/src/lib/control.ts
//
// Vista Control (Sprint 4): presupuesto definido vs ejecutado vs disponible por
// rubro, con semáforo. Todo cálculo viene del backend (Spec §17); el front solo
// presenta. Montos como string (regla 1) → formatCOP.

import { apiJson } from "@/lib/api";

export type Semaforo = "verde" | "amarillo" | "rojo";

export interface ControlLinea {
  rubro_id: string;
  rubro: string;
  definido: string;
  ejecutado: string;
  disponible: string;
  pct_ejecutado: string | null; // null si definido == 0
  semaforo: Semaforo;
}

export interface ControlSubtotal {
  definido: string;
  ejecutado: string;
  disponible: string;
}

export interface ControlGrupo {
  grupo: string;
  lineas: ControlLinea[];
  subtotal: ControlSubtotal;
}

export interface SinPresupuesto {
  rubro: string;
  ejecutado: string;
}

export interface VistaControl {
  mes: string;
  estado: string;
  grupos: ControlGrupo[];
  total: ControlSubtotal;
  caja_disponible: string;
  // CR-WAVA (aditivo, opcional para compat): caja en dos líneas + total.
  caja_disponible_bancos?: string;
  transito_remanente?: string;
  caja_disponible_total?: string;
  sin_presupuesto: SinPresupuesto[];
}

// Etiquetas de presentación de los 6 grupos del plan de cuentas
// (ARQUITECTURA_PRESUPUESTAL: 0000 ingresos → 5000 otros).
export const GRUPO_LABEL: Record<string, string> = {
  ingresos_operativos: "Ingresos operativos",
  costo_producto: "Costo de producto",
  operacion: "Operación",
  nomina: "Nómina",
  deudas_obligaciones: "Deudas y obligaciones",
  otros: "Otros y varios",
};

export async function vistaControl(mes: string): Promise<VistaControl> {
  // `mes` en formato YYYY-MM (la ruta lo normaliza al día 1).
  return apiJson(`/meses/${mes}/control`);
}

// ── C5: vista combinada categoría × cuenta ──────────────────────────────────

export interface ControlCuentaLinea {
  rubro_id: string;
  rubro: string;
  por_banco: Record<string, string>; // banco → ejecutado (string, regla 1)
  total: string;
}

export interface ControlCuentaGrupo {
  grupo: string;
  lineas: ControlCuentaLinea[];
  subtotal: { por_banco: Record<string, string>; total: string };
}

export interface ControlPorCuenta {
  mes: string;
  estado: string;
  bancos: string[]; // columnas presentes
  grupos: ControlCuentaGrupo[];
  total: { por_banco: Record<string, string>; total: string };
  sin_presupuesto: { rubro: string; por_banco: Record<string, string> }[];
}

export async function vistaControlPorCuenta(
  mes: string,
): Promise<ControlPorCuenta> {
  return apiJson(`/meses/${mes}/control/por-cuenta`);
}

// Etiquetas de presentación de los bancos.
export const BANCO_LABEL: Record<string, string> = {
  bancolombia: "Bancolombia",
  bbva: "BBVA",
  global66: "Global66",
  manual: "Manual",
};
