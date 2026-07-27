// frontend/src/lib/gastosRecurrentes.ts
//
// Plantilla de gastos recurrentes (decisión CEO 2026-07-26): CRUD de
// /api/v1/gastos-recurrentes. Cada gasto apunta a un rubro existente (hereda
// grupo/código del Plan de Cuentas). GET para lectura (dashboard:leer); las
// mutaciones las autoriza el backend con rubros:gestionar (el front solo esconde
// controles, regla 9). Es INFORMATIVO: no toca el motor. Montos como STRING (regla 1).

import { apiFetch, apiJson } from "@/lib/api";

export type Frecuencia =
  | "mensual"
  | "bimestral"
  | "trimestral"
  | "cuatrimestral"
  | "semestral"
  | "anual";

export const FRECUENCIAS: { valor: Frecuencia; label: string }[] = [
  { valor: "mensual", label: "Mensual" },
  { valor: "bimestral", label: "Bimestral" },
  { valor: "trimestral", label: "Trimestral" },
  { valor: "cuatrimestral", label: "Cuatrimestral" },
  { valor: "semestral", label: "Semestral" },
  { valor: "anual", label: "Anual" },
];

export interface GastoRecurrente {
  id: string;
  rubro_id: string;
  rubro_nombre: string | null;
  rubro_grupo: string | null;
  rubro_codigo: string | null;
  descripcion: string;
  monto: string;
  frecuencia: Frecuencia;
  monto_mensual: string;
  dia_pago: number | null;
  /** Mes final YYYY-MM si el gasto es temporal; null = permanente. */
  hasta: string | null;
  notas: string | null;
  activo: boolean;
  orden: number;
}

export interface ResumenGastos {
  total: string;
  por_grupo: Record<string, string>;
}

export interface GastosRespuesta {
  items: GastoRecurrente[];
  resumen: ResumenGastos;
}

export interface GastoCrearInput {
  rubro_id: string;
  descripcion: string;
  monto: string;
  frecuencia: Frecuencia;
  dia_pago?: number | null;
  hasta?: string | null;
  notas?: string | null;
}

export interface GastoEditarInput {
  id: string;
  rubro_id?: string;
  descripcion?: string;
  monto?: string;
  frecuencia?: Frecuencia;
  dia_pago?: number | null;
  hasta?: string | null;
  notas?: string | null;
  activo?: boolean;
}

export async function listarGastos(): Promise<GastosRespuesta> {
  return apiJson("/gastos-recurrentes");
}

export async function crearGasto(
  input: GastoCrearInput,
): Promise<GastoRecurrente> {
  return apiJson("/gastos-recurrentes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export async function editarGasto({
  id,
  ...campos
}: GastoEditarInput): Promise<GastoRecurrente> {
  return apiJson(`/gastos-recurrentes/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(campos),
  });
}

export async function eliminarGasto(id: string): Promise<void> {
  const r = await apiFetch(`/gastos-recurrentes/${id}`, { method: "DELETE" });
  if (!r.ok && r.status !== 204) {
    const body = await r.json().catch(() => ({}));
    throw new Error(body.detail ?? "No se pudo eliminar el gasto");
  }
}

export const GRUPO_LABEL: Record<string, string> = {
  ingresos_operativos: "Ingresos operativos",
  costo_producto: "Costo de producto",
  operacion: "Operación",
  nomina: "Nómina",
  deudas_obligaciones: "Deudas y obligaciones",
  otros: "Otros",
  sin_rubro: "Sin rubro",
};
