// KpiTile — baldosa de KPI del cockpit (Blueprint §3).
// Etiqueta discreta (Raleway) sobre cifra protagonista (Montserrat, tabular-nums).
// El backend ya entrega la cifra formateada; aquí solo se presenta.

import { cn } from "@/lib/utils";

export interface KpiDelta {
  texto: string;
  tono: "sube" | "baja";
}

export interface KpiTileProps {
  label: string;
  value: string;
  sub?: string;
  delta?: KpiDelta;
  /** `peligro` pinta la cifra en rojo (reservado a perforación de caja / negativos). */
  tono?: "neutro" | "peligro";
  className?: string;
}

export function KpiTile({
  label,
  value,
  sub,
  delta,
  tono = "neutro",
  className,
}: KpiTileProps) {
  return (
    <div
      className={cn(
        "rounded-xl border border-hairline bg-surface p-4 shadow-sm",
        className,
      )}
    >
      <p className="font-sans text-xs font-medium tracking-wide text-ink-faint uppercase">
        {label}
      </p>
      <p
        className={cn(
          "tabular mt-1.5 font-display text-2xl font-bold",
          tono === "peligro" ? "text-red" : "text-ink",
        )}
      >
        {value}
      </p>
      {(sub || delta) && (
        <div className="mt-1 flex items-center gap-2">
          {delta && (
            <span
              className={cn(
                "tabular font-display text-sm font-semibold",
                delta.tono === "sube" ? "text-green" : "text-red",
              )}
            >
              {delta.texto}
            </span>
          )}
          {sub && (
            <span className="font-sans text-xs text-ink-soft">{sub}</span>
          )}
        </div>
      )}
    </div>
  );
}
