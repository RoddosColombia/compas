// frontend/src/lib/rubros.ts
//
// C1 categorías administrables (CR-S4, GO Kimi 9.2/9.4): cliente del CRUD
// /api/v1/rubros. GET para todos los roles (dashboard:leer); las mutaciones las
// autoriza el backend con rubros:gestionar — el front solo esconde botones según
// capacidades (regla 9: nada de mapear rol→UI).

import { apiJson } from "@/lib/api";

export type TipoFlujo = "egreso" | "ingreso";
export type TipoRubro = "fijo" | "variable";

export interface Rubro {
  id: string;
  grupo: string;
  nombre: string;
  tipo_flujo: TipoFlujo;
  /** Código jerárquico del plan de cuentas (p. ej. "2070"); null si no aplica. */
  codigo: string | null;
  /** Fijo/Variable — rigor del gasto (ARQUITECTURA_PRESUPUESTAL); null en sistema. */
  tipo: TipoRubro | null;
  orden: number;
  activo: boolean;
  es_sistema: boolean;
}

export interface RubroCrearInput {
  grupo: string;
  nombre: string;
  tipo_flujo: TipoFlujo;
  // RF-F9 · Fundacional §2 — Plan de cuentas completo: código contable + clase
  // (Fijo/Variable) son obligatorios al crear. El backend rechaza el POST sin
  // ellos (RubroCrearBody). Rubros previos sin código NO se tocan.
  codigo: string;
  tipo: TipoRubro;
}

export interface RubroEditarInput {
  id: string;
  nombre?: string;
  orden?: number;
  tipo_flujo?: TipoFlujo;
  codigo?: string;
  tipo?: TipoRubro;
  /** Solo true (reactivar, B-3); la baja va por desactivarRubro. */
  activo?: true;
}

export async function listarRubros(): Promise<Rubro[]> {
  return apiJson("/rubros");
}

export async function crearRubro(input: RubroCrearInput): Promise<Rubro> {
  return apiJson("/rubros", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export async function editarRubro({
  id,
  ...campos
}: RubroEditarInput): Promise<Rubro> {
  return apiJson(`/rubros/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(campos),
  });
}

export async function desactivarRubro(id: string): Promise<Rubro> {
  return apiJson(`/rubros/${id}/desactivar`, { method: "POST" });
}

export async function reactivarRubro(id: string): Promise<Rubro> {
  return editarRubro({ id, activo: true });
}

/** Agrupa en los 6 grupos del plan de cuentas, respetando `orden` en cada uno. */
export function agruparRubros(rubros: Rubro[]): Map<string, Rubro[]> {
  const orden = [
    "ingresos_operativos",
    "costo_producto",
    "operacion",
    "nomina",
    "deudas_obligaciones",
    "otros",
  ];
  const out = new Map<string, Rubro[]>();
  for (const g of orden) {
    const filas = rubros
      .filter((r) => r.grupo === g)
      .sort((a, b) => a.orden - b.orden);
    if (filas.length > 0) out.set(g, filas);
  }
  return out;
}
