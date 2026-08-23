// frontend/src/lib/carteraPrevia.ts
//
// SUP-4: la carga semanal del cronograma. El CEO sube el archivo (los lunes) y el
// backend hace todo: agrega la cartera ya originada a la serie semanal del motor y
// deja la rampa del mes en curso en el remanente hacia la meta. Montos como STRING
// (regla 1); el front solo los muestra.

import { ApiError, apiFetch, apiJson } from "@/lib/api";

export interface ResumenCarga {
  creditos: number;
  semanas: number;
  cuotas_futuras: number;
  recaudo_futuro: string;
  vencido_sin_pagar: string;
  creditos_en_mora: number;
  colocaciones_por_mes: Record<string, number>;
  rampa_mes_en_curso: Record<string, number>;
  errores: string[];
}

export interface SerieCartera {
  semanas: number;
  recaudo_total: string;
  detalle: { semana_global: number; recaudo: string; n_activos: number }[];
}

export async function cargarCronograma(file: File): Promise<ResumenCarga> {
  const fd = new FormData();
  fd.append("archivo", file);
  const r = await apiFetch("/cartera-previa/cargar-cronograma", {
    method: "POST",
    body: fd,
  });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) {
    throw new ApiError(
      r.status,
      body.detail ?? "No se pudo cargar el cronograma.",
    );
  }
  return body;
}

export async function obtenerSerieCartera(): Promise<SerieCartera> {
  return apiJson("/cartera-previa/serie");
}
