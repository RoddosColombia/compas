// components/charts/ComposicionCaja.tsx
//
// V1.2 (Parte VI iterado) — el gráfico se reorganiza alrededor de la CAJA, que es la
// variable que decide. DOS paneles sobre el mismo eje X:
//   · arriba (45%): ingreso y egreso LADO A LADO (barras agrupadas) para comparar mes
//     a mes; el egreso apila su gama de ROJOS discriminada (Auteco + moto nueva) y el
//     gasto encima.
//   · abajo (55%, más alto): la caja acumulada con su umbral, en un eje ANCLADO AL
//     UMBRAL (no al cero) para que las caídas de $100-200 M se vean. Anotada: el mes de
//     menor caja, el próximo compromiso Auteco y —si ocurre— la perforación del umbral.
// Nada se inventa: una anotación sin dato no se dibuja. SVG a mano; .toNumber() SOLO
// geometría (regla 1); los rótulos usan Decimal.

import { useState } from "react";

import {
  type PuntoComposicion,
  anotacionesCaja,
  puntosComposicion,
} from "@/lib/egreso";
import { formatCOPCompact, formatCOPEntero, parseMonto } from "@/lib/money";
import type { MarcaOrigen, MesProyeccion } from "@/lib/proyeccion";
import { cn } from "@/lib/utils";

// E1·P6 — marcas que representan cifra ANCLADA (real o mes en curso): la línea de caja
// va SÓLIDA hasta el último de estos meses y PUNTEADA (proyección) de ahí en adelante.
const MARCAS_ANCLADAS = new Set<MarcaOrigen>([
  "cerrado",
  "cerrado_sospechoso",
  "en_ejecucion",
]);

interface ComposicionCajaProps {
  meses: MesProyeccion[];
  umbral: string;
  ventanaReconciliada: [string, string] | null;
  mesesAnclados?: Record<string, MarcaOrigen>;
}

const W = 900;
const H = 320;
const ML = 78;
const MR = 78;
const MT = 18;
const MB = 40; // banda inferior para las etiquetas compartidas del eje X
const GAP = 20; // separación entre el panel de barras y el de caja

