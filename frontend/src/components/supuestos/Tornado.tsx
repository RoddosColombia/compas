// Tornado — C3 §3: "¿Qué mueve mi umbral?". Barras horizontales por variable,
// ordenadas por |impacto| en pesos desc, con el delta etiquetado y una frase de
// conclusión arriba. Los datos vienen del endpoint de sensibilidad — cero
// cálculo financiero aquí (solo restas de presentación con decimal.js).
// Recupera la idea de sensibilidad del artefacto de referencia.

import type Decimal from "decimal.js-light";

import { Card, CardTitle } from "@/components/ui/card";
import { formatCOP, formatCOPCompact, parseMonto } from "@/lib/money";
import type { Sensibilidad } from "@/lib/parametros";

interface Fila {
  etiqueta: string;
  variacion: string;
  /** piso(variación +) − piso base (puede ser negativo) */
  dMas: Decimal;
  /** piso(variación −) − piso base */
  dMenos: Decimal;
  magnitud: Decimal;
}

export function ordenarTornado(data: Sensibilidad): Fila[] {
  const base = parseMonto(data.piso_base);
  return data.variables
    .map((v) => {
      const dMas = parseMonto(v.piso_mas).minus(base);
      const dMenos = parseMonto(v.piso_menos).minus(base);
      const magnitud = dMas.abs().greaterThan(dMenos.abs())
        ? dMas.abs()
        : dMenos.abs();
      return {
        etiqueta: v.etiqueta,
        variacion: v.variacion,
        dMas,
        dMenos,
        magnitud,
      };
    })
    .sort((a, b) => b.magnitud.comparedTo(a.magnitud));
}

export function Tornado({ data }: { data: Sensibilidad }) {
  const filas = ordenarTornado(data);
  if (filas.length === 0) return null;
  const maxMag = filas[0].magnitud;
  const top = filas.slice(0, 2).map((f) => f.etiqueta.toLowerCase());

  return (
    <Card className="flex flex-col gap-3 p-5">
      <div>
        <CardTitle>¿Qué mueve mi umbral?</CardTitle>
        <p className="mt-0.5 font-sans text-cuerpo text-ink-soft">
          Tu piso de caja depende sobre todo de {top[0]}
          {top[1] ? ` y de ${top[1]}` : ""}.
        </p>
        <p className="font-sans text-apoyo text-ink-faint">
          piso base{" "}
          <span className="tabular" title={formatCOP(data.piso_base)}>
            {formatCOPCompact(data.piso_base)}
          </span>{" "}
          · escenario {data.escenario} · {data.horizonte_meses} meses
        </p>
      </div>

      <ol className="flex flex-col gap-2.5">
        {filas.map((f) => {
          const pct = maxMag.isZero()
            ? 0
            : Math.min(
                100,
                Number(f.magnitud.div(maxMag).times(100).toDecimalPlaces(0)),
              );
          return (
            <li key={f.etiqueta} className="font-sans text-cuerpo">
              <div className="mb-0.5 flex items-baseline justify-between gap-3">
                <span className="text-ink">
                  {f.etiqueta}{" "}
                  <span className="text-apoyo text-ink-faint">
                    {f.variacion}
                  </span>
                </span>
                <span className="tabular text-apoyo text-ink-soft">
                  piso {rangoTexto(f)}
                </span>
              </div>
              <div className="h-2.5 overflow-hidden rounded-full bg-surface-muted">
                <div
                  data-testid={`barra-${f.etiqueta}`}
                  className="h-full rounded-full bg-atencion"
                  style={{ width: `${pct}%` }}
                />
              </div>
            </li>
          );
        })}
      </ol>
    </Card>
  );
}

function rangoTexto(f: Fila): string {
  // "±$ 54 M" cuando es ~simétrico; "-$ 54 M / +$ 48 M" cuando no.
  const peor = f.dMas.isNegative() ? f.dMas : f.dMenos;
  const mejor = f.dMas.isNegative() ? f.dMenos : f.dMas;
  const pc = formatCOPCompact(peor.abs());
  const mc = formatCOPCompact(mejor.abs());
  if (pc === mc) return `±${pc}`;
  return `−${pc} / +${mc}`;
}
