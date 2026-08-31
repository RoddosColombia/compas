// CurvaCajaRV2 — RV-V2 Fundacional §3, rebanada 1 (7 de 10 AC).
//
// LA gráfica principal de proyección, contra el mockup vinculante
// (`docs/design-references/proyeccion-mockup.html · drawCash`).
//
// AC cubiertos por esta rebanada:
//   #1 · Real sólido, proyectado punteado, ancla marcada con su valor.
//   #2 · Dos umbrales dibujados (atención ámbar, crítico rojo) + valle sombreado
//        como zona con la duración rotulada.
//   #3 · Números en la gráfica: último real + fondo del valle (mes · monto).
//   #4 · Tooltip por mes (hover) con caja + desglose de composición.
//   #6 · Etiquetas del eje X cada 2 meses en la zona de proyección.
//   #9 · Color = solo estado (usa tokens RV-V1 --color-chart-*, --color-critico,
//        --color-atencion). Ninguna serie se distingue por color de estado.
//  #10 · Enlazada a los 23 campos reales de `MesProyeccion` — cero datos de
//        ejemplo.
//
// AC diferidos a rebanada 2: #5 (escenario superpuesto), #7 (motos editable),
// #8 (composición en gráfica propia).
//
// SVG inline (sin librería — Trivy gate pendiente). `.toNumber()` es SOLO
// geometría de presentación (misma restricción que CashCurve): montos como
// string en props, formato con `formatCOP*`, cálculos financieros en backend.

import { useMemo, useState } from "react";

import {
  formatCOP,
  formatCOPCompact,
  formatMesCorto,
  parseMonto,
} from "@/lib/money";
import type { MesProyeccion, Proyeccion } from "@/lib/proyeccion";

// ─────────────────────────── geometría del viewBox ───────────────────────────
const W = 960;
const H = 320;
// Padding interior: izquierda para etiquetas Y compactas ("$500M"), derecha
// para etiquetas de umbral ("atención"), arriba/abajo para textos anotados.
const PAD = { top: 20, right: 96, bottom: 36, left: 42 } as const;
const X0 = PAD.left;
const X1 = W - PAD.right;
const Y0 = PAD.top;
const Y1 = H - PAD.bottom;

// ─────────────────────────── util (puros) ───────────────────────────

/** Paso "bonito" para las marcas del eje Y — potencia de 10 ajustada a 1/2/5.
 * Igual que niceStep del mockup, pero sin float ambiguo (entrada como número). */
function niceStep(max: number): number {
  if (max <= 0) return 1;
  const pow = 10 ** Math.floor(Math.log10(max));
  const rel = max / pow;
  if (rel < 2) return pow / 5; // 5 marcas
  if (rel < 5) return pow / 2;
  return pow;
}

/** Cadencia de etiquetas del eje X (AC #6). Real (0..ancla) siempre densa;
 * proyección (>ancla) según horizonte: ≤18m→2, ≤30m→3, >30m→6. */
function pasoEtiquetasProy(horizonte: number): number {
  if (horizonte <= 18) return 2;
  if (horizonte <= 30) return 3;
  return 6;
}

/** Índice del ancla = último mes de la ventana que aparece en `meses_anclados`
 * como cerrado o en_ejecucion. -1 si no hay ninguno (proyección pura). */
function indiceAncla(
  ventana: MesProyeccion[],
  meses_anclados: Proyeccion["meses_anclados"],
): number {
  if (!meses_anclados) return -1;
  let ultimo = -1;
  ventana.forEach((m, i) => {
    if (meses_anclados[m.mes]) ultimo = i;
  });
  return ultimo;
}

/** Rachas contiguas donde `caja < umbral` (AC #2). Devuelve `[i0, i1]` inclusivos.
 * Solo miramos la parte de PROYECCIÓN (i > ancla): un mes ya cerrado ya no es
 * un valle "por venir". */
