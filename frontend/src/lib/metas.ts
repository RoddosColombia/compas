// frontend/src/lib/metas.ts
//
// Metas de ingreso (D2 §6, CR-D2) — INFORMATIVAS: no tocan el motor ni la caja.
// CRUD de /api/v1/metas-ingreso. GET para lectura (dashboard:leer); las mutaciones
// las autoriza el backend con proyeccion:gestionar (el front solo esconde controles,
// regla 9). `real_ejecutado` ya viene con la exclusión de rubros neutros. Montos como
// STRING (regla 1); el % de cumplimiento lo calcula el backend (null si meta 0/ausente).

import { apiFetch, apiJson } from "@/lib/api";

export interface LineaMeta {
  nombre: string;
  valor: string;
}

export interface Meta {
  id: string;
  mes: string; // YYYY-MM
  valor: string; // meta del mes
  lineas: LineaMeta[];
  real_ejecutado: string | null; // Σ ingresos del mes, excluidos los neutros
  pct_cumplimiento: string | null; // null si meta 0/ausente
  activo: boolean;
}

export interface MetasRespuesta {
  items: Meta[];
}

export interface MetaCrearInput {
  mes: string; // YYYY-MM
  valor: string;
  lineas?: LineaMeta[];
}

export interface MetaEditarInput {
  id: string;
  valor?: string;
  lineas?: LineaMeta[];
}

export async function listarMetas(): Promise<MetasRespuesta> {
  return apiJson("/metas-ingreso");
}

export async function crearMeta(input: MetaCrearInput): Promise<Meta> {
  return apiJson("/metas-ingreso", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export async function editarMeta({
  id,
  ...campos
}: MetaEditarInput): Promise<Meta> {
  return apiJson(`/metas-ingreso/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(campos),
  });
}

export async function eliminarMeta(id: string): Promise<void> {
  const r = await apiFetch(`/metas-ingreso/${id}`, { method: "DELETE" });
  if (!r.ok && r.status !== 204) {
    const body = await r.json().catch(() => ({}));
    throw new Error(body.detail ?? "No se pudo eliminar la meta");
  }
}
