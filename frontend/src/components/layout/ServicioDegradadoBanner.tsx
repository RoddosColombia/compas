// Banner "servicio degradado" · F-04 (2026-09-02), corregido 2026-09-03.
//
// Escucha la QueryCache y avisa cuando el backend no está respondiendo bien.
// Cero cambios en los consumers.
//
// POR QUÉ SE CORRIGIÓ (incidente "todo en blanco", 2026-09-03):
//   1. Solo reaccionaba a `timeout` y `server`. El modo de falla real era
//      `unauthorized` (401): el refresh moría, `accessToken` quedaba en null y
//      TODAS las queries daban 401 — sin banner, sin redirección, y con las
//      páginas renderizando nada. El usuario veía la app vacía sin una sola
//      pista de por qué.
//   2. Se auto-ocultaba a los 20s. Con un backend caído de verdad, eso es
//      peor que no avisar: aparece, desaparece, y vuelve el misterio. Ahora
//      solo desaparece cuando una query VUELVE A FUNCIONAR — la señal dura
//      lo que dura el problema.
//
// Sigue sin ser un popup: barra fija arriba, discreta, con acción.

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError, type ApiErrorKind, haySesion } from "@/lib/api";

type Motivo = Exclude<ApiErrorKind, "client">;

const MENSAJES: Record<Motivo, string> = {
  timeout:
    "El servidor está tardando más de lo normal. Si estuvo inactivo un rato, puede estar despertando (hasta ~1 min).",
  server:
    "El servidor tuvo un error interno. Los datos que ves pueden estar desactualizados.",
  network: "No hay conexión con el servidor de COMPAS.",
  unauthorized:
    "Tu sesión venció y no se pudo renovar, así que las pantallas no pueden cargar datos.",
};

export function ServicioDegradadoBanner() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [motivo, setMotivo] = useState<Motivo | null>(null);

  useEffect(() => {
    const cache = qc.getQueryCache();
    const unsub = cache.subscribe((event) => {
      if (event.type !== "updated") return;
      const err = event.query.state.error;
      if (err instanceof ApiError && err.kind !== "client") {
        setMotivo(err.kind);
      } else if (event.query.state.status === "success") {
        // Una query volvió a funcionar → el servicio se recuperó de verdad.
        setMotivo(null);
      }
    });
    return unsub;
  }, [qc]);

  if (motivo === null) return null;

  const sesionPerdida = motivo === "unauthorized" && !haySesion();

  // <output> ya expone role="status" implícitamente — elemento semántico en vez
  // de un div con role (biome a11y/useSemanticElements).
  return (
    <output
      aria-live="polite"
      className="block border-b border-atencion/40 bg-atencion/10 px-4 py-2 font-sans text-apoyo text-atencion md:px-6"
      data-testid="servicio-degradado-banner"
    >
      <span className="font-semibold">
        {sesionPerdida ? "Sesión perdida ·" : "Servicio degradado ·"}
      </span>{" "}
      {MENSAJES[motivo]}
      {sesionPerdida ? (
        <button
          type="button"
          onClick={() => navigate("/login")}
          className="ml-3 rounded-md border border-atencion/50 px-2 py-0.5 font-medium text-atencion hover:bg-atencion/20"
        >
          Volver a entrar
        </button>
      ) : (
        <button
          type="button"
          onClick={() => {
            setMotivo(null);
            void qc.refetchQueries();
          }}
          className="ml-3 rounded-md border border-atencion/50 px-2 py-0.5 font-medium text-atencion hover:bg-atencion/20"
        >
          Reintentar
        </button>
      )}
    </output>
  );
}
