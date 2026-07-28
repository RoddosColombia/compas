// components/charts/ComposicionCaja.tsx
//
// V1 §2 — la caja deja de estar sola: barras mensuales de ingreso (arriba) y
// costo + gasto apilados (abajo) sobre un eje IZQUIERDO propio (cientos de M),
// con la línea de caja acumulada encima sobre su eje DERECHO (miles de M) y el
// umbral punteado. La ventana reconciliada (facturas reales) se sombrea. Hover
// por período con el desglose y "de los cuales Auteco" (real/proyectado). En
// horizontes largos agrega por trimestre/año (puntosComposicion) para no saturar
// el eje X. SVG a mano como CashCurve; .toNumber() SOLO geometría (regla 1).

import { useState } from "react";

import { type PuntoComposicion, puntosComposicion } from "@/lib/egreso";
import { formatCOPCompact, formatCOPEntero, parseMonto } from "@/lib/money";
import type { MesProyeccion } from "@/lib/proyeccion";
import { cn } from "@/lib/utils";

interface ComposicionCajaProps {
  meses: MesProyeccion[];
  umbral: string;
  ventanaReconciliada: [string, string] | null;
}

const W = 900;
const H = 320;
const ML = 78;
const MR = 78;
const MT = 20;
const MB = 54;

