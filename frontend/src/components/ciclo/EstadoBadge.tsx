// EstadoBadge — chip de estado del mes con tooltip de "qué significa y qué
// sigue" (C1, extraído en C2 para compartirlo entre MesesPage y la Cabina).

import type { Mes } from "@/lib/meses";

const ESTILO: Record<Mes["estado"], string> = {
  sugerido: "bg-surface-muted text-ink-soft",
  propuesto: "bg-amber/10 text-amber",
  definido: "bg-cyan/10 text-cyan",
  en_ejecucion: "bg-green/10 text-green",
  cerrado: "bg-surface-muted text-ink-faint",
};

const AYUDA: Record<Mes["estado"], string> = {
  sugerido:
    "Mes abierto. Siguiente paso: generar el presupuesto sugerido y acotarlo.",
  propuesto:
    "Presupuesto acotado al menos una vez. Siguiente paso: aprobarlo para ponerlo en ejecución.",
  definido: "Presupuesto aprobado. El mes pasa a ejecución.",
  en_ejecucion:
    "Presupuesto en ejecución. Síguelo en Presupuesto (control) y reporta la caja diaria.",
  cerrado: "Mes cerrado: el histórico es inmutable.",
};

export function EstadoBadge({ estado }: { estado: Mes["estado"] }) {
  return (
    <span
      title={AYUDA[estado]}
      className={`cursor-help rounded-full px-2 py-0.5 font-sans text-xs font-medium ${ESTILO[estado]}`}
    >
      {estado}
    </span>
  );
}
