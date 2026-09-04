// ComposicionFlujoRV2 — RV-V2 Fundacional §3 AC #8.
//
// Composición del flujo en su gráfica PROPIA (no franja, regla 7 del DESIGN.md).
// Del mockup vinculante `docs/design-references/proyeccion-mockup.html · drawComp`.
//
// Un mes = un grupo de barras:
//   · Arriba del cero:  INGRESO NETO (verde = --color-chart-ingreso).
//   · Abajo del cero, apilado: GASTO FIJO (azul), AUTECO (fuchsia), OTROS (teal).
// Encima, la LÍNEA DE FLUJO NETO (ink, 55 % opacity). Línea del cero visible.
//
// Los 4 colores vienen de los TOKENS de RV-V1 (`--color-chart-*`) — cero hex
// hardcodeado. Los 4 conceptos son DISJUNTOS del semáforo (regla 9 del DESIGN.md).
//
// Mapping concepto → campo (los ≤0 vienen ya negativos en la API):
//   · ingreso     = ingreso_bruto
//   · gasto_fijo  = gastos_fijos
//   · auteco      = pago_inventario + adelanto + fondeo   (compras Auteco + interés)
//   · otros       = gps + costo_nueva + int_deuda + iva + aval
// Los agregamos por VALOR ABSOLUTO abajo, para apilar sin signos ambiguos.
// La línea de flujo neto es `flujo` tal cual del API — invariante del motor.

import { useMemo } from "react";

import { formatCOPCompact, formatMesCorto, parseMonto } from "@/lib/money";
import type { MesProyeccion } from "@/lib/proyeccion";

// Geometría (viewBox 960 × 300 del mockup).
const W = 960;
const H = 300;
const PAD = { top: 20, right: 96, bottom: 26, left: 44 } as const;
const X0 = PAD.left;
const X1 = W - PAD.right;

// ─────────────────────────── util ───────────────────────────

/** Paso "bonito" para el eje Y: potencia de 10 ajustada a 1/2/5. */
function niceStep(max: number): number {
  if (max <= 0) return 1;
  const pow = 10 ** Math.floor(Math.log10(max));
  const rel = max / pow;
  if (rel < 2) return pow / 5;
  if (rel < 5) return pow / 2;
  return pow;
}

/** Cadencia de etiquetas del eje X — misma regla que la curva principal. */
function pasoEtiquetas(horizonte: number): number {
  if (horizonte <= 18) return 2;
  if (horizonte <= 30) return 3;
  return 6;
}

/** Los 4 conceptos por mes, siempre ≥ 0 (se apilan sin signos). `flujo`
 * conserva su signo real — la línea del neto puede ir arriba o abajo del cero. */
interface Bloque {
  ingreso: number;
  gastoFijo: number;
  auteco: number;
  otros: number;
  flujo: number;
}

function bloqueDe(m: MesProyeccion): Bloque {
  const abs = (v: string): number => Math.abs(parseMonto(v).toNumber());
  const auteco = abs(m.pago_inventario) + abs(m.adelanto) + abs(m.fondeo);
  const otros =
    abs(m.gps) +
    abs(m.costo_nueva) +
    abs(m.int_deuda) +
    abs(m.iva) +
    abs(m.aval);
  return {
    ingreso: parseMonto(m.ingreso_bruto).toNumber(),
    gastoFijo: abs(m.gastos_fijos),
    auteco,
    otros,
    flujo: parseMonto(m.flujo).toNumber(),
  };
}

interface ComposicionFlujoRV2Props {
  meses: MesProyeccion[];
  /** Ventana visible (default = todos). */
  ventanaMeses?: number;
  /** RV-V4: escenario superpuesto. Si viene, dibuja la LÍNEA de flujo neto
   * del escenario como overlay dashed sobre --color-chart-escenario. Las
   * barras del BASE quedan intactas (evita el ruido de barras dobles/mes).
   * Se recorta a la misma ventana que `meses`. */
  escenarioMeses?: MesProyeccion[];
}

// ─────────────────────────── componente ───────────────────────────