export function ComposicionCaja({
  meses,
  umbral,
  ventanaReconciliada,
  mesesAnclados = {},
}: ComposicionCajaProps) {
  const [hover, setHover] = useState<number | null>(null);
  if (meses.length < 1) return null;

  const P = puntosComposicion(meses, ventanaReconciliada);
  const n = P.length;
  // number SOLO para la geometría (regla 1); el formato usa Decimal.
  const ingreso = P.map((p) => p.ingreso.toNumber());
  const auteco = P.map((p) => p.auteco.toNumber());
  const costo = P.map((p) => p.costo.toNumber());
  const gasto = P.map((p) => p.gasto.toNumber());
  const cajas = P.map((p) => p.caja.toNumber());
  const u = parseMonto(umbral).toNumber();
  const anota = anotacionesCaja(P, parseMonto(umbral));

  const plotW = W - ML - MR;
  const slot = plotW / n;
  const cx = (i: number) => ML + (i + 0.5) * slot;
  const pasoX = Math.max(1, Math.ceil(n / 8));

  // ── Dos paneles: barras (45%) arriba, caja (55%) abajo ──
  const plotH = H - MT - MB;
  const barsH = Math.round(plotH * 0.45);
  const cajaH = plotH - barsH - GAP;
  const barsY0 = MT;
  const barsY1 = MT + barsH; // línea base (cero) de las barras
  const cajaY0 = barsY1 + GAP;
  const cajaY1 = cajaY0 + cajaH;

  // Panel de BARRAS agrupadas — ingreso y egreso (costo+gasto) hacia ARRIBA.
  const egresoTot = costo.map((c, i) => c + gasto[i]);
  const maxBar = Math.max(...ingreso, ...egresoTot, 0) || 1;
  const yBar = (v: number) => barsY1 - (v / maxBar) * barsH;
  const bw = Math.min(slot * 0.34, 24); // ancho de cada barra del par

  // Panel de CAJA — eje anclado al UMBRAL (A1): [min(caja,umbral)−m, max(caja,umbral)+m].
  const lo = Math.min(...cajas, u);
  const hi = Math.max(...cajas, u);
  const margen = (hi - lo || Math.abs(hi) || 1) * 0.08;
  const cMin = lo - margen;
  const cMax = hi + margen;
  const spanCaja = cMax - cMin || 1;
  const yCaja = (v: number) => cajaY1 - ((v - cMin) / spanCaja) * cajaH;
  const puntosCaja = cajas.map((v, i) => `${cx(i)},${yCaja(v)}`);
  // E1·P6 — partir la línea: sólida hasta el último mes anclado (real/en curso),
  // punteada de ahí en adelante (proyección). Sin anclaje → una sola línea (candado).
  let corte = -1;
  for (let i = 0; i < meses.length; i++) {
    if (MARCAS_ANCLADAS.has(mesesAnclados[meses[i].mes] as MarcaOrigen))
      corte = i;
  }
  const cajaSolida =
    corte >= 0
      ? puntosCaja.slice(0, corte + 1).join(" ")
      : puntosCaja.join(" ");
  const cajaPunteada =
    corte >= 0 && corte < puntosCaja.length - 1
      ? puntosCaja
          .slice(corte)
          .join(" ") // solapa en el corte para continuidad
      : "";
  const sospIdx = meses.findIndex(
    (m) => mesesAnclados[m.mes] === "cerrado_sospechoso",
  );

  const ticksBar = [maxBar, maxBar / 2, 0];
  const ticksCaja = [cMin, (cMin + cMax) / 2, cMax];

  // sombreado de la ventana reconciliada (períodos con facturas reales) — ambos paneles
  let recL = -1;
  let recR = -1;
  for (let i = 0; i < n; i++) {
    if (P[i].real) {
      if (recL < 0) recL = i;
      recR = i;
    }
  }

  // posición del rótulo de una anotación sin salirse del lienzo
  const clampX = (i: number) => Math.min(Math.max(cx(i), ML + 32), W - MR - 32);

  return (
    <div className="flex h-full flex-col">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="min-h-0 w-full flex-1"
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label="Ingreso y egreso por período (barras agrupadas) y, debajo, la caja acumulada contra su umbral, anotada"
      >
        <title>
          Composición de caja: ingreso y egreso arriba; caja acumulada y mínimo
          de caja abajo, con anotaciones de los meses clave
        </title>

        {recL >= 0 && (
          <rect
            x={cx(recL) - slot / 2}
            y={barsY0}
            width={(recR - recL) * slot + slot}
            height={cajaY1 - barsY0}
            className="fill-cyan/5"
          />
        )}

        {/* marca vertical del próximo compromiso Auteco (A4) — atraviesa ambos paneles */}
        {anota.autecoIdx !== null && (
          <g>
            <line
              x1={cx(anota.autecoIdx)}
              x2={cx(anota.autecoIdx)}
              y1={barsY0}
              y2={cajaY1}
              className="stroke-ink/30"
              strokeWidth={1}
              strokeDasharray="3 3"
            />
            <text
              x={clampX(anota.autecoIdx)}
              y={barsY0 + 10}
              textAnchor="middle"
              fontSize={11}
              className="fill-ink-soft font-sans"
            >
              Compromiso Auteco {formatCOPCompact(P[anota.autecoIdx].auteco)}
            </text>
          </g>
        )}

        {/* ── Panel superior: barras agrupadas ── */}
        {ticksBar.map((v) => (
          <text
            key={`b${v}`}
            x={ML - 8}
            y={yBar(v) + 4}
            textAnchor="end"
            fontSize={12}
            className="tabular fill-ink-faint font-sans"
          >
            {formatCOPCompact(String(v))}
          </text>
        ))}
        <line
          x1={ML}
          x2={W - MR}
          y1={barsY1}
          y2={barsY1}
          className="stroke-ink/25"
          strokeWidth={1}
        />

        {P.map((p, i) => {
          const xIng = cx(i) - bw - 1; // ingreso a la izquierda del par
          const xEg = cx(i) + 1; // egreso a la derecha
          const yAut = yBar(auteco[i]);
          const yCosto = yBar(costo[i]);
          const yEg = yBar(egresoTot[i]);
          return (
            <g key={p.etiqueta}>
              {/* ingreso (verde) */}
              <rect
                x={xIng}
                y={yBar(ingreso[i])}
                width={bw}
                height={Math.max(0, barsY1 - yBar(ingreso[i]))}
                className="fill-positivo/80"
              />
              {/* egreso apilado: Auteco (rojo) + moto nueva (rojo claro) + gasto */}
              <rect
                x={xEg}
                y={yAut}
                width={bw}
                height={Math.max(0, barsY1 - yAut)}
                className="fill-costo"
              />
              <rect
                x={xEg}
                y={yCosto}
                width={bw}
                height={Math.max(0, yAut - yCosto)}
                className="fill-costo/55"
              />
              <rect
                x={xEg}
                y={yEg}
                width={bw}
                height={Math.max(0, yCosto - yEg)}
                className="fill-gasto"
              />
            </g>
          );
        })}

        {/* ── Panel inferior: caja acumulada + umbral, anclado al umbral ── */}
        {ticksCaja.map((v) => (
          <g key={`c${v}`}>
            <line
              x1={ML}
              x2={W - MR}
              y1={yCaja(v)}
              y2={yCaja(v)}
              className="stroke-hairline"
              strokeWidth={1}
            />
            <text
              x={ML - 8}
              y={yCaja(v) + 4}
              textAnchor="end"
              fontSize={12}
              className="tabular fill-cyan/80 font-sans"
            >
              {formatCOPCompact(String(v))}
            </text>
          </g>
        ))}

        {/* umbral (línea punteada, sobre el eje de la caja) */}
        <line
          x1={ML}
          x2={W - MR}
          y1={yCaja(u)}
          y2={yCaja(u)}
          className="stroke-critico"
          strokeWidth={1.5}
          strokeDasharray="6 4"
        />
        <text
          x={W - MR + 6}
          y={yCaja(u) + 4}
          textAnchor="start"
          fontSize={12}
          className="tabular fill-critico font-sans"
        >
          mínimo de caja
        </text>

        {/* línea de caja acumulada — sólida (real/en curso) → punteada (proyección) */}
        <polyline
          data-caja
          points={cajaSolida}
          fill="none"
          className="stroke-cyan"
          strokeWidth={2.5}
          vectorEffect="non-scaling-stroke"
        />
        {cajaPunteada && (
          <polyline
            data-caja
            points={cajaPunteada}
            fill="none"
            className="stroke-ink-decor"
            strokeWidth={2}
            strokeDasharray="7 5"
            vectorEffect="non-scaling-stroke"
          />
        )}
        {sospIdx >= 0 && (
          <circle
            data-sospechoso
            cx={cx(sospIdx)}
            cy={yCaja(cajas[sospIdx])}
            r={5}
            className="fill-atencion"
          />
        )}

        {/* anotación: mes de MENOR caja (A4) — siempre existe */}
        <g>
          <circle
            cx={cx(anota.minIdx)}
            cy={yCaja(cajas[anota.minIdx])}
            r={4}
            className="fill-cyan"
          />
          <text
            x={clampX(anota.minIdx)}
            y={yCaja(cajas[anota.minIdx]) - 10}
            textAnchor="middle"
            fontSize={11}
            className="fill-ink font-sans font-semibold"
          >
            menor caja {formatCOPCompact(P[anota.minIdx].caja)}
          </text>
        </g>

        {/* anotación: perforación del umbral (A4) — solo si ocurre */}
        {anota.perforaIdx !== null && (
          <g>
            <circle
              cx={cx(anota.perforaIdx)}
              cy={yCaja(cajas[anota.perforaIdx])}
              r={4}
              className="fill-surface stroke-critico"
              strokeWidth={2}
            />
            <text
              x={clampX(anota.perforaIdx)}
              y={yCaja(cajas[anota.perforaIdx]) + 18}
              textAnchor="middle"
              fontSize={11}
              className="fill-critico font-sans"
            >
              baja del mínimo de caja
            </text>
          </g>
        )}

        {/* etiquetas del eje X — compartidas, en la banda inferior */}
        {P.map((p, i) =>
          i % pasoX === 0 ? (
            <text
              key={p.etiqueta}
              x={cx(i)}
              y={H - 12}
              textAnchor="middle"
              fontSize={12}
              className="fill-ink-faint font-sans"
            >
              {p.etiqueta}
            </text>
          ) : null,
        )}

        {/* zonas de hover invisibles por período (cubren ambos paneles) */}
        {P.map((p, i) => (
          <rect
            key={p.etiqueta}
            x={ML + i * slot}
            y={barsY0}
            width={slot}
            height={cajaY1 - barsY0}
            fill="transparent"
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover((h) => (h === i ? null : h))}
          />
        ))}
      </svg>

      {/* leyenda (el color nunca va solo — F1). Fuera del SVG, en la columna flex. */}
      <div className="mt-1 flex shrink-0 flex-wrap items-center gap-x-4 gap-y-1 px-2 text-apoyo text-ink-soft">
        <Clave className="bg-positivo/80" label="Ingreso" />
        <Clave className="bg-costo" label="Costo" />
        <Clave className="bg-gasto" label="Gasto" />
        <Clave className="bg-cyan" label="Caja acumulada" linea />
        <Clave className="bg-critico" label="Mínimo de caja" linea punteado />
        {ventanaReconciliada && (
          <Clave
            className="bg-cyan/20"
            label="Meses con facturas ya registradas"
          />
        )}
      </div>

      {hover !== null && (
        <HoverTooltip p={P[hover]} leftPct={(cx(hover) / W) * 100} />
      )}
    </div>
  );
}