function rachasValle(
  ventana: MesProyeccion[],
  ancla: number,
  umbral: number,
): [number, number][] {
  const rachas: [number, number][] = [];
  let inicio = -1;
  for (let i = Math.max(0, ancla); i < ventana.length; i++) {
    const bajo = parseMonto(ventana[i].caja).toNumber() < umbral;
    if (bajo && inicio === -1) inicio = i;
    if (!bajo && inicio !== -1) {
      rachas.push([inicio, i - 1]);
      inicio = -1;
    }
  }
  if (inicio !== -1) rachas.push([inicio, ventana.length - 1]);
  return rachas;
}

/** Índice del piso (mín caja) dentro de la parte de proyección. Es el "fondo
 * del valle" del AC #3; con ancla=-1 (proyección pura) miramos todo. */
function indicePiso(ventana: MesProyeccion[], ancla: number): number {
  let piso = Number.POSITIVE_INFINITY;
  let idx = -1;
  const desde = Math.max(0, ancla);
  for (let i = desde; i < ventana.length; i++) {
    const v = parseMonto(ventana[i].caja).toNumber();
    if (v < piso) {
      piso = v;
      idx = i;
    }
  }
  return idx;
}

interface CurvaCajaRV2Props {
  data: Proyeccion;
  /** Ventana visible (número de meses desde el arranque). Default = todos. */
  ventanaMeses?: number;
  /** Test hook: fija hoy para determinismo. */
  hoyMes?: string;
  /** RV-V2 rebanada 3 · AC #5 · Escenario superpuesto: base + escenario con
   * ÁREA rellena entre ambos. Se dibuja como línea punteada verde encima de
   * la proyección base. Cuando llega, la etiqueta del ancla no se mueve —
   * el ancla es del RESULTADO REAL, no del escenario. */
  escenarioData?: Proyeccion;
}

interface Tooltip {
  idx: number;
  x: number;
  y: number;
}

// ─────────────────────────── componente ───────────────────────────