export function ComposicionFlujoRV2({
  meses,
  ventanaMeses,
  escenarioMeses,
}: ComposicionFlujoRV2Props) {
  const {
    ventana,
    bloques,
    zero,
    xPos,
    up,
    dn,
    marcasPos,
    marcasNeg,
    bw,
    lineaFlujo,
    lineaFlujoEscenario,
    xLabels,
  } = useMemo(() => {
    const ventana = meses.slice(0, ventanaMeses ?? meses.length);
    const bloques = ventana.map(bloqueDe);
    // RV-V4: recortamos el escenario a la misma ventana. Los índices se
    // alinean por posición (el motor entrega ambos con la misma cadencia).
    const ventanaEscenario = escenarioMeses?.slice(0, ventana.length) ?? [];
    const bloquesEscenario = ventanaEscenario.map(bloqueDe);

    // Escala: max positivo (solo ingreso) y max negativo (suma de egresos apilados).
    // Cuando hay escenario, extendemos la escala para acomodar sus valores
    // (ingreso y flujo pueden ser mayores/menores que el base). El BASE se
    // sigue dibujando con la misma geometría — solo aumentamos el rango.
    let maxPos = 0;
    let maxNeg = 0;
    for (const b of bloques) {
      if (b.ingreso > maxPos) maxPos = b.ingreso;
      const totalNeg = b.gastoFijo + b.auteco + b.otros;
      if (totalNeg > maxNeg) maxNeg = totalNeg;
    }
    for (const b of bloquesEscenario) {
      if (b.ingreso > maxPos) maxPos = b.ingreso;
      if (b.flujo > maxPos) maxPos = b.flujo;
      if (-b.flujo > maxNeg) maxNeg = -b.flujo;
    }
    // Al menos algo para no dividir por cero cuando la ventana viene toda en 0.
    if (maxPos === 0) maxPos = 1;
    if (maxNeg === 0) maxNeg = 1;

    const alturaPlot = H - PAD.top - PAD.bottom;
    const span = maxPos + maxNeg;
    const zero = PAD.top + (alturaPlot * maxPos) / span;

    const xPos = (j: number): number =>
      X0 + ((X1 - X0) * j) / Math.max(1, ventana.length - 1);
    const up = (v: number): number => ((zero - PAD.top) * v) / maxPos;
    const dn = (v: number): number => ((H - PAD.bottom - zero) * v) / maxNeg;

    // Marcas del eje Y (ambos lados del cero). UN paso común para los dos lados:
    // así las líneas quedan simétricas y espaciadas, y no se amontonan con
    // densidades distintas (antes: 500 arriba vs 200 abajo). El cero NO lleva
    // etiqueta —la línea del cero ya lo marca— para descongestionar el centro.
    const step = niceStep(Math.max(maxPos, maxNeg));
    const marcasPos: number[] = [];
    for (let g = step; g <= maxPos; g += step) marcasPos.push(g);
    const marcasNeg: number[] = [];
    for (let g = step; g <= maxNeg; g += step) marcasNeg.push(g);

    // Ancho de barra: hasta 30 px, o el 62 % del espacio disponible por columna.
    const bw = Math.min(30, ((X1 - X0) / Math.max(1, ventana.length)) * 0.62);

    // Línea del flujo neto: y = zero - up(flujo) si ≥0; zero + dn(-flujo) si <0.
    const yFlujo = (v: number): number =>
      v >= 0 ? zero - up(v) : zero + dn(-v);
    const lineaFlujo =
      ventana.length > 0
        ? "M " +
          ventana
            .map(
              (_m, j) =>
                `${xPos(j).toFixed(1)},${yFlujo(bloques[j].flujo).toFixed(1)}`,
            )
            .join(" L ")
        : "";

    // RV-V4: mismo formato que la base, pero con los flujos del escenario.
    const lineaFlujoEscenario =
      ventanaEscenario.length >= 2
        ? "M " +
          ventanaEscenario
            .map(
              (_m, j) =>
                `${xPos(j).toFixed(1)},${yFlujo(bloquesEscenario[j].flujo).toFixed(1)}`,
            )
            .join(" L ")
        : "";

    // Etiquetas eje X — misma regla que la curva.
    const paso = pasoEtiquetas(ventana.length);
    const xLabels: number[] = [];
    ventana.forEach((_m, i) => {
      if (i % paso === 0) xLabels.push(i);
    });

    return {
      ventana,
      bloques,
      zero,
      maxPos,
      maxNeg,
      xPos,
      up,
      dn,
      marcasPos,
      marcasNeg,
      bw,
      lineaFlujo,
      lineaFlujoEscenario,
      xLabels,
    };
  }, [meses, ventanaMeses, escenarioMeses]);

  if (ventana.length === 0) {
    return (
      <p className="font-sans text-cuerpo text-ink-soft">
        Sin datos para dibujar la composición.
      </p>
    );
  }

  return (
    <div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label="Composición mensual del flujo: ingreso neto arriba, egresos por concepto abajo apilados, línea de flujo neto."
        className="w-full h-auto"
      >
        <title>Composición del flujo · RV-V2</title>

        {/* Grid + etiquetas Y positivas */}
        {marcasPos.map((g) => (
          <g key={`gp-${g}`}>
            <line
              x1={X0}
              y1={zero - up(g)}
              x2={X1}
              y2={zero - up(g)}
              stroke="var(--color-hairline)"
              strokeWidth={1}
            />
            <text
              x={X0 - 5}
              y={zero - up(g) + 3}
              fill="var(--color-ink-faint)"
              fontSize={9}
              textAnchor="end"
              className="font-display tabular"
            >
              {formatCOPCompact(String(g))}
            </text>
          </g>
        ))}
        {/* Grid + etiquetas Y negativas */}
        {marcasNeg.map((g) => (
          <g key={`gn-${g}`}>
            <line
              x1={X0}
              y1={zero + dn(g)}
              x2={X1}
              y2={zero + dn(g)}
              stroke="var(--color-hairline)"
              strokeWidth={1}
            />
            <text
              x={X0 - 5}
              y={zero + dn(g) + 3}
              fill="var(--color-ink-faint)"
              fontSize={9}
              textAnchor="end"
              className="font-display tabular"
            >
              -{formatCOPCompact(String(g))}
            </text>
          </g>
        ))}

        {/* Barras por mes: ingreso arriba, egresos apilados abajo */}
        {ventana.map((m, j) => {
          const b = bloques[j];
          const cx = xPos(j) - bw / 2;
          const alturaIng = up(b.ingreso);
          // Pila de egresos con separación mínima entre segmentos.
          const hGF = dn(b.gastoFijo);
          const hAut = dn(b.auteco);
          const hOtr = dn(b.otros);
          return (
            <g key={`bar-${m.mes}`} data-testid={`comp-bar-${m.mes}`}>
              <rect
                x={cx}
                y={zero - alturaIng}
                width={bw}
                height={alturaIng}
                fill="var(--color-chart-ingreso)"
                rx={1.5}
                data-testid={`bar-ingreso-${m.mes}`}
              />
              <rect
                x={cx}
                y={zero + 2}
                width={bw}
                height={Math.max(0, hGF - 2)}
                fill="var(--color-chart-gasto-fijo)"
                data-testid={`bar-gasto-fijo-${m.mes}`}
              />
              <rect
                x={cx}
                y={zero + 2 + hGF}
                width={bw}
                height={Math.max(0, hAut - 2)}
                fill="var(--color-chart-auteco)"
                data-testid={`bar-auteco-${m.mes}`}
              />
              <rect
                x={cx}
                y={zero + 2 + hGF + hAut}
                width={bw}
                height={Math.max(0, hOtr - 2)}
                fill="var(--color-chart-otros)"
                data-testid={`bar-otros-${m.mes}`}
              />
            </g>
          );
        })}

        {/* Línea de flujo neto (encima de las barras) */}
        <path
          d={lineaFlujo}
          fill="none"
          stroke="var(--color-ink)"
          strokeWidth={1.8}
          strokeOpacity={0.55}
          data-testid="linea-flujo-neto"
        />

        {/* RV-V4: escenario superpuesto — flujo neto del escenario dashed */}
        {lineaFlujoEscenario && (
          <path
            d={lineaFlujoEscenario}
            fill="none"
            stroke="var(--color-chart-escenario)"
            strokeWidth={1.8}
            strokeDasharray="4 3"
            data-testid="linea-flujo-escenario"
          />
        )}

        {/* Línea del cero (referencia visual clara del signo) */}
        <line
          x1={X0}
          y1={zero}
          x2={X1}
          y2={zero}
          stroke="var(--color-ink-soft)"
          strokeWidth={1.2}
        />

        {/* Etiquetas X */}
        {xLabels.map((i) => (
          <text
            key={`xl-${i}`}
            x={xPos(i)}
            y={H - 8}
            fill="var(--color-ink-faint)"
            fontSize={9.5}
            textAnchor="middle"
            className="font-display tabular"
          >
            {formatMesCorto(ventana[i].mes)}
          </text>
        ))}
      </svg>

      {/* Leyenda inline: los 4 conceptos + el neto. Cada concepto = un token. */}
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 font-sans text-apoyo text-ink-soft">
        <span className="flex items-center gap-1.5">
          <span
            aria-hidden
            className="inline-block h-2 w-3 rounded-sm"
            style={{ background: "var(--color-chart-ingreso)" }}
          />
          ingreso neto
        </span>
        <span className="flex items-center gap-1.5">
          <span
            aria-hidden
            className="inline-block h-2 w-3 rounded-sm"
            style={{ background: "var(--color-chart-gasto-fijo)" }}
          />
          gastos fijos
        </span>
        <span className="flex items-center gap-1.5">
          <span
            aria-hidden
            className="inline-block h-2 w-3 rounded-sm"
            style={{ background: "var(--color-chart-auteco)" }}
          />
          inventario Auteco
        </span>
        <span className="flex items-center gap-1.5">
          <span
            aria-hidden
            className="inline-block h-2 w-3 rounded-sm"
            style={{ background: "var(--color-chart-otros)" }}
          />
          otros egresos
        </span>
        <span className="flex items-center gap-1.5">
          <span
            aria-hidden
            className="inline-block h-[2px] w-4"
            style={{ background: "var(--color-ink)", opacity: 0.55 }}
          />
          flujo neto
        </span>
        {lineaFlujoEscenario && (
          <span className="flex items-center gap-1.5">
            <span
              aria-hidden
              className="inline-block h-[2px] w-4"
              style={{
                background:
                  "repeating-linear-gradient(to right, var(--color-chart-escenario) 0 4px, transparent 4px 7px)",
              }}
            />
            flujo neto · escenario
          </span>
        )}
      </div>
    </div>
  );
}
