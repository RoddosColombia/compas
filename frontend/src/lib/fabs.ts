// Cliente de FABS (chat embebido). Los montos llegan como string YA formateado
// es-CO dentro del texto — NUNCA hacer Number sobre ellos (regla 1).
import { apiJson } from "@/lib/api";

export interface CifraFabs {
  valor: string;
  unidad: string;
  evidencia: { fuente: string; ref: string };
}

export interface RespuestaFabs {
  texto: string;
  abstuvo: boolean;
  cifras: CifraFabs[];
}

export interface TurnoHistorial {
  rol: "user" | "assistant";
  texto: string;
  canal: string;
  ts: string | null;
}

export function historialFabs(): Promise<TurnoHistorial[]> {
  return apiJson<TurnoHistorial[]>("/cfo/historial");
}

export function preguntarFabs(pregunta: string): Promise<RespuestaFabs> {
  return apiJson<RespuestaFabs>("/cfo", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pregunta }),
  });
}