export function ComposicionCaja({
  meses,
  umbral,
  ventanaReconciliada,
}: ComposicionCajaProps) {
  const [hover, setHover] = useState<number | null>(null);
  if (meses.length < 1) return null;

  const P = puntosComposicion(meses, ventanaReconciliada);
  const n = P.length;
  // number SOLO para la geometría de las barras/línea (regla 1); el formato usa Decimal.
  const ingreso = P.map((p) => p.ingreso.toNumber());
  const costo = P.map((p) => p.costo.toNumber());
  const gasto = P.map((p) => p.gasto.toNumber());
  const cajas = P.map((p) => p.caja.toNumber());
  const u = parseMonto(umbral).toNumber();

  // Eje IZQUIERDO (barras): ingreso hacia arriba, costo+gasto hacia abajo.
  const topBar = Math.max(...ingreso, 0);
  const botBar = -Math.max(...costo.map((c, i) => c + gasto[i]), 0);
  const spanBar = topBar - botBar || 1;
  // Eje DERECHO (caja): incluye umbral y 0.
  const minCaja = Math.min(...cajas, u, 0);
  const maxCaja = Math.max(...cajas, u);
  const spanCaja = maxCaja - minCaja || 1;

  const plotW = W - ML - MR;
  const plotH = H - MT - MB;
  const slot = plotW / n;
  const barW = Math.min(slot * 0.6, 34);
  const cx = (i: number) => ML + (i + 0.5) * slot;
  const yBar = (v: number) => MT + (1 - (v - botBar) / spanBar) * plotH;
  const yCaja = (v: number) => MT + (1 - (v - minCaja) / spanCaja) * plotH;

  const y0 = yBar(0);
  const lineaCaja = cajas.map((v, i) => `${cx(i)},${yCaja(v)}`).join(" ");
  const pasoX = Math.max(1, Math.ceil(n / 8));

  const ticksBar = [topBar, topBar / 2, 0, botBar / 2, botBar];
  const ticksCaja = [0, 1, 2, 3].map((k) => minCaja + (spanCaja * k) / 3);

  // sombreado de la ventana reconciliada (períodos con facturas reales)
  let recL = -1;
  let recR = -1;
  for (let i = 0; i < n; i++) {
    if (P[i].real) {
      if (recL < 0) recL = i;
      recR = i;
    }
  }

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="h-full w-full"
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label="Ingreso, costo y gasto por período con la caja acumulada y su umbral"
      >
        <title>
          Composición de caja: ingreso, costo, gasto y caja acumulada
        </title>

        {recL >= 0 && (
          <rect
            x={cx(recL) - slot / 2}
            y={MT}
            width={(recR - recL) * slot + slot}
            height={plotH}
            className="fill-cyan/5"
          />
        )}

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
              x={W - MR + 6}
              y={yCaja(v) + 4}
              textAnchor="start"
              fontSize={12}
              className="tabular fill-cyan/80 font-sans"
            >
              {formatCOPCompact(String(v))}
            </text>
          </g>
        ))}

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
          y1={y0}
          y2={y0}
          className="stroke-ink/25"
          strokeWidth={1}
        />

        {/* barras: ingreso arriba, costo (oscuro) + gasto (claro) apilados abajo */}
        {P.map((p, i) => {
          const yc = yBar(-costo[i]);
          return (
            <g key={p.etiqueta}>
              <rect
                x={cx(i) - barW / 2}
                y={yBar(ingreso[i])}
                width={barW}
                height={Math.max(0, y0 - yBar(ingreso[i]))}
                className="fill-positivo/80"
              />
              <rect
                x={cx(i) - barW / 2}
                y={y0}
                width={barW}
                height={Math.max(0, yc - y0)}
                className="fill-ink/65"
              />
              <rect
                x={cx(i) - barW / 2}
                y={yc}
                width={barW}
                height={Math.max(0, yBar(-(costo[i] + gasto[i])) - yc)}
                className="fill-ink/35"
              />
            </g>
          );
        })}

        {/* umbral (sobre el eje de la caja) */}
        <line
          x1={ML}
          x2={W - MR}
          y1={yCaja(u)}
          y2={yCaja(u)}
          className="stroke-critico"
          strokeWidth={1.5}
          strokeDasharray="6 4"
        />

        {/* línea de caja acumulada (eje derecho) */}
        <polyline
          points={lineaCaja}
          fill="none"
          className="stroke-cyan"
          strokeWidth={2.5}
          vectorEffect="non-scaling-stroke"
        />

        {P.map((p, i) =>
          i % pasoX === 0 ? (
            <text
              key={p.etiqueta}
              x={cx(i)}
              y={H - 30}
              textAnchor="middle"
              fontSize={12}
              className="fill-ink-faint font-sans"
            >
              {p.etiqueta}
            </text>
          ) : null,
        )}

        {/* zonas de hover invisibles por período */}
        {P.map((p, i) => (
          <rect
            key={p.etiqueta}
            x={ML + i * slot}
            y={MT}
            width={slot}
            height={plotH}
            fill="transparent"
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover((h) => (h === i ? null : h))}
          />
        ))}
      </svg>

      {/* leyenda (el color nunca va solo — F1) */}
      <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 px-2 text-apoyo text-ink-soft">
        <Clave className="bg-positivo/80" label="Ingreso" />
        <Clave className="bg-ink/65" label="Costo" />
        <Clave className="bg-ink/35" label="Gasto" />
        <Clave className="bg-cyan" label="Caja acumulada" linea />
        <Clave className="bg-critico" label="Umbral" linea punteado />
        {ventanaReconciliada && (
          <Clave className="bg-cyan/20" label="Ventana con facturas reales" />
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
      className="pointer-events-none absolute top-2 z-20 w-56 rounded-lg border border-hairline bg-surface p-3 text-apoyo shadow-lg"
      style={izq ? { right: `${100 - leftPct}%` } : { left: `${leftPct}%` }}
    >
      <div className="mb-1 font-semibold text-ink">{p.etiqueta}</div>
      <Fila etiqueta="Ingreso" valor={formatCOPEntero(p.ingreso)} />
      <Fila etiqueta="Costo" valor={formatCOPEntero(p.costo)} />
      {!p.auteco.isZero() && (
        <div className="pl-3 text-ink-faint">
          de los cuales Auteco: {formatCOPEntero(p.auteco)} ·{" "}
          {p.real ? "real" : "proyectado"}
        </div>
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