function Clave({
  className,
  label,
  linea,
  punteado,
}: {
  className: string;
  label: string;
  linea?: boolean;
  punteado?: boolean;
}) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className={cn(
          "inline-block",
          linea ? "h-0.5 w-4" : "h-2.5 w-2.5 rounded-sm",
          punteado && "opacity-70",
          className,
        )}
      />
      {label}
    </span>
  );
}

function HoverTooltip({
  p,
  leftPct,
}: { p: PuntoComposicion; leftPct: number }) {
  const izq = leftPct > 60;
  return (
    <div
      className="pointer-events-none absolute top-2 z-20 w-60 rounded-lg border border-hairline bg-surface p-3 text-apoyo shadow-lg"
      style={izq ? { right: `${100 - leftPct}%` } : { left: `${leftPct}%` }}
    >
      <div className="mb-1 font-semibold text-ink">{p.etiqueta}</div>

      <Fila etiqueta="Ingreso" valor={formatCOPEntero(p.ingreso)} />
      <Sub etiqueta="Recaudo semanal" valor={formatCOPEntero(p.recaudo)} />
      <Sub etiqueta="Cuota inicial" valor={formatCOPEntero(p.inicial)} />

      <Fila etiqueta="Costo" valor={formatCOPEntero(p.costo)} />
      {!p.auteco.isZero() && (
        <Sub
          etiqueta={`Auteco · ${p.real ? "real" : "proyectado"}`}
          valor={formatCOPEntero(p.auteco)}
        />
      )}
      {!p.nueva.isZero() && (
        <Sub etiqueta="Moto nueva" valor={formatCOPEntero(p.nueva)} />
      )}

      <Fila etiqueta="Gasto" valor={formatCOPEntero(p.gasto)} />
      <Fila
        etiqueta="Flujo"
        valor={formatCOPEntero(p.flujo)}
        tono={p.flujo.isNegative() ? "critico" : undefined}
      />
      <Fila etiqueta="Caja" valor={formatCOPEntero(p.caja)} fuerte />
    </div>
  );
}

function Sub({ etiqueta, valor }: { etiqueta: string; valor: string }) {
  return (
    <div className="flex justify-between gap-3 pl-3 text-ink-faint">
      <span>{etiqueta}</span>
      <span className="tabular">{valor}</span>
    </div>
  );
}

function Fila({
  etiqueta,
  valor,
  tono,
  fuerte,
}: {
  etiqueta: string;
  valor: string;
  tono?: "critico";
  fuerte?: boolean;
}) {
  return (
    <div className="flex justify-between gap-3">
      <span className="text-ink-soft">{etiqueta}</span>
      <span
        className={cn(
          "tabular",
          fuerte ? "font-semibold text-ink" : "text-ink",
          tono === "critico" && "text-critico",
        )}
      >
        {valor}
      </span>
    </div>
  );
}
