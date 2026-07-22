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
  sin_presupuesto: SinPresupuesto[];
}

// Etiquetas de presentación de los 5 grupos (§1.2).
export const GRUPO_LABEL: Record<string, string> = {
  costo_producto: "Costo de producto",
  operacion: "Operación",
  nomina: "Nómina",
  deudas_obligaciones: "Deudas y obligaciones",
  otros: "Otros",
};

export async function vistaControl(mes: string): Promise<VistaControl> {
  // `mes` en formato YYYY-MM (la ruta lo normaliza al día 1).
  return apiJson(`/meses/${mes}/control`);
}
