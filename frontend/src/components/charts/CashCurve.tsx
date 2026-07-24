// CashCurve — curva de caja proyectada vs. umbral (SVG inline, sin dependencia de
// gráficos). Trazo Cyber Cyan, área en tinte cian, umbral discontinuo en rojo
// (color de sistema) y marcadores rojos en los meses de perforación.
// .toNumber() aquí es SOLO geometría de presentación (como formatCOP), nunca cálculo.

import { parseMonto } from "@/lib/money";
import type { MesProyeccion } from "@/lib/proyeccion";
import { cn } from "@/lib/utils";

interface CashCurveProps {
  meses: MesProyeccion[];
  umbral: string;
  /** Clase de alto del SVG (ej. "h-60" hero, "h-28" mini). */
  className?: string;
}

export function CashCurve({ meses, umbral, className }: CashCurveProps) {
  const W = 900;
  const H = 240;
  const P = 10; // padding vertical
  if (meses.length < 2) return null;

  const cajas = meses.map((m) => parseMonto(m.caja).toNumber());
  const u = parseMonto(umbral).toNumber();
  const min = Math.min(...cajas, u, 0);
  const max = Math.max(...cajas, u);
  const span = max - min || 1;
  const x = (i: number) => (i / (meses.length - 1)) * W;
  const y = (v: number) => P + (1 - (v - min) / span) * (H - 2 * P);

  const linea = cajas.map((v, i) => `${x(i)},${y(v)}`).join(" ");
  const area = `0,${y(min)} ${linea} ${W},${y(min)}`;
  const yUmbral = y(u);
  const yCero = y(0);

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className={cn("w-full", className ?? "h-60")}
      preserveAspectRatio="none"
      role="img"
      aria-label="Curva de caja proyectada contra el umbral de caja mínima"
    >
      <title>Caja proyectada vs. umbral</title>
      <polygon points={area} className="fill-cyan/10" />
      {/* línea de cero (si el rango la cruza) */}
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
        className="stroke-red"
        strokeWidth={1.5}
        strokeDasharray="6 4"
      />
      {/* curva de caja — Cyber Cyan */}
      <polyline
        points={linea}
        fill="none"
        className="stroke-cyan"
        strokeWidth={2.5}
        vectorEffect="non-scaling-stroke"
      />
      {/* marcadores de meses bajo el mínimo (perforación) */}
      {cajas.map((v, i) =>
        v < u ? (
          <circle
            key={meses[i].mes}
            cx={x(i)}
            cy={y(v)}
            r={3}
            className="fill-red"
          />
        ) : null,
      )}
    </svg>
  );
}
