// ScenariosChart — superpone las curvas de caja de varios escenarios contra el
// umbral (SVG inline). Escala compartida entre todas las series para que sean
// comparables. Colores de marca (cyan base, green optimista, amber pesimista);
// el rojo queda reservado al umbral (línea de sistema). .toNumber() aquí es SOLO
// geometría de presentación, nunca cálculo.

import { parseMonto } from "@/lib/money";
import type { Escenario, MesProyeccion } from "@/lib/proyeccion";
import { cn } from "@/lib/utils";

export type SerieColor = "cyan" | "green" | "amber";

export interface SerieEscenario {
  escenario: Escenario;
  color: SerieColor;
  meses: MesProyeccion[];
}

const TRAZO: Record<SerieColor, string> = {
  cyan: "stroke-cyan",
  green: "stroke-green",
  amber: "stroke-amber",
};

interface ScenariosChartProps {
  series: SerieEscenario[];
  umbral: string;
  className?: string;
}

export function ScenariosChart({
  series,
  umbral,
  className,
}: ScenariosChartProps) {
  const W = 900;
  const H = 260;
  const P = 10;
  const validas = series.filter((s) => s.meses.length >= 2);
  if (validas.length === 0) return null;

  const u = parseMonto(umbral).toNumber();
  const todas = validas.flatMap((s) =>
    s.meses.map((m) => parseMonto(m.caja).toNumber()),
  );
  const min = Math.min(...todas, u, 0);
  const max = Math.max(...todas, u);
  const span = max - min || 1;
  const x = (i: number, n: number) => (i / (n - 1)) * W;
  const y = (v: number) => P + (1 - (v - min) / span) * (H - 2 * P);
  const yUmbral = y(u);
  const yCero = y(0);

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className={cn("w-full", className ?? "h-64")}
      preserveAspectRatio="none"
      role="img"
      aria-label="Curvas de caja de los escenarios contra el umbral"
    >
      <title>Escenarios de caja vs. umbral</title>
      {min < 0 && (
        <line
          x1={0}
          x2={W}
          y1={yCero}
          y2={yCero}
          className="stroke-hairline"
          strokeWidth={1}
        />
      )}
      {/* umbral (caja mínima) — rojo de sistema, discontinuo */}
      <line
        x1={0}
        x2={W}
        y1={yUmbral}
        y2={yUmbral}
        className="stroke-critico"
        strokeWidth={1.5}
        strokeDasharray="6 4"
      />
      {validas.map((s) => {
        const pts = s.meses
          .map(
            (m, i) =>
              `${x(i, s.meses.length)},${y(parseMonto(m.caja).toNumber())}`,
          )
          .join(" ");
        return (
          <polyline
            key={s.escenario}
            points={pts}
            fill="none"
            className={TRAZO[s.color]}
            strokeWidth={2.5}
            vectorEffect="non-scaling-stroke"
          />
        );
      })}
    </svg>
  );
}
