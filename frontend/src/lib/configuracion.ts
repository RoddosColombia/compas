// frontend/src/lib/configuracion.ts
//
// RF-F3 · P1 — cliente del umbral de ATENCIÓN administrable. GET todos los roles
// (dashboard:leer); PUT solo gestores de proyección. El backend impone la autoridad
// (aquí solo se esconde el editor por capacidad, regla 9).

import { apiJson } from "@/lib/api";

export interface UmbralAtencion {
  critico: string;
  atencion: string;
  vigente_desde?: string;
  modificado_por?: string;
}

export async function obtenerUmbralAtencion(): Promise<UmbralAtencion> {
  return apiJson("/configuracion/umbral-atencion");
}

export async function escribirUmbralAtencion(
  valor: string,
): Promise<UmbralAtencion> {
  return apiJson("/configuracion/umbral-atencion", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ valor }),
  });
}
