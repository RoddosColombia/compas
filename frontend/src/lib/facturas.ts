// frontend/src/lib/facturas.ts
//
// Cliente de facturas de IVA (E2 / PR2). El backend hace TODO el cálculo (regla 1):
// los montos llegan como string → formatCOP; NUNCA Number sobre un monto. Este módulo
// solo transporta. Las tres AUSENCIAS del §5 del spec de diseño se distinguen por
// campo: `tercero_*` = null → "Reservado" (PII restringida); `base_gravable`/`total_bruto`
// = null → "—" (dato que no existe); un "0.00" es cero real.

import { ApiError, apiFetch, apiJson } from "@/lib/api";

export type TipoFactura = "compra" | "venta";
export type TipoContribuyente = "persona_juridica" | "persona_natural";

export interface FacturaRow {
  id: string;
  tipo: TipoFactura;
  origen: string;
  numero: string;
  tercero_nombre: string | null; // null = Reservado (PII, Ley 1581)
  tercero_nit: string | null;
  tipo_contribuyente: TipoContribuyente | null;
  fecha: string; // 'YYYY-MM-DD'
  base_gravable: string | null; // null = — (la DIAN no la trae)
  total_bruto: string | null;
  tarifa_iva: string | null;
  iva_valor: string;
  total: string;
  deducible: boolean;
  activo: boolean;
  periodo: string; // '2026-C2'
}

export async function listarFacturas(activo?: boolean): Promise<FacturaRow[]> {
  const q = activo === undefined ? "" : `?activo=${activo}`;
  return apiJson(`/facturas${q}`);
}

// ── Carga (POST /facturas/cargar, multipart) ──
export type EstadoCarga =
  | "creada"
  | "duplicada"
  | "rechazada_no_dian"
  | "rechazada_tipo_no_soportado"
  | "requiere_confirmacion"
  | "error";

export interface DatosExtraidos {
  tipo_documento: string;
  cufe: string | null;
  numero: string;
  fecha: string;
  tipo: TipoFactura;
  origen: string;
  tercero_nit: string;
  tercero_nombre: string;
  tipo_contribuyente: TipoContribuyente | null;
  base_gravable: string | null;
  total_bruto: string;
  iva_valor: string;
  inc_valor: string;
  bolsas: string;
  otros_impuestos: string;
  total_impuesto: string;
  total_factura: string;
  rete_fuente: string;
  rete_iva: string;
  rete_ica: string;
  coherente: boolean;
}

export interface CargaResultado {
  archivo: string;
  estado: EstadoCarga;
  motivo: string | null;
  factura_id: string | null;
  datos_extraidos: DatosExtraidos | null;
}

export interface CargaRespuesta {
  resultados: CargaResultado[];
  resumen: Record<string, number>;
}

export async function cargarFacturas(files: File[]): Promise<CargaRespuesta> {
  const fd = new FormData();
  for (const f of files) fd.append("archivos", f);
  // NO fijar Content-Type: el navegador pone el boundary del multipart.
  const r = await apiFetch("/facturas/cargar", { method: "POST", body: fd });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) {
    throw new ApiError(r.status, body.detail ?? "No se pudo cargar el lote.");
  }
  return body;
}

// ── Editar deducibilidad / origen (PATCH) ──
export async function editarFactura(
  id: string,
  cambios: { deducible?: boolean; origen?: string },
): Promise<FacturaRow> {
  return apiJson(`/facturas/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cambios),
  });
}

export interface LoteResultado {
  id: string;
  estado: "actualizada" | "sin_cambio" | "error";
  motivo?: string;
}

export interface LoteRespuesta {
  resultados: LoteResultado[];
  resumen: { actualizadas: number; sin_cambio: number; errores: number };
}

/** PATCH /facturas/deducibilidad. OJO: responde 200 aunque TODOS los ids fallen —
 * la verdad está en `resultados`/`resumen`, no en el status. La UI no puede decir
 * "N marcadas" si `resumen.errores > 0`. */
export async function marcarDeducibilidadLote(
  ids: string[],
  deducible: boolean,
): Promise<LoteRespuesta> {
  return apiJson("/facturas/deducibilidad", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids, deducible }),
  });
}

// ── Captura manual (POST /facturas) — la usa la pantalla de confirmación ──
export interface FacturaManualBody {
  tipo: TipoFactura;
  origen: string;
  numero: string;
  tercero_nombre: string;
  tercero_nit: string;
  fecha: string;
  base_gravable: string;
  tarifa_iva: string;
  deducible: boolean;
}

export async function crearFacturaManual(
  body: FacturaManualBody,
): Promise<FacturaRow> {
  return apiJson("/facturas", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}
