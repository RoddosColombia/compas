// PanelImpacto — la joya de C3 §2: VIGENTE → CON TUS CAMBIOS, lado a lado,
// ANTES de guardar. Recibe la proyección vigente y la del preview (compute-only)
// y muestra piso, mes crítico, meses bajo mínimo y capital con deltas F1, más
// una mini curva de dos trazos (vigente tenue + propuesto en cyan) a 18 meses.
// Si el preview falla o está calculando: skeleton/aviso — NUNCA cifras viejas
// sin marcar. Montos string + decimal.js (regla 1); cero cálculo financiero
// más allá de restas de presentación.

import { AlertBanner } from "@/components/ui/alert-banner";
import { Card, CardTitle } from "@/components/ui/card";
import { Cargando } from "@/components/ui/cargando";
import {
  formatCOP,
  formatCOPCompact,
  formatDelta,
  formatMesCorto,
  parseMonto,
} from "@/lib/money";
import type { Proyeccion } from "@/lib/proyeccion";
import { mesAIndice } from "@/lib/unidades";
import { cn } from "@/lib/utils";

const VENTANA_CURVA = 18;

export function PanelImpacto({
  vigente,
  propuesto,
  calculando,
  error,
  hayCambios,
}: {
  vigente: Proyeccion | undefined;
  propuesto: Proyeccion | undefined;
  calculando: boolean;
  error: boolean;
  hayCambios: boolean;
}) {
  return (
    <Card className="flex flex-col gap-3 p-5">
      <CardTitle>Impacto de tus cambios</CardTitle>

      {!hayCambios && (
        <p className="font-sans text-cuerpo text-ink-soft">
          Cambia un supuesto y aquí verás su efecto — piso de caja, mes crítico
          y capital requerido — antes de guardar nada.
        </p>
      )}

      {hayCambios && error && (
        <AlertBanner variant="warn">
          No se pudo calcular el impacto (el borrador no se pierde). Corrige el
          campo marcado o reintenta cambiando cualquier valor.
        </AlertBanner>
      )}

      {hayCambios && !error && (calculando || !propuesto || !vigente) && (
        <Cargando variante="tabla" />
      )}

      {hayCambios && !error && !calculando && propuesto && vigente && (
        <>
          <div className="grid grid-cols-[1fr_auto_auto] items-baseline gap-x-4 gap-y-2 font-sans text-cuerpo">
            <span className="text-apoyo tracking-wide text-ink-faint uppercase">
              Indicador
            </span>
            <span className="text-right text-apoyo tracking-wide text-ink-faint uppercase">
              Vigente
            </span>
            <span className="text-right text-apoyo tracking-wide text-ink-faint uppercase">
              Con tus cambios
            </span>

            <FilaMonto
              label="Piso de caja"
              vigente={vigente.piso_caja}
              propuesto={propuesto.piso_caja}
            />
            <FilaMesCritico vigente={vigente} propuesto={propuesto} />
            <FilaTexto
              label="Meses bajo mínimo"
              vigente={`${vigente.meses_bajo_minimo} de ${vigente.meses.length}`}
              propuesto={`${propuesto.meses_bajo_minimo} de ${propuesto.meses.length}`}
              peor={propuesto.meses_bajo_minimo > vigente.meses_bajo_minimo}
            />
            <FilaMonto
              label="Capital requerido"
              vigente={vigente.capital_requerido}
              propuesto={propuesto.capital_requerido}
              menorEsMejor
            />
          </div>

          <MiniComparativa vigente={vigente} propuesto={propuesto} />
          <p className="font-sans text-apoyo text-ink-faint">
            Caja a {VENTANA_CURVA} meses: trazo tenue = vigente · cyan = con tus
            cambios. Nada se guarda hasta que confirmes.
          </p>
        </>
      )}
    </Card>
  );
}

