// CashCurve — curva de caja proyectada vs. umbral (SVG inline, sin dependencia de
// gráficos). Trazo Cyber Cyan, área ≤8 % de opacidad, umbral discontinuo.
// .toNumber() aquí es SOLO geometría de presentación (como formatCOP), nunca cálculo.
//
// F1 (§6 del sistema): modo `anotada` — ejes siempre visibles (Y con 3–4 marcas
// abreviadas, X con meses mmm-aa), umbral ETIQUETADO sobre el propio trazo,
// anotación del hecho relevante (el mínimo con mes · cifra, no un puntico
// anónimo) y zona sombreada del período ya transcurrido. El modo simple
// (sin anotaciones) se conserva para los usos existentes (mini-curvas).

import { formatCOPCompact, formatMesCorto, parseMonto } from "@/lib/money";
import type { MesProyeccion } from "@/lib/proyeccion";
import { cn } from "@/lib/utils";

interface CashCurveProps {
  meses: MesProyeccion[];
  umbral: string;
  /** Clase de alto del SVG (ej. "h-60" hero, "h-28" mini). */
  className?: string;
  /** F1: ejes + umbral etiquetado + mínimo anotado + pasado sombreado. */
  anotada?: boolean;
  /** Mes actual YYYY-MM para el sombreado del pasado (inyectable en tests). */
  hoyMes?: string;
}

function mesActual(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function CashCurve({
  meses,
  umbral,
  className,
  anotada = false,
  hoyMes,
}: CashCurveProps) {
  const W = 900;
  const H = anotada ? 300 : 240;
  // márgenes: en modo anotado hay espacio para ejes y etiquetas
  const ML = anotada ? 80 : 0;
  const MR = anotada ? 14 : 0;
  const MT = anotada ? 18 : 10;
  const MB = anotada ? 28 : 10;
  if (meses.length < 2) return null;

  const cajas = meses.map((m) => parseMonto(m.caja).toNumber());
  const u = parseMonto(umbral).toNumber();
  const min = Math.min(...cajas, u, 0);
  const max = Math.max(...cajas, u);
  const span = max - min || 1;
  const x = (i: number) => ML + (i / (meses.length - 1)) * (W - ML - MR);
  const y = (v: number) => MT + (1 - (v - min) / span) * (H - MT - MB);

  const linea = cajas.map((v, i) => `${x(i)},${y(v)}`).join(" ");
  const area = `${x(0)},${y(min)} ${linea} ${x(meses.length - 1)},${y(min)}`;
  const yUmbral = y(u);
  const yCero = y(0);

  // ── Anotaciones F1 ──
  const iMin = cajas.indexOf(Math.min(...cajas));
  const hoy = hoyMes ?? mesActual();
  // último índice ya transcurrido (mes < mes actual) para la zona sombreada
  let iPasado = -1;
  for (let i = 0; i < meses.length; i++) {
    if (meses[i].mes < hoy) iPasado = i;
  }
  // marcas del eje Y (4, equiespaciadas) y del X (~6 meses)
  const ticksY = [0, 1, 2, 3].map((k) => min + (span * k) / 3);
  const pasoX = Math.max(1, Math.ceil(meses.length / 6));
  const anclaMin = iMin / (meses.length - 1) > 0.6 ? "end" : "start";

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className={cn("w-full", className ?? (anotada ? "h-full" : "h-60"))}
      preserveAspectRatio={anotada ? "xMidYMid meet" : "none"}
      role="img"
      aria-label="Curva de caja proyectada contra el umbral de caja mínima"
    >
      <title>Caja proyectada vs. umbral</title>

      {/* zona ya transcurrida (real) vs. proyectada */}
      {anotada && iPasado >= 0 && (
        <rect
          x={x(0)}
          y={MT}
          width={x(iPasado) - x(0)}
          height={H - MT - MB}
          className="fill-ink/5"
        />
      )}

      {/* rejilla horizontal tenue + marcas Y abreviadas (solo anotada) */}
      {anotada &&
        ticksY.map((v) => (
          <g key={v}>
            <line
              x1={ML}
              x2={W - MR}
              y1={y(v)}
              y2={y(v)}
              className="stroke-hairline"
              strokeWidth={1}
            />
            <text
              x={ML - 8}
              y={y(v) + 4}
              textAnchor="end"
              fontSize={12.5}
              className="tabular fill-ink-faint font-sans"
            >
              {formatCOPCompact(String(v))}
            </text>
          </g>
        ))}

      {/* meses en el eje X (mmm-aa) */}
      {anotada &&
        meses.map((m, i) =>
          i % pasoX === 0 ? (
            <text
              key={m.mes}
              x={x(i)}
              y={H - 8}
              textAnchor="middle"
              fontSize={12.5}
              className="fill-ink-faint font-sans"
            >
              {formatMesCorto(m.mes)}
            </text>
          ) : null,
        )}

      <polygon points={area} className="fill-cyan/10" />
      {/* línea de cero (si el rango la cruza) */}
      {min < 0 && (
        <line
          x1={ML}
          x2={W - MR}
          y1={yCero}
          y2={yCero}
          className="stroke-hairline"
          strokeWidth={1}
        />
      )}
      {/* umbral (caja mínima) — discontinuo, ETIQUETADO sobre el trazo */}
      <line
        x1={ML}
        x2={W - MR}
        y1={yUmbral}
        y2={yUmbral}
        className={anotada ? "stroke-critico" : "stroke-red"}
        strokeWidth={1.5}
        strokeDasharray="6 4"
      />
      {anotada && (
        <text
          x={W - MR - 4}
          y={yUmbral - 6}
          textAnchor="end"
          fontSize={12.5}
          className="tabular fill-critico font-sans font-medium"
        >
          — Umbral {formatCOPCompact(umbral)}
        </text>
      )}
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
            className={anotada ? "fill-critico" : "fill-red"}
          />
        ) : null,
      )}
      {/* anotación del hecho relevante: el mínimo con mes · cifra */}
      {anotada && (
        <g>
          <circle
            cx={x(iMin)}
            cy={y(cajas[iMin])}
            r={4.5}
            className="fill-critico"
          />
          <text
            x={x(iMin) + (anclaMin === "end" ? -10 : 10)}
            y={y(cajas[iMin]) - 10}
            textAnchor={anclaMin}
            fontSize={12.5}
            className="tabular fill-critico font-sans font-semibold"
          >
            {formatMesCorto(meses[iMin].mes)} ·{" "}
            {formatCOPCompact(meses[iMin].caja)}
          </text>
        </g>
      )}
    </svg>
  );
}
