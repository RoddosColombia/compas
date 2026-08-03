// frontend/src/lib/cierre.ts
//
// Cierre de mes (Sprint 4 backend, UI en C2). Dos pasos:
//   • POST /meses/{mes}/cierre/conciliacion — cierre operativo (compute-only,
//     ciclo:cierre_operativo): devuelve la conciliación sin cambiar estado.
//   • POST /meses/{mes}/cierre/confirmar — confirmar (ciclo:confirmar_cierre,
//     Idempotency-Key obligatoria): congela el mes y re-ancla M+1.
// Precondiciones que impone el backend (el front solo las refleja): mes en
// ejecución, mes siguiente abierto, conciliación dentro del umbral y sin bancos
// "sin dato". Montos como string (regla 1).

import { apiJson } from "@/lib/api";
import type { Conciliacion } from "@/lib/caja";

export interface ConciliacionCierre extends Omit<Conciliacion, "mes"> {
  mes: string; // YYYY-MM
}

export async function cierreConciliacion(
  mes: string, // YYYY-MM
): Promise<ConciliacionCierre> {
  return apiJson(`/meses/${mes}/cierre/conciliacion`, { method: "POST" });
}

export interface ResultadoCierre {
  mes: string;
  estado: string; // "cerrado"
  diferencia: string;
  ajuste_tx_id: string | null;
  saldo_inicial_siguiente: string;
  // CR-WAVA: caja en dos líneas + total (nunca sumado dentro de un banco).
  bancos: string;
  transito_wava: string;
  caja_total: string;
  aviso_transito: string | null;
}

export async function confirmarCierre(
  mes: string,
  idempotencyKey: string, // crypto.randomUUID() — UNA por intento (patrón C1)
  transitoWava = "0", // CR-WAVA: dinero en tránsito (Wava) declarado al cerrar
): Promise<ResultadoCierre> {
  return apiJson(`/meses/${mes}/cierre/confirmar`, {
    method: "POST",
    headers: {
      "Idempotency-Key": idempotencyKey,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ transito_wava: transitoWava }),
  });
}
