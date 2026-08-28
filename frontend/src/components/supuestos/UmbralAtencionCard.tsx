// frontend/src/components/supuestos/UmbralAtencionCard.tsx
//
// RF-F3 · P1 — el editor mínimo del umbral de ATENCIÓN. El CEO lo edita en Supuestos.
// Guarda una NUEVA fila en `Configuracion` (historial temporal); no sobrescribe. El
// backend valida > crítico. Botón solo visible con `proyeccion:gestionar` (regla 9).

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { AlertBanner } from "@/components/ui/alert-banner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  escribirUmbralAtencion,
  obtenerUmbralAtencion,
} from "@/lib/configuracion";
import { formatCOP } from "@/lib/money";

export function UmbralAtencionCard({
  puedeGestionar,
}: {
  puedeGestionar: boolean;
}) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["umbral-atencion"],
    queryFn: obtenerUmbralAtencion,
  });
  const [borrador, setBorrador] = useState<string>("");
  const [mensaje, setMensaje] = useState<string | null>(null);

  useEffect(() => {
    if (q.data && !borrador) setBorrador(q.data.atencion);
  }, [q.data, borrador]);

  const guardar = useMutation({
    mutationFn: (valor: string) => escribirUmbralAtencion(valor),
    onSuccess: () => {
      setMensaje(null);
      qc.invalidateQueries({ queryKey: ["umbral-atencion"] });
      // Alerta y valles del cockpit dependen del umbral → recalcularlos.
      qc.invalidateQueries({ queryKey: ["proyeccion"] });
      qc.invalidateQueries({ queryKey: ["valles"] });
    },
    onError: (e: unknown) =>
      setMensaje(e instanceof Error ? e.message : "Error"),
  });

  const cambio = q.data && borrador && borrador !== q.data.atencion;

  return (
    <Card className="flex flex-col gap-3">
      <div>
        <p className="font-display text-seccion font-semibold text-ink">
          Umbral de atención
        </p>
        <p className="text-apoyo text-ink-faint">
          Nivel superior de vigilancia por encima del mínimo (crítico). Cruzarlo
          dispara la lógica de valles y las alertas ámbar.
        </p>
      </div>

      {mensaje && <AlertBanner variant="danger">{mensaje}</AlertBanner>}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <div>
          <div className="text-apoyo uppercase tracking-wide text-ink-faint">
            Crítico (mínimo)
          </div>
          <div className="tabular font-display text-lg font-semibold text-ink">
            {q.data ? formatCOP(q.data.critico) : "—"}
          </div>
        </div>
        <div>
          <div className="text-apoyo uppercase tracking-wide text-ink-faint">
            Atención vigente
          </div>
          <div className="tabular font-display text-lg font-semibold text-atencion">
            {q.data ? formatCOP(q.data.atencion) : "—"}
          </div>
        </div>
        {q.data?.vigente_desde && (
          <div>
            <div className="text-apoyo uppercase tracking-wide text-ink-faint">
              Desde
            </div>
            <div className="tabular font-display text-apoyo text-ink-soft">
              {q.data.vigente_desde}
            </div>
          </div>
        )}
      </div>

      {puedeGestionar && q.data && (
        <div className="flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1">
            <span className="text-apoyo font-medium text-ink-soft">
              Nuevo umbral (COP)
            </span>
            <input
              type="text"
              inputMode="decimal"
              className="tabular w-48 rounded-md border border-hairline bg-surface px-2 py-1.5 font-sans text-cuerpo text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan"
              value={borrador}
              onChange={(e) => setBorrador(e.target.value)}
              aria-label="Nuevo umbral de atención"
            />
          </label>
          <Button
            variant="cyan"
            size="sm"
            disabled={!cambio || guardar.isPending}
            onClick={() => guardar.mutate(borrador)}
          >
            {guardar.isPending ? "Guardando…" : "Guardar"}
          </Button>
          <p className="text-apoyo text-ink-faint">
            Se guarda como nueva vigencia; el historial queda intacto.
          </p>
        </div>
      )}
    </Card>
  );
}
