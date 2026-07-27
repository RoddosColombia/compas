// ChartCard — sistema F1 §5: el título es la CONCLUSIÓN en lenguaje de negocio
// ("La caja toca su punto más bajo en may-2027"), el subtítulo es lo técnico
// (métrica · escenario · período), y el pie da fuente/actualización. Un solo
// protagonista por pantalla: `protagonista` duplica el alto del lienzo.

import type { ReactNode } from "react";

import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export function ChartCard({
  conclusion,
  subtitulo,
  pie,
  protagonista = false,
  acciones,
  children,
  className,
}: {
  /** La conclusión en lenguaje de negocio — lo que el gráfico demuestra. */
  conclusion: string;
  /** métrica · escenario · período. */
  subtitulo?: string;
  /** Fuente / última actualización. */
  pie?: string;
  /** 2× el alto del resto — máximo uno por pantalla. */
  protagonista?: boolean;
  acciones?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <Card className={cn("flex flex-col gap-3 p-5", className)}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-display text-seccion text-ink">{conclusion}</h3>
          {subtitulo && (
            <p className="mt-0.5 font-sans text-apoyo text-ink-faint">
              {subtitulo}
            </p>
          )}
        </div>
        {acciones}
      </div>
      <div className={protagonista ? "h-80" : "h-40"}>{children}</div>
      {pie && (
        <p className="border-t border-hairline pt-2 font-sans text-apoyo text-ink-faint">
          {pie}
        </p>
      )}
    </Card>
  );
}
