// QueExigeAtencion — el control que prioriza (C2 pieza 3): desvíos ordenados
// por plata, no tabla alfabética. Con los datos que YA devuelve vistaControl:
//   1. Sobre-ejecutados (disponible < 0), por |disponible| desc.
//   2. En riesgo: consumo desproporcionado al calendario —
//      pct_ejecutado > pct_mes_transcurrido + UMBRAL_RIESGO_PTS — ordenados por
//      el exceso en pesos sobre el ritmo calendario.
// Los montos se comparan con decimal.js (regla 1); los PORCENTAJES no son
// montos y pueden ser number. Si no hay nada mal, el silencio también informa.

import type Decimal from "decimal.js-light";
import { Link } from "react-router-dom";

import { Card, CardTitle } from "@/components/ui/card";
import type { ControlGrupo, ControlLinea } from "@/lib/control";
import { formatCOP, parseMonto } from "@/lib/money";

// Puntos porcentuales de tolerancia sobre el ritmo del calendario antes de
// marcar una línea "en riesgo" (heurística C2; el run-rate real es C2.1/C3).
const UMBRAL_RIESGO_PTS = 15;

/** % del mes transcurrido (día de hoy / días del mes). No toca montos → number. */
export function pctMesTranscurrido(
  mes7: string,
  hoy: Date = new Date(),
): number {
  const [y, m] = mes7.split("-").map(Number);
  const actual = hoy.getFullYear() * 12 + (hoy.getMonth() + 1);
  const objetivo = y * 12 + m;
  if (objetivo < actual) return 100; // mes pasado: calendario completo
  if (objetivo > actual) return 0; // mes futuro: aún no arranca
  const diasMes = new Date(y, m, 0).getDate();
  return (hoy.getDate() / diasMes) * 100;
}

export interface ItemAtencion {
  rubro_id: string;
  rubro: string;
  tipo: "sobre" | "riesgo";
  mensaje: string;
  /** magnitud en pesos para ordenar (|disponible| o exceso vs. calendario) */
  magnitud: Decimal;
}

/** Desvíos priorizados: sobre-ejecutados primero, luego en riesgo; cada tier
 * ordenado por magnitud en pesos descendente. */
export function calcularAtencion(
  grupos: ControlGrupo[],
  pctMes: number,
): ItemAtencion[] {
  const lineas: ControlLinea[] = grupos.flatMap((g) => g.lineas);
  const sobre: ItemAtencion[] = [];
  const riesgo: ItemAtencion[] = [];

  for (const l of lineas) {
    const disponible = parseMonto(l.disponible);
    if (disponible.isNegative()) {
      sobre.push({
        rubro_id: l.rubro_id,
        rubro: l.rubro,
        tipo: "sobre",
        magnitud: disponible.abs(),
        mensaje: `«${l.rubro}» se pasó ${formatCOP(disponible.abs())}${
          l.pct_ejecutado !== null
            ? ` (${l.pct_ejecutado} % del presupuesto)`
            : ""
        }`,
      });
      continue;
    }
    // % es porcentaje, no monto → comparación con number es válida aquí.
    if (
      l.pct_ejecutado !== null &&
      Number(l.pct_ejecutado) > pctMes + UMBRAL_RIESGO_PTS
    ) {
      const definido = parseMonto(l.definido);
      const ritmoCalendario = definido.times(pctMes).div(100);
      riesgo.push({
        rubro_id: l.rubro_id,
        rubro: l.rubro,
        tipo: "riesgo",
        magnitud: parseMonto(l.ejecutado).minus(ritmoCalendario),
        mensaje: `«${l.rubro}» va al ${l.pct_ejecutado} % con el ${Math.round(pctMes)} % del mes transcurrido`,
      });
    }
  }

  const porMagnitud = (a: ItemAtencion, b: ItemAtencion) =>
    b.magnitud.comparedTo(a.magnitud);
  return [...sobre.sort(porMagnitud), ...riesgo.sort(porMagnitud)];
}

export function QueExigeAtencion({
  grupos,
  mes,
  max,
  conAnchors = false,
  hoy,
}: {
  grupos: ControlGrupo[];
  mes: string; // YYYY-MM
  /** recorta la lista (Cabina: top 5); sin límite en ControlPage */
  max?: number;
  /** en ControlPage los ítems anclan a la fila de la tabla (#rubro-<id>) */
  conAnchors?: boolean;
  /** inyectable para tests */
  hoy?: Date;
}) {
  const items = calcularAtencion(grupos, pctMesTranscurrido(mes, hoy));
  const visibles = max !== undefined ? items.slice(0, max) : items;

  return (
    <Card className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <CardTitle>Qué exige atención</CardTitle>
        {!conAnchors && (
          <Link
            to="/control"
            className="font-sans text-xs font-medium text-cyan hover:underline"
          >
            Ver el control completo →
          </Link>
        )}
      </div>

      {visibles.length === 0 ? (
        <p className="font-sans text-sm font-medium text-green">
          Todos los rubros en rango ✓
        </p>
      ) : (
        <ol className="flex flex-col gap-1.5">
          {visibles.map((it) => {
            const contenido = (
              <>
                <span
                  className={`mt-0.5 inline-block h-2 w-2 shrink-0 rounded-full ${
                    it.tipo === "sobre" ? "bg-red" : "bg-amber"
                  }`}
                />
                <span className="text-ink">{it.mensaje}</span>
              </>
            );
            return (
              <li key={it.rubro_id} className="font-sans text-sm">
                {conAnchors ? (
                  <a
                    href={`#rubro-${it.rubro_id}`}
                    className="flex items-start gap-2 rounded-md px-1 py-0.5 hover:bg-surface-muted"
                  >
                    {contenido}
                  </a>
                ) : (
                  <span className="flex items-start gap-2 px-1 py-0.5">
                    {contenido}
                  </span>
                )}
              </li>
            );
          })}
        </ol>
      )}

      {max !== undefined && items.length > max && (
        <p className="font-sans text-xs text-ink-faint">
          y {items.length - max} más en el control completo
        </p>
      )}
    </Card>
  );
}
