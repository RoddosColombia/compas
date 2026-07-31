// components/charts/ComposicionCaja.tsx
//
// V1 §2 + V1.1 (Parte VI): la caja deja de estar sola. DOS paneles alineados sobre el
// MISMO eje X (ítem 5: antes la caja compartía lienzo con las barras y su línea se leía
// como "negativa"): arriba, barras de ingreso (verde) y costo+gasto apilados (gama de
// ROJOS, ítem 3 — distinta del `critico` de alertas); abajo, la caja acumulada con su
// umbral, en su propio eje. La barra de costo se DISCRIMINA en Auteco vs moto nueva
// (ítem 2). El hover trae el desglose (ítem 1: recaudo semanal vs cuota inicial; costo:
// Auteco real/proyectado vs moto nueva). Layout en columna flex para que las etiquetas
// del eje X y la leyenda quepan sin invadir el pie de la tarjeta (ítems 4 y 7).
// SVG a mano; .toNumber() SOLO geometría (regla 1).

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
const H = 300;
const ML = 78;
const MR = 78;
const MT = 16;
const MB = 40; // banda inferior para las etiquetas compartidas del eje X
const GAP = 22; // separación entre el panel de barras y el de caja

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
  const auteco = P.map((p) => p.auteco.toNumber());
  const costo = P.map((p) => p.costo.toNumber());
  const gasto = P.map((p) => p.gasto.toNumber());
  const cajas = P.map((p) => p.caja.toNumber());
  const u = parseMonto(umbral).toNumber();

  const plotW = W - ML - MR;
  const slot = plotW / n;
  const barW = Math.min(slot * 0.6, 34);
  const cx = (i: number) => ML + (i + 0.5) * slot;

  // ── Dos paneles apilados que comparten el eje X ──
  const plotH = H - MT - MB;
  const topH = Math.round(plotH * 0.58); // barras
  const botH = plotH - topH - GAP; // caja
  const topY0 = MT;
  const botY0 = MT + topH + GAP;

  // Panel SUPERIOR (barras): ingreso hacia arriba, costo+gasto hacia abajo.
  const topBar = Math.max(...ingreso, 0);
  const botBar = -Math.max(...costo.map((c, i) => c + gasto[i]), 0);
  const spanBar = topBar - botBar || 1;
  const yBar = (v: number) => topY0 + (1 - (v - botBar) / spanBar) * topH;
  const y0 = yBar(0);

  // Panel INFERIOR (caja): incluye umbral y 0.
  const minCaja = Math.min(...cajas, u, 0);
  const maxCaja = Math.max(...cajas, u);
  const spanCaja = maxCaja - minCaja || 1;
  const yCaja = (v: number) => botY0 + (1 - (v - minCaja) / spanCaja) * botH;

  const lineaCaja = cajas.map((v, i) => `${cx(i)},${yCaja(v)}`).join(" ");
  const pasoX = Math.max(1, Math.ceil(n / 8));

  const ticksBar = [topBar, 0, botBar];
  const ticksCaja = [0, 1, 2].map((k) => minCaja + (spanCaja * k) / 2);

  // sombreado de la ventana reconciliada (períodos con facturas reales) — ambos paneles
  let recL = -1;
  let recR = -1;
  for (let i = 0; i < n; i++) {
    if (P[i].real) {
      if (recL < 0) recL = i;
      recR = i;
    }
  }

  return (
    <div className="flex h-full flex-col">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="min-h-0 w-full flex-1"
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label="Ingreso, costo y gasto por período y, debajo, la caja acumulada contra su umbral"
      >
        <title>
          Composición de caja: ingreso, costo y gasto arriba; caja acumulada y
          umbral abajo
        </title>

        {recL >= 0 && (
          <rect
            x={cx(recL) - slot / 2}
            y={topY0}
            width={(recR - recL) * slot + slot}
            height={botY0 + botH - topY0}
            className="fill-cyan/5"
          />
        )}

        {/* ── Panel superior: barras ── */}
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

        {/* barras: ingreso arriba; costo (Auteco + moto nueva) y gasto apilados abajo */}
        {P.map((p, i) => {
          const yAut = yBar(-auteco[i]); // fin del segmento Auteco
          const yCosto = yBar(-costo[i]); // fin del costo (Auteco + nueva)
          return (
            <g key={p.etiqueta}>
              <rect
                x={cx(i) - barW / 2}
                y={yBar(ingreso[i])}
                width={barW}
                height={Math.max(0, y0 - yBar(ingreso[i]))}
                className="fill-positivo/80"
              />
              {/* costo — Auteco (rojo pleno) */}
              <rect
                x={cx(i) - barW / 2}
                y={y0}
                width={barW}
                height={Math.max(0, yAut - y0)}
                className="fill-costo"
              />
              {/* costo — moto nueva (mismo rojo, más claro) */}
              <rect
                x={cx(i) - barW / 2}
                y={yAut}
                width={barW}
                height={Math.max(0, yCosto - yAut)}
                className="fill-costo/55"
              />
              {/* gasto — rojo suave de la gama */}
              <rect
                x={cx(i) - barW / 2}
                y={yCosto}
                width={barW}
                height={Math.max(0, yBar(-(costo[i] + gasto[i])) - yCosto)}
                className="fill-gasto"
              />
            </g>
          );
        })}

        {/* ── Panel inferior: caja acumulada + umbral ── */}
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

        {/* umbral (línea punteada sobre el eje de la caja) */}
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
          umbral
        </text>

        {/* línea de caja acumulada */}
        <polyline
          points={lineaCaja}
          fill="none"
          className="stroke-cyan"
          strokeWidth={2.5}
          vectorEffect="non-scaling-stroke"
        />

        {/* etiquetas del eje X — COMPARTIDAS, en la banda inferior (no invaden el pie) */}
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
            y={topY0}
            width={slot}
            height={botY0 + botH - topY0}
            fill="transparent"
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover((h) => (h === i ? null : h))}
          />
        ))}
      </svg>

      {/* leyenda (el color nunca va solo — F1). Fuera del SVG, en la columna flex, para
          que SIEMPRE quepa (ítem 7) sin empujar contra el pie de la tarjeta (ítem 4). */}
      <div className="mt-1 flex shrink-0 flex-wrap items-center gap-x-4 gap-y-1 px-2 text-apoyo text-ink-soft">
        <Clave className="bg-positivo/80" label="Ingreso" />
        <Clave className="bg-costo" label="Costo" />
        <Clave className="bg-gasto" label="Gasto" />
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
      className="pointer-events-none absolute top-2 z-20 w-60 rounded-lg border border-hairline bg-surface p-3 text-apoyo shadow-lg"
      style={izq ? { right: `${100 - leftPct}%` } : { left: `${leftPct}%` }}
    >
      <div className="mb-1 font-semibold text-ink">{p.etiqueta}</div>

      <Fila etiqueta="Ingreso" valor={formatCOPEntero(p.ingreso)} />
      {/* ítem 1 — ingreso discriminado */}
      <Sub etiqueta="Recaudo semanal" valor={formatCOPEntero(p.recaudo)} />
      <Sub etiqueta="Cuota inicial" valor={formatCOPEntero(p.inicial)} />

      <Fila etiqueta="Costo" valor={formatCOPEntero(p.costo)} />
      {/* ítem 2 — costo discriminado */}
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
