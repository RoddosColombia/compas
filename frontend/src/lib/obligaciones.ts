// frontend/src/lib/obligaciones.ts
//
// Obligaciones + facturas (D2 §2/§7, CR-D2). GET con dashboard:leer; las mutaciones
// las autoriza el backend con proyeccion:gestionar (el front solo esconde controles,
// regla 9). Montos como STRING (regla 1). Pago con distinción de origen: `roddos` sale
// de caja; `tercero` baja la deuda sin tocar la caja de RODDOS (la reconciliación lo
// excluye). Modelo full: un pago marca la factura pagada.

import { apiFetch, apiJson } from "@/lib/api";

export type NaturalezaObligacion = "cuotas" | "facturacion";
export type OrigenPago = "roddos" | "tercero";
export type EstadoFactura = "pendiente" | "pagada";

export interface Obligacion {
  id: string;
  nombre: string;
  acreedor: string;
  naturaleza: NaturalezaObligacion;
  activo: boolean;
  es_sistema: boolean;
  actualizado_at: string;
  saldo_pendiente: string | null; // Σ valor de facturas sin pagar (facturación)
  plazo_base_dias?: number | null;
  plazo_max_dias?: number | null;
  tasa_excedente_mensual?: string | null;
}

export interface FacturaObligacion {
  id: string;
  obligacion_id: string;
  numero: string | null;
  fecha_factura: string; // YYYY-MM-DD
  valor: string;
  plazo_elegido_dias: number;
  nota: string | null;
  activo: boolean;
  estado: EstadoFactura;
  pagada_desde: OrigenPago | null;
  pagada_at: string | null;
  pagada_valor: string | null;
  pagada_nota: string | null;
}

export interface FacturaCrearInput {
  numero?: string;
  fecha_factura: string;
  valor: string;
  plazo_elegido_dias: number;
  nota?: string;
}

export interface PagoInput {
  fecha: string;
  valor: string;
  pagada_desde: OrigenPago;
  nota?: string;
}

export async function listarObligaciones(): Promise<{ items: Obligacion[] }> {
  return apiJson("/obligaciones?activo=true");
}

export async function listarFacturas(
  obligacionId: string,
): Promise<{ items: FacturaObligacion[] }> {
  return apiJson(`/obligaciones/${obligacionId}/facturas`);
}

export async function registrarFactura(
  obligacionId: string,
  input: FacturaCrearInput,
): Promise<FacturaObligacion> {
  return apiJson(`/obligaciones/${obligacionId}/facturas`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export async function anularFactura(facturaId: string): Promise<void> {
  const r = await apiFetch(`/obligaciones/facturas/${facturaId}`, {
    method: "DELETE",
  });
  if (!r.ok && r.status !== 204) {
    const body = await r.json().catch(() => ({}));
    throw new Error(body.detail ?? "No se pudo anular la factura");
  }
}

export async function registrarPago(
  obligacionId: string,
  facturaId: string,
  input: PagoInput,
): Promise<FacturaObligacion> {
  return apiJson(`/obligaciones/${obligacionId}/facturas/${facturaId}/pagar`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export async function anularPago(
  obligacionId: string,
  facturaId: string,
): Promise<FacturaObligacion> {
  return apiJson(`/obligaciones/${obligacionId}/facturas/${facturaId}/pagar`, {
    method: "DELETE",
  });
}

// RF-F8 · Fundacional §2 — "Negocia esta deuda" (simulación compute-only).
// El backend NO escribe: solo devuelve el impacto que TENDRÍA la renegociación.
// La persistencia queda para CR-RF-F8-B (necesita evento audit nuevo aprobado).
export interface ValleResumen {
  mes: string; // YYYY-MM
  caja: string; // COP
}

export interface SimulacionNegociacion {
  piso_actual: string;
  piso_negociado: string;
  delta_piso: string; // negociado - actual; positivo = mejora el piso
  mes_pago_actual: string; // YYYY-MM
  mes_pago_negociado: string;
  valles_actuales: ValleResumen[];
  valles_negociados: ValleResumen[];
}

export async function simularNegociacion(
  obligacionId: string,
  facturaId: string,
  input: {
    plazo_elegido_dias_nuevo?: number;
    fecha_factura_nueva?: string;
  },
): Promise<SimulacionNegociacion> {
  return apiJson(
    `/obligaciones/${obligacionId}/facturas/${facturaId}/simular`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    },
  );
}

// Mes de pago derivado (D2 §4): fecha_factura + plazo//30 meses. Solo para mostrar;
// la reconciliación del backend es la fuente de verdad de la caja.
export function mesDePago(fechaFactura: string, plazoDias: number): string {
  const [y, m] = fechaFactura.split("-").map((n) => Number.parseInt(n, 10));
  if (!Number.isFinite(y) || !Number.isFinite(m)) return "—";
  const meses = Math.floor(plazoDias / 30);
  const total = y * 12 + (m - 1) + meses;
  const yy = Math.floor(total / 12);
  const mm = (total % 12) + 1;
  return `${yy}-${String(mm).padStart(2, "0")}`;
}
