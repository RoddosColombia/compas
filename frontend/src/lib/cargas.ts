// frontend/src/lib/cargas.ts
//
// Tipos y llamadas de la pantalla de cargas (Spec §1.6, F-22, US-10).
// Validación de archivo en cliente = espejo de F-22 (el backend re-valida).

import { ApiError, apiFetch, apiJson } from "@/lib/api";

export interface ErrorCarga {
  fila: number;
  motivo: string;
  valor_crudo: string | null;
}

export interface Carga {
  id: string;
  banco: string;
  archivo_nombre: string;
  estado: "procesando" | "completada" | "fallida";
  total_filas: number;
  nuevas: number;
  duplicadas: number;
  errores: number;
  motivo_fallo: string | null;
  created_at: string;
  errores_detalle?: ErrorCarga[];
}

export interface ListaCargas {
  items: Carga[];
  next_cursor: string | null;
}

export const MAX_BYTES = 10 * 1024 * 1024; // F-22
const EXT_OK = [".xlsx", ".xls"];

/** F-22 en cliente: null si es válido, mensaje si no. */
export function validarArchivo(nombre: string, bytes: number): string | null {
  const ext = nombre.slice(nombre.lastIndexOf(".")).toLowerCase();
  if (ext === ".xlsm") return "Archivos .xlsm (con macros) no se aceptan.";
  if (!EXT_OK.includes(ext))
    return `Extensión '${ext}' no soportada; solo .xlsx/.xls.`;
  if (bytes > MAX_BYTES) return "El extracto supera el límite de 10 MB.";
  return null;
}

export async function listarCargas(cursor?: string): Promise<ListaCargas> {
  const q = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
  return apiJson(`/cargas${q}`);
}

export async function detalleCarga(id: string): Promise<Carga> {
  return apiJson(`/cargas/${id}`);
}

export async function subirExtracto(archivo: File): Promise<Carga> {
  const fd = new FormData();
  fd.append("archivo", archivo);
  const r = await apiFetch("/cargas", { method: "POST", body: fd });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) {
    const detail =
      typeof body.detail === "string"
        ? body.detail
        : "Error subiendo el extracto";
    throw new ApiError(r.status, detail);
  }
  return body as Carga;
}

export interface TransaccionManualInput {
  fecha: string;
  descripcion: string;
  valor: string; // string SIEMPRE (regla 1)
  tipo_flujo: "egreso" | "ingreso";
  rubro_id?: string | null;
}

export async function crearTransaccionManual(
  input: TransaccionManualInput,
  idempotencyKey: string,
): Promise<{ id: string; id_banco: string; valor: string }> {
  return apiJson("/transacciones", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": idempotencyKey,
    },
    body: JSON.stringify(input),
  });
}

// FIX-G2: transacciones del mes (panel de manuales). `anulada` = ya tiene su
// contra-asiento; `es_reverso` = es un contra-asiento (enlaza al original por
// revierte_id). Montos string (regla 1).
export interface TransaccionMovimiento {
  id: string;
  fecha: string;
  descripcion: string;
  valor: string;
  tipo_flujo: "egreso" | "ingreso";
  rubro_id: string;
  banco: string;
  id_banco: string;
  revierte_id: string | null;
  anulada: boolean;
  es_reverso: boolean;
}

export async function listarTransaccionesManuales(
  mes: string,
): Promise<{ items: TransaccionMovimiento[] }> {
  return apiJson(`/transacciones?banco=manual&mes=${encodeURIComponent(mes)}`);
}

export async function anularTransaccion(
  id: string,
  motivo: string,
): Promise<TransaccionMovimiento> {
  return apiJson(`/transacciones/${id}/anular`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ motivo }),
  });
}
