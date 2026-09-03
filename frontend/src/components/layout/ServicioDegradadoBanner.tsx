// F-04 (auditoría 2026-09-02) · Banner "servicio degradado"
//
// Se muestra cuando una query de React Query FALLA con `ApiError` de kind
// `timeout` o `server` (backend degradado / mongo caído). Escucha la
// QueryCache — cero cambios en los consumers.
//
// Auto-oculta después de 20s (o cuando una query nueva triunfa). Aria-live
// para lectores de pantalla.
//
// Diseño intencional: NO ES UN POPUP. Es una barra fija arriba, discreta,
// con acción "Reintentar". Objetivo: convertir un spinner eterno en una
// señal honesta de "el servidor está lento, no la red".

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { ApiError } from "@/lib/api";

const AUTO_OCULTAR_MS = 20_000;

export function ServicioDegradadoBanner() {
  const qc = useQueryClient();
  const [motivo, setMotivo] = useState<"timeout" | "server" | null>(null);

  useEffect(() => {
    const cache = qc.getQueryCache();
    const unsub = cache.subscribe((event) => {
      if (event.type !== "updated") return;
      const err = event.query.state.error;
      if (err instanceof ApiError && (err.kind === "timeout" || err.kind === "server")) {
        setMotivo(err.kind);
      } else if (event.query.state.status === "success") {
        // Una query nueva triunfó → probablemente el server se recuperó.
        setMotivo(null);
      }
    });
    return unsub;
  }, [qc]);

  useEffect(() => {
    if (motivo === null) return;
    const t = setTimeout(() => setMotivo(null), AUTO_OCULTAR_MS);
    return () => clearTimeout(t);
  }, [motivo]);

  if (motivo === null) return null;

  const mensaje =
    motivo === "timeout"
      ? "El servidor está tardando más de lo normal. Reintenta en unos segundos."
      : "El servidor tuvo un error interno. Los datos que ves pueden estar desactualizados.";

  return (
    <div
      role="status"
      aria-live="polite"
      className="border-b border-atencion/40 bg-atencion/10 px-4 py-2 font-sans text-apoyo text-atencion md:px-6"
      data-testid="servicio-degradado-banner"
    >
      <span className="font-semibold">Servicio degradado ·</span> {mensaje}
      <button
        type="button"
        onClick={() => {
          setMotivo(null);
          qc.refetchQueries();
        }}
        className="ml-3 rounded-md border border-atencion/50 px-2 py-0.5 font-medium text-atencion hover:bg-atencion/20"
      >
        Reintentar
      </button>
    </div>
  );
}
