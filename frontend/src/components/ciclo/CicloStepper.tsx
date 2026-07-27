// CicloStepper — el ciclo mensual como stepper de texto (C1, extraído en C2
// para compartirlo entre PresupuestoMesPage y la Cabina sin duplicar).
// Estados del mes: sugerido (recién abierto o con sugerido generado) →
// propuesto → en_ejecucion (definido es transicional) → cerrado.

import { cn } from "@/lib/utils";

const PASOS = [
  "Abierto",
  "Sugerido",
  "Propuesto",
  "Aprobado (en ejecución)",
  "Cerrado",
] as const;

/** Índice del paso actual en el stepper según estado del mes + si hay líneas. */
export function pasoActual(estado: string, sinLineas: boolean): number {
  switch (estado) {
    case "sugerido":
      return sinLineas ? 0 : 1;
    case "propuesto":
      return 2;
    case "definido":
    case "en_ejecucion":
      return 3;
    case "cerrado":
      return 4;
    default:
      return 0;
  }
}

const ACCION_SIGUIENTE: Record<number, string> = {
  0: "Siguiente paso: generar el presupuesto sugerido.",
  1: "Siguiente paso: acotar los rubros que lo necesiten y aprobar.",
  2: "Siguiente paso: aprobar el presupuesto para ponerlo en ejecución.",
  3: "El mes está en ejecución: síguelo en Presupuesto (control).",
  4: "El mes está cerrado y es inmutable.",
};

export function CicloStepper({
  estado,
  sinLineas,
}: {
  estado: string;
  sinLineas: boolean;
}) {
  const paso = pasoActual(estado, sinLineas);
  return (
    <div className="flex flex-col gap-2">
      <ol className="flex flex-wrap items-center gap-1 font-sans text-sm">
        {PASOS.map((p, i) => (
          <li key={p} className="flex items-center gap-1">
            {i > 0 && <span className="text-ink-faint">→</span>}
            <span
              aria-current={i === paso ? "step" : undefined}
              className={cn(
                "rounded-full px-2.5 py-0.5",
                i === paso
                  ? "bg-cyan/10 font-semibold text-cyan"
                  : i < paso
                    ? "text-ink-soft"
                    : "text-ink-faint",
              )}
            >
              {p}
            </span>
          </li>
        ))}
      </ol>
      <p className="font-sans text-apoyo text-ink-faint">
        {ACCION_SIGUIENTE[paso]}
      </p>
    </div>
  );
}
