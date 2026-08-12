// frontend/src/lib/modelosMoto.ts
//
// CR-COCK: cliente del catálogo administrable de modelos de moto
// (/api/v1/modelos-moto). GET para todos (dashboard:leer); las mutaciones las
// autoriza el backend con proyeccion:gestionar — el front solo esconde controles
// según capacidades (regla 9). Montos como STRING (regla 1); nunca Number.

import { apiJson } from "@/lib/api";

export interface ModeloMoto {
  id: string;
  nombre: string;
  costo_auteco: string;
  precio_venta_con_iva: string;
  cuota_inicial: string;
  cuota_semanal: string;
  plazo_semanas: number;
  matricula: string;
  participacion_mix: string;
  /** PLAN-52: segundo plan de pago opcional (comparte precio/inicial/costo). */
  plan2_plazo_semanas: number | null;
  plan2_cuota_semanal: string | null;
  /** Fracción 0..1 del mix del modelo que va al plan 1; sin plan 2 es "1". */
  peso_plan1: string;
  orden: number;
  activo: boolean;
  es_sistema: boolean;
}

export interface ModeloCrearInput {
  nombre: string;
  costo_auteco: string;
  precio_venta_con_iva: string;
  cuota_inicial: string;
  cuota_semanal: string;
  plazo_semanas: number;
  matricula: string;
  participacion_mix: string;
  plan2_plazo_semanas?: number;
  plan2_cuota_semanal?: string;
  peso_plan1?: string;
}

export interface ModeloEditarInput {
  id: string;
  nombre?: string;
  orden?: number;
  plazo_semanas?: number;
  /** Solo true (reactivar, B-3); la baja va por desactivarModelo. */
  activo?: true;
  costo_auteco?: string;
  precio_venta_con_iva?: string;
  cuota_inicial?: string;
  cuota_semanal?: string;
  matricula?: string;
  participacion_mix?: string;
  plan2_plazo_semanas?: number;
  plan2_cuota_semanal?: string;
  peso_plan1?: string;
  /** PLAN-52: vuelve el modelo a un solo plan (el peso regresa a 1). */
  quitar_plan2?: true;
}

export async function listarModelos(activo?: boolean): Promise<ModeloMoto[]> {
  const qs = activo === undefined ? "" : `?activo=${activo}`;
  return apiJson(`/modelos-moto${qs}`);
}

export async function crearModelo(
  input: ModeloCrearInput,
): Promise<ModeloMoto> {
  return apiJson("/modelos-moto", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export async function editarModelo({
  id,
  ...campos
}: ModeloEditarInput): Promise<ModeloMoto> {
  return apiJson(`/modelos-moto/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(campos),
  });
}

export async function desactivarModelo(id: string): Promise<ModeloMoto> {
  return apiJson(`/modelos-moto/${id}/desactivar`, { method: "POST" });
}

export async function reactivarModelo(id: string): Promise<ModeloMoto> {
  return editarModelo({ id, activo: true });
}
