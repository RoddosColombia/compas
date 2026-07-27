// Cargando — skeleton del sistema F1 §5 (nada de "Cargando…" a secas).
// El mensaje de cold-start de Render vive en App (Protegida) y se conserva.

import { cn } from "@/lib/utils";

export function Cargando({
  variante = "card",
  className,
}: {
  /** kpis = fila de 4 baldosas; card = bloque; tabla = filas. */
  variante?: "kpis" | "card" | "tabla";
  className?: string;
}) {
  if (variante === "kpis") {
    return (
      <output
        aria-label="Cargando indicadores"
        className={cn(
          "grid animate-pulse grid-cols-2 gap-5 md:grid-cols-4",
          className,
        )}
      >
        {[0, 1, 2, 3].map((i) => (
          <div
            key={i}
            className="h-28 rounded-xl border border-hairline bg-surface-muted"
          />
        ))}
      </output>
    );
  }
  if (variante === "tabla") {
    return (
      <output
        aria-label="Cargando tabla"
        className={cn("flex animate-pulse flex-col gap-2", className)}
      >
        {[0, 1, 2, 3, 4].map((i) => (
          <div key={i} className="h-10 rounded-md bg-surface-muted" />
        ))}
      </output>
    );
  }
  return (
    <output
      aria-label="Cargando"
      className={cn(
        "block h-48 animate-pulse rounded-xl border border-hairline bg-surface-muted",
        className,
      )}
    />
  );
}
