// frontend/src/lib/reglas.ts
//
// C3 auto-clasificación (CR-S5, GO Kimi 9.3/9.4): cliente del CRUD
// /api/v1/reglas-clasificacion. GET para todos los roles (dashboard:leer); las
// mutaciones las autoriza el backend con reglas:gestionar — el front solo esconde
// botones según capacidades (regla 9). Las guardas de dominio (D1 coherencia de
// tipos, unicidad de patrón activo, B-1 revalidación al activar) viven en el
// backend; aquí solo se muestra su `detail`.

import { apiJson } from "@/lib/api";
import type { TipoFlujo } from "@/lib/rubros";

export interface Regla {
  id: string;
  patron: string;
  patron_normalizado: string;
  rubro_id: string;
  tipo_flujo: TipoFlujo;
  prioridad: number;
  origen: "manual" | "aprendida";
  activa: boolean;
  creada_por: string;
}

export interface ReglaCrearInput {
  patron: string;
  rubro_id: string;
  tipo_flujo: TipoFlujo;
  prioridad: number;
}

export interface ReglaEditarInput {
  id: string;
  patron?: string;
  prioridad?: number;
  rubro_id?: string;
  /** Solo true (reactivar, B-3); la baja va por desactivarRegla. */
  activa?: true;
}

export interface ResultadoAplicar {
  clasificadas: number;
  sin_match: number;
  /** B-1 I-PR1 (simetría D2): reglas activas cuyo rubro está inactivo. */
  reglas_con_rubro_inactivo: string[];
}

export async function listarReglas(): Promise<Regla[]> {
  return apiJson("/reglas-clasificacion");
}

export async function crearRegla(input: ReglaCrearInput): Promise<Regla> {
  return apiJson("/reglas-clasificacion", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export async function editarRegla({
  id,
  ...campos
}: ReglaEditarInput): Promise<Regla> {
  return apiJson(`/reglas-clasificacion/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(campos),
  });
}

export async function desactivarRegla(id: string): Promise<Regla> {
  return apiJson(`/reglas-clasificacion/${id}/desactivar`, { method: "POST" });
}

export async function reactivarRegla(id: string): Promise<Regla> {
  return editarRegla({ id, activa: true });
}

export async function aprobarRegla(id: string): Promise<Regla> {
  return apiJson(`/reglas-clasificacion/${id}/aprobar`, { method: "POST" });
}

export async function aplicarPendientes(): Promise<ResultadoAplicar> {
  return apiJson("/reglas-clasificacion/aplicar-pendientes", {
    method: "POST",
  });
}
