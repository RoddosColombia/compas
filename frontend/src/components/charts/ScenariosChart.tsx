// ScenariosChart — F1.1 §3: el gráfico de escenarios que COMUNICA. En vez de
// tres líneas superpuestas en una escala de 5 años: BANDA DE RANGO (área entre
// pesimista y optimista, tinte suave) + línea base encima, zoom a la ventana
// donde los futuros divergen, umbral etiquetado sobre el trazo, ejes visibles,
// y ETIQUETA DIRECTA al final de cada trazo con el piso del escenario — esas
// tres cifras son la pantalla entera. .toNumber() SOLO geometría (regla 1).

import { formatCOPCompact, formatMesCorto, parseMonto } from "@/lib/money";
import type { MesProyeccion } from "@/lib/proyeccion";
import { cn } from "@/lib/utils";

export type TonoSerie = "atencion" | "cyan" | "positivo";

export interface SerieEscenario {
  /** etiqueta directa del trazo (Pesimista/Base/Optimista) */
  label: string;
  tono: TonoSerie;
  meses: MesProyeccion[];
  /** piso de caja del ESCENARIO COMPLETO (no de la ventana) — la cifra clave */
  piso: string;
}

const TEXTO: Record<TonoSerie, string> = {
  cyan: "fill-ink",
  positivo: "fill-positivo",
  atencion: "fill-atencion",
};

export function ScenariosChart({
  pesimista,
  base,
  optimista,
  umbral,
  className,
}: {
  pesimista: SerieEscenario;
  base: SerieEscenario;
  optimista: SerieEscenario;
  umbral: string;
  className?: string;
}) {
  const W = 900;
  const H = 300;
  const ML = 80;
  const MR = 210; // espacio para las etiquetas directas al final del trazo
  const MT = 18;
  const MB = 28;

  const series = [pesimista, base, optimista];
  const n = Math.min(...series.map((s) => s.meses.length));
  if (n < 2) return null;

  const vals = (s: SerieEscenario) =>
    s.meses.slice(0, n).map((m) => parseMonto(m.caja).toNumber());
  const vp = vals(pesimista);
  const vb = vals(base);
  const vo = vals(optimista);
  const u = parseMonto(umbral).toNumber();

  const min = Math.min(...vp, ...vb, ...vo, u);
  const max = Math.max(...vp, ...vb, ...vo, u);
  const span = max - min || 1;
  const x = (i: number) => ML + (i / (n - 1)) * (W - ML - MR);
  const y = (v: number) => MT + (1 - (v - min) / span) * (H - MT - MB);
  const linea = (vs: number[]) => vs.map((v, i) => `${x(i)},${y(v)}`).join(" ");

  // banda de rango: optimista arriba + pesimista abajo (en reversa)
  const banda = [
    ...vo.map((v, i) => `${x(i)},${y(v)}`),
    ...vp.map((v, i) => `${x(i)},${y(v)}`).reverse(),
  ].join(" ");

  const ticksY = [0, 1, 2, 3].map((k) => min + (span * k) / 3);
  const pasoX = Math.max(1, Math.ceil(n / 6));

  // etiquetas directas al final, con anti-colisión vertical (≥18 px)
  const etiquetas = [
    { s: optimista, yFin: y(vo[n - 1]) },
    { s: base, yFin: y(vb[n - 1]) },
    { s: pesimista, yFin: y(vp[n - 1]) },
  ].sort((a, b) => a.yFin - b.yFin);
  for (let i = 1; i < etiquetas.length; i++) {
    if (etiquetas[i].yFin - etiquetas[i - 1].yFin < 18) {
      etiquetas[i].yFin = etiquetas[i - 1].yFin + 18;
    }
  }

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className={cn("w-full", className ?? "h-full")}
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label="Banda de escenarios de caja (pesimista a optimista) contra el umbral"
    >
      <title>Escenarios de caja vs. umbral</title>

      {ticksY.map((v) => (
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
      {base.meses.slice(0, n).map((m, i) =>
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

      {/* banda pesimista↔optimista (tinte suave) + bordes finos */}
      <polygon points={banda} className="fill-cyan/10" />
      <polyline
        points={linea(vo)}
        fill="none"
        className="stroke-positivo"
        strokeWidth={1.5}
        vectorEffect="non-scaling-stroke"
      />
      <polyline
        points={linea(vp)}
        fill="none"
        className="stroke-atencion"
        strokeWidth={1.5}
        vectorEffect="non-scaling-stroke"
      />
      {/* línea base encima */}
      <polyline
        points={linea(vb)}
        fill="none"
        className="stroke-cyan"
        strokeWidth={2.5}
        vectorEffect="non-scaling-stroke"
      />

      {/* umbral etiquetado sobre el propio trazo */}
      <line
        x1={ML}
        x2={W - MR}
        y1={y(u)}
        y2={y(u)}
        className="stroke-critico"
        strokeWidth={1.5}
        strokeDasharray="6 4"
      />
      <text
        x={W - MR - 4}
        y={y(u) - 6}
        textAnchor="end"
        fontSize={12.5}
        className="tabular fill-critico font-sans font-medium"
      >
        — Umbral {formatCOPCompact(umbral)}
      </text>

      {/* la pantalla entera: el piso de cada escenario, etiqueta directa */}
      {etiquetas.map(({ s, yFin }) => (
        <text
          key={s.label}
          x={W - MR + 8}
          y={yFin + 4}
          fontSize={12.5}
          className={cn("tabular font-sans font-semibold", TEXTO[s.tono])}
        >
          {s.label} · piso {formatCOPCompact(s.piso)}
        </text>
      ))}
    </svg>
  );
}
