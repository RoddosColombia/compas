// frontend/src/lib/rubros.ts
//
// C1 categorías administrables (CR-S4, GO Kimi 9.2/9.4): cliente del CRUD
// /api/v1/rubros. GET para todos los roles (dashboard:leer); las mutaciones las
// autoriza el backend con rubros:gestionar — el front solo esconde botones según
// capacidades (regla 9: nada de mapear rol→UI).

import { apiJson } from "@/lib/api";

export type TipoFlujo = "egreso" | "ingreso";

export interface Rubro {
  id: string;
  grupo: string;
  nombre: string;
  tipo_flujo: TipoFlujo;
  orden: number;
  activo: boolean;
  es_sistema: boolean;
}

export interface RubroCrearInput {
  grupo: string;
  nombre: string;
  tipo_flujo: TipoFlujo;
}

export interface RubroEditarInput {
  id: string;
  nombre?: string;
  orden?: number;
  tipo_flujo?: TipoFlujo;
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

/** Agrupa en los 5 grupos (§1.2), respetando `orden` dentro de cada grupo. */
export function agruparRubros(rubros: Rubro[]): Map<string, Rubro[]> {
  const orden = [
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