export function CurvaCajaRV2({
  data,
  ventanaMeses,
  escenarioData,
}: CurvaCajaRV2Props) {
  const [tooltip, setTooltip] = useState<Tooltip | null>(null);

  const {
    ventana,
    ancla,
    piso,
    umbralCritico,
    umbralAtencion,
    marcas,
    xPos,
    yPos,
    rachas,
    pathReal,
    pathProy,
    pathEscenario,
    pathAreaEscenario,
    xLabels,
  } = useMemo(() => {
    const ventana = data.meses.slice(
      0,
      ventanaMeses ?? data.meses.length,
    );
    const umbralCritico = parseMonto(data.caja_minima).toNumber();
    const umbralAtencion = data.caja_atencion
      ? parseMonto(data.caja_atencion).toNumber()
      : null;
    const ancla = indiceAncla(ventana, data.meses_anclados);

    // vmax: escalado con 8% de holgura arriba (como el mockup). Cuando hay
    // escenario superpuesto, escala hasta el mayor de los dos para que ninguna
    // curva se recorte arriba.
    const cajas = ventana.map((m) => parseMonto(m.caja).toNumber());
    const cajasEsc = escenarioData
      ? escenarioData.meses
          .slice(0, ventana.length)
          .map((m) => parseMonto(m.caja).toNumber())
      : [];
    const vmax = Math.max(umbralCritico, ...cajas, ...cajasEsc) * 1.08;

    const xPos = (j: number): number =>
      X0 + ((X1 - X0) * j) / Math.max(1, ventana.length - 1);
    const yPos = (v: number): number => Y1 - ((Y1 - Y0) * v) / vmax;

    // Marcas del eje Y (grid horizontal): 0, step, 2*step, ...
    const step = niceStep(vmax);
    const marcas: number[] = [];
    for (let g = 0; g <= vmax; g += step) marcas.push(g);

    // Rachas del valle: preferir umbral de atención si existe (RF-F3),
    // sino crítico.
    const umbralValle = umbralAtencion ?? umbralCritico;
    const rachas = rachasValle(ventana, ancla, umbralValle);

    const piso = indicePiso(ventana, ancla);

    // Paths: real sólido hasta ANCLA (inclusive), proyección punteada
    // desde ANCLA (inclusive, para que empalmen visualmente sin gap).
    const realHasta = ancla >= 0 ? ancla : -1;
    const desdeProy = ancla >= 0 ? ancla : 0;
    const puntoPath = (i: number): string =>
      `${xPos(i).toFixed(1)},${yPos(cajas[i]).toFixed(1)}`;
    const pathReal =
      realHasta >= 0
        ? "M " +
          Array.from({ length: realHasta + 1 }, (_, i) => puntoPath(i)).join(
            " L ",
          )
        : "";
    const pathProy =
      desdeProy < ventana.length
        ? "M " +
          Array.from(
            { length: ventana.length - desdeProy },
            (_, k) => puntoPath(desdeProy + k),
          ).join(" L ")
        : "";

    // AC #5 · escenario superpuesto: línea punteada verde + ÁREA rellena entre
    // base y escenario. Solo la parte proyectada (desde el ancla): la real no
    // cambia con el escenario. Sin escenarioData, ambos paths quedan vacíos.
    let pathEscenario = "";
    let pathAreaEscenario = "";
    if (escenarioData && cajasEsc.length > 0) {
      const desde = Math.max(0, ancla);
      const nProy = ventana.length - desde;
      if (nProy > 0) {
        const puntoEsc = (i: number): string =>
          `${xPos(i).toFixed(1)},${yPos(cajasEsc[i]).toFixed(1)}`;
        pathEscenario =
          "M " +
          Array.from({ length: nProy }, (_, k) => puntoEsc(desde + k)).join(
            " L ",
          );
        // Área entre base y escenario: polígono cerrado — sube por la base y
        // baja por el escenario en orden inverso.
        const idsUp = Array.from({ length: nProy }, (_, k) => desde + k);
        const idsDown = [...idsUp].reverse();
        pathAreaEscenario =
          "M " +
          idsUp.map((i) => puntoPath(i)).join(" L ") +
          " L " +
          idsDown.map((i) => puntoEsc(i)).join(" L ") +
          " Z";
      }
    }

    // Etiquetas eje X (AC #6): en la parte real, cada 2 meses; en la proyección,
    // paso según horizonte. El ancla siempre está etiquetada.
    const paso = pasoEtiquetasProy(ventana.length);
    const xLabels: number[] = [];
    ventana.forEach((_m, i) => {
      const esAncla = i === ancla;
      const enReal = ancla >= 0 && i <= ancla && i % 2 === 0;
      const enProy = i > ancla && (i - Math.max(ancla, 0)) % paso === 0;
      if (esAncla || enReal || enProy) xLabels.push(i);
    });

    return {
      ventana,
      ancla,
      piso,
      umbralCritico,
      umbralAtencion,
      vmax,
      marcas,
      xPos,
      yPos,
      rachas,
      pathReal,
      pathProy,
      pathEscenario,
      pathAreaEscenario,
      xLabels,
    };
  }, [data, ventanaMeses, escenarioData]);

  if (ventana.length === 0) {
    return (
      <p className="font-sans text-cuerpo text-ink-soft">
        Sin datos para dibujar la proyección.
      </p>
    );
  }

  const cajaFormato = (i: number): string =>
    formatCOP(ventana[i].caja);

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label="Curva de caja proyectada: real sólido, proyectado punteado, umbrales de atención y crítico, valle sombreado."
        className="w-full h-auto"
        onMouseLeave={() => setTooltip(null)}
      >
        <title>Curva de caja · RV-V2</title>

        {/* fondo del plot */}
        <rect
          x={X0}
          y={Y0}
          width={X1 - X0}
          height={Y1 - Y0}
          fill="var(--color-surface)"
          rx={6}
        />

        {/* grid horizontal + etiquetas Y compactas */}
        {marcas.map((g) => (
          <g key={`gy-${g}`}>
            <line
              x1={X0}
              y1={yPos(g)}
              x2={X1}
              y2={yPos(g)}
              stroke="var(--color-hairline)"
              strokeWidth={1}
            />
            <text
              x={X0 - 4}
              y={yPos(g) + 3}
              fill="var(--color-ink-faint)"
              fontSize={10}
              textAnchor="end"
              className="font-display tabular"
            >
              {formatCOPCompact(String(g))}
            </text>
          </g>
        ))}

        {/* AC #2: bandas del valle (rojo tenue) + rótulo con duración */}
        {rachas.map(([i0, i1]) => {
          const bx0 = i0 > 0 ? (xPos(i0) + xPos(i0 - 1)) / 2 : xPos(i0) - 6;
          const bx1 =
            i1 < ventana.length - 1
              ? (xPos(i1) + xPos(i1 + 1)) / 2
              : xPos(i1) + 6;
          const n = i1 - i0 + 1;
          return (
            <g key={`valle-${i0}-${i1}`}>
              <rect
                x={bx0}
                y={Y0}
                width={bx1 - bx0}
                height={Y1 - Y0}
                fill="var(--color-critico)"
                fillOpacity={0.07}
              />
              <text
                x={(bx0 + bx1) / 2}
                y={Y0 + 12}
                fill="var(--color-critico)"
                fontSize={10}
                fontWeight={600}
                textAnchor="middle"
                className="font-display"
              >
                {`valle · ${n} ${n === 1 ? "mes" : "meses"}`}
              </text>
            </g>
          );
        })}

        {/* AC #2: dos umbrales dibujados */}
        {umbralAtencion !== null && (
          <g>
            <line
              x1={X0}
              y1={yPos(umbralAtencion)}
              x2={X1}
              y2={yPos(umbralAtencion)}
              stroke="var(--color-atencion)"
              strokeWidth={1.4}
              strokeDasharray="2 3"
            />
            <text
              x={X1 + 4}
              y={yPos(umbralAtencion) - 2}
              fill="var(--color-atencion)"
              fontSize={10}
              className="font-display"
            >
              atención
            </text>
            <text
              x={X1 + 4}
              y={yPos(umbralAtencion) + 10}
              fill="var(--color-atencion)"
              fontSize={9}
              className="font-display tabular"
            >
              {formatCOPCompact(data.caja_atencion ?? "0")}
            </text>
          </g>
        )}
        <g>
          <line
            x1={X0}
            y1={yPos(umbralCritico)}
            x2={X1}
            y2={yPos(umbralCritico)}
            stroke="var(--color-critico)"
            strokeWidth={1}
            strokeDasharray="4 3"
          />
          <text
            x={X1 + 4}
            y={yPos(umbralCritico) + 3}
            fill="var(--color-critico)"
            fontSize={10}
            className="font-display"
          >
            crítico
          </text>
        </g>

        {/* AC #5: escenario superpuesto (base + escenario con área coloreada).
            Se dibuja DEBAJO de las curvas para que el trazo principal domine
            visualmente y el escenario refuerce con la mancha. */}
        {pathAreaEscenario && (
          <path
            d={pathAreaEscenario}
            fill="var(--color-chart-escenario)"
            fillOpacity={0.12}
            stroke="none"
            data-testid="area-escenario"
          />
        )}
        {pathEscenario && (
          <path
            d={pathEscenario}
            fill="none"
            stroke="var(--color-chart-escenario)"
            strokeWidth={2}
            strokeDasharray="4 3"
            strokeLinejoin="round"
            strokeLinecap="round"
            data-testid="curva-escenario"
          />
        )}

        {/* AC #1: real sólido */}
        {pathReal && (
          <path
            d={pathReal}
            fill="none"
            stroke="var(--color-chart-real)"
            strokeWidth={2.6}
            strokeLinejoin="round"
            strokeLinecap="round"
            data-testid="curva-real"
          />
        )}
        {/* AC #1: proyección punteada */}
        {pathProy && (
          <path
            d={pathProy}
            fill="none"
            stroke="var(--color-chart-proyectado)"
            strokeWidth={2}
            strokeDasharray="6 4"
            strokeLinejoin="round"
            strokeLinecap="round"
            data-testid="curva-proyectada"
          />
        )}

        {/* AC #1 + #3: círculos + ancla + texto "último real" */}
        {ancla >= 0 &&
          Array.from({ length: ancla + 1 }, (_, i) => (
            <circle
              key={`p-${i}`}
              cx={xPos(i)}
              cy={yPos(parseMonto(ventana[i].caja).toNumber())}
              r={2.6}
              fill="var(--color-chart-real)"
            />
          ))}
        {ancla >= 0 && (
          <g data-testid="ancla">
            <circle
              cx={xPos(ancla)}
              cy={yPos(parseMonto(ventana[ancla].caja).toNumber())}
              r={4.5}
              fill="none"
              stroke="var(--color-chart-real)"
              strokeWidth={2}
            />
            <text
              x={xPos(ancla)}
              y={yPos(parseMonto(ventana[ancla].caja).toNumber()) - 12}
              fill="var(--color-ink)"
              fontSize={10.5}
              fontWeight={600}
              textAnchor="middle"
              className="font-display tabular"
              data-testid="ancla-monto"
            >
              {formatCOPCompact(ventana[ancla].caja)}
            </text>
            <text
              x={xPos(ancla)}
              y={yPos(parseMonto(ventana[ancla].caja).toNumber()) - 25}
              fill="var(--color-ink-faint)"
              fontSize={9}
              textAnchor="middle"
              className="font-display"
            >
              último real
            </text>
          </g>
        )}

        {/* AC #3: fondo del valle (mes · monto) — solo si perfora la referencia */}
        {piso >= 0 &&
          parseMonto(ventana[piso].caja).toNumber() <
            (umbralAtencion ?? umbralCritico) && (
            <g data-testid="fondo-valle">
              <circle
                cx={xPos(piso)}
                cy={yPos(parseMonto(ventana[piso].caja).toNumber())}
                r={4}
                fill="none"
                stroke="var(--color-critico)"
                strokeWidth={2}
              />
              <text
                x={
                  xPos(piso) > X1 - 150 ? xPos(piso) - 8 : xPos(piso) + 8
                }
                y={yPos(parseMonto(ventana[piso].caja).toNumber()) + 16}
                fill="var(--color-critico)"
                fontSize={10.5}
                fontWeight={600}
                textAnchor={xPos(piso) > X1 - 150 ? "end" : "start"}
                className="font-display tabular"
                data-testid="fondo-valle-rotulo"
              >
                {`${formatMesCorto(ventana[piso].mes)} · ${formatCOPCompact(
                  ventana[piso].caja,
                )}`}
              </text>
            </g>
          )}

        {/* AC #6: etiquetas del eje X */}
        {xLabels.map((i) => (
          <text
            key={`xl-${i}`}
            x={xPos(i)}
            y={Y1 + 16}
            fill="var(--color-ink-faint)"
            fontSize={9.5}
            textAnchor="middle"
            className="font-display tabular"
          >
            {formatMesCorto(ventana[i].mes)}
          </text>
        ))}

        {/* AC #4: capa transparente para hover-por-punto (tooltip) */}
        {ventana.map((m, i) => (
          <rect
            key={`hov-${i}`}
            x={xPos(i) - 12}
            y={Y0}
            width={24}
            height={Y1 - Y0}
            fill="transparent"
            onMouseEnter={() => setTooltip({ idx: i, x: xPos(i), y: 0 })}
            data-testid={`hover-${m.mes}`}
          />
        ))}
      </svg>

      {/* AC #4: tooltip HTML posicionado por %. Simple; RV-V3 lo pulirá. */}
      {tooltip !== null && (
        <div
          role="tooltip"
          data-testid="curva-tooltip"
          className="pointer-events-none absolute rounded-md border border-hairline bg-surface p-2 font-sans text-apoyo shadow-md"
          style={{
            left: `${(tooltip.x / W) * 100}%`,
            top: "10px",
            transform: "translateX(-50%)",
          }}
        >
          <div className="font-semibold text-ink">
            {formatMesCorto(ventana[tooltip.idx].mes)}
          </div>
          <div className="tabular text-ink-soft">
            caja: {cajaFormato(tooltip.idx)}
          </div>
          <div className="mt-1 text-ink-faint">
            <div>ingreso: {formatCOP(ventana[tooltip.idx].ingreso_bruto)}</div>
            <div>egresos: {formatCOP(ventana[tooltip.idx].egresos)}</div>
            <div>flujo: {formatCOP(ventana[tooltip.idx].flujo)}</div>
          </div>
        </div>
      )}
    </div>
  );
}