function FilaMonto({
  label,
  vigente,
  propuesto,
  menorEsMejor = false,
}: {
  label: string;
  vigente: string;
  propuesto: string;
  menorEsMejor?: boolean;
}) {
  const delta = parseMonto(propuesto).minus(parseMonto(vigente));
  const d = formatDelta(delta);
  const mejora = menorEsMejor
    ? delta.isNegative()
    : delta.greaterThan(0) || delta.isZero();
  return (
    <>
      <span className="text-ink">{label}</span>
      <span
        className="tabular text-right text-ink-soft"
        title={formatCOP(vigente)}
      >
        {formatCOPCompact(vigente)}
      </span>
      <span className="text-right">
        <span
          className="tabular font-semibold text-ink"
          title={formatCOP(propuesto)}
        >
          {formatCOPCompact(propuesto)}
        </span>{" "}
        {!delta.isZero() && (
          <span
            className={cn(
              "tabular text-apoyo font-semibold",
              mejora ? "text-positivo" : "text-critico",
            )}
          >
            {d.texto}
          </span>
        )}
      </span>
    </>
  );
}

function FilaMesCritico({
  vigente,
  propuesto,
}: {
  vigente: Proyeccion;
  propuesto: Proyeccion;
}) {
  const corrimiento =
    vigente.meses_bajo_minimo > 0 && propuesto.meses_bajo_minimo > 0
      ? mesAIndice(propuesto.mes_mas_ajustado, vigente.mes_mas_ajustado)
      : null;
  return (
    <>
      <span className="text-ink">Mes crítico</span>
      <span className="tabular text-right text-ink-soft">
        {vigente.meses_bajo_minimo > 0
          ? formatMesCorto(vigente.mes_mas_ajustado)
          : "—"}
      </span>
      <span className="text-right">
        <span className="tabular font-semibold text-ink">
          {propuesto.meses_bajo_minimo > 0
            ? formatMesCorto(propuesto.mes_mas_ajustado)
            : "—"}
        </span>{" "}
        {corrimiento !== null && corrimiento !== 0 && (
          <span className="text-apoyo text-ink-soft">
            (se corre {Math.abs(corrimiento)}{" "}
            {Math.abs(corrimiento) === 1 ? "mes" : "meses"})
          </span>
        )}
      </span>
    </>
  );
}

function FilaTexto({
  label,
  vigente,
  propuesto,
  peor,
}: {
  label: string;
  vigente: string;
  propuesto: string;
  peor: boolean;
}) {
  return (
    <>
      <span className="text-ink">{label}</span>
      <span className="tabular text-right text-ink-soft">{vigente}</span>
      <span
        className={cn(
          "tabular text-right font-semibold",
          peor ? "text-critico" : "text-ink",
        )}
      >
        {propuesto}
      </span>
    </>
  );
}

/** Dos trazos a 18 meses: vigente (tenue) vs propuesto (cyan). SVG puro;
 * .toNumber() SOLO geometría de presentación, como CashCurve. */
function MiniComparativa({
  vigente,
  propuesto,
}: {
  vigente: Proyeccion;
  propuesto: Proyeccion;
}) {
  const a = vigente.meses.slice(0, VENTANA_CURVA);
  const b = propuesto.meses.slice(0, VENTANA_CURVA);
  if (a.length < 2 || b.length < 2) return null;
  const W = 600;
  const H = 120;
  const P = 8;
  const va = a.map((m) => parseMonto(m.caja).toNumber());
  const vb = b.map((m) => parseMonto(m.caja).toNumber());
  const u = parseMonto(vigente.caja_minima).toNumber();
  const min = Math.min(...va, ...vb, u);
  const max = Math.max(...va, ...vb, u);
  const span = max - min || 1;
  const x = (i: number, n: number) => (i / (n - 1)) * W;
  const y = (v: number) => P + (1 - (v - min) / span) * (H - 2 * P);
  const linea = (vals: number[]) =>
    vals.map((v, i) => `${x(i, vals.length)},${y(v)}`).join(" ");
  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="h-28 w-full"
      preserveAspectRatio="none"
      role="img"
      aria-label="Caja vigente vs. con tus cambios (18 meses)"
    >
      <title>Vigente vs. propuesto</title>
      <line
        x1={0}
        x2={W}
        y1={y(u)}
        y2={y(u)}
        className="stroke-critico"
        strokeWidth={1}
        strokeDasharray="5 4"
      />
      <polyline
        points={linea(va)}
        fill="none"
        className="stroke-ink-decor"
        strokeWidth={2}
        vectorEffect="non-scaling-stroke"
      />
      <polyline
        points={linea(vb)}
        fill="none"
        className="stroke-cyan"
        strokeWidth={2.5}
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}
