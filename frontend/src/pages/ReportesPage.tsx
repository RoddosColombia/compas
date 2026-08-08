// frontend/src/pages/ReportesPage.tsx
//
// Reportes — resumen ejecutivo de la proyección de caja para junta/inversionistas,
// exportable a PDF (impresión del navegador; el @media print del index.css oculta
// el sidebar y los controles). Compone los tres escenarios del motor (C7) en un
// documento de una página. Montos con formatCOP (regla 1); el front solo presenta.

import { useQueries } from "@tanstack/react-query";
import { useState } from "react";

import { CashCurve } from "@/components/charts/CashCurve";
import { PageHeader } from "@/components/layout/PageHeader";
import { TitularJuicio } from "@/components/proyeccion/TitularJuicio";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { Cargando } from "@/components/ui/cargando";
import { ChartCard } from "@/components/ui/chart-card";
import { ErrorEstado } from "@/components/ui/error-estado";
import { KpiTileV2 } from "@/components/ui/kpi-tile";
import {
  formatCOP,
  formatCOPCompact,
  formatCOPEntero,
  formatDelta,
  formatMesCorto,
  parseMonto,
} from "@/lib/money";
import {
  type Escenario,
  type Proyeccion,
  obtenerProyeccion,
} from "@/lib/proyeccion";

const HORIZONTES = [12, 24, 36, 60, 120, 180];
const ESCENARIOS: { esc: Escenario; label: string }[] = [
  { esc: "pesimista", label: "Pesimista" },
  { esc: "base", label: "Base" },
  { esc: "optimista", label: "Optimista" },
];

export default function ReportesPage() {
  const [horizonte, setHorizonte] = useState(60);

  const resultados = useQueries({
    queries: ESCENARIOS.map((s) => ({
      queryKey: ["proyeccion", s.esc, horizonte],
      queryFn: () =>
        obtenerProyeccion({ escenario: s.esc, horizonteMeses: horizonte }),
    })),
  });

  const cargando = resultados.some((r) => r.isLoading);
  const error = resultados.every((r) => r.isError);
  const datos = resultados.map((r) => r.data);
  const listos = datos.every((d): d is Proyeccion => d !== undefined);
  const base = listos
    ? datos[ESCENARIOS.findIndex((s) => s.esc === "base")]
    : null;

  const acciones = (
    <div className="flex flex-wrap items-center gap-3">
      <label className="flex items-center gap-2 font-sans text-sm">
        <span className="text-ink-soft">Horizonte</span>
        <select
          className="rounded-md border border-hairline bg-surface px-3 py-1.5 text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan"
          value={horizonte}
          onChange={(e) => setHorizonte(Number(e.target.value))}
        >
          {HORIZONTES.map((h) => (
            <option key={h} value={h}>
              {h >= 12 ? `${h / 12} año${h > 12 ? "s" : ""}` : `${h} m`}
            </option>
          ))}
        </select>
      </label>
      <Button
        variant="cyan"
        className="no-print"
        onClick={() => window.print()}
      >
        Descargar PDF
      </Button>
    </div>
  );

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        titulo="Reportes"
        descripcion="Resumen ejecutivo de la proyección de caja, listo para la junta."
        acciones={acciones}
      />

      {cargando && (
        <>
          <Cargando variante="kpis" />
          <Cargando variante="card" className="h-80" />
        </>
      )}
      {error && (
        <ErrorEstado
          mensaje="No se pudo armar el reporte: verifica que haya modelos de moto y parámetros configurados en Supuestos."
          onReintentar={() => {
            for (const r of resultados) void r.refetch();
          }}
        />
      )}

      {listos && base && (
        <>
          <Card>
            <CardTitle>Resumen ejecutivo</CardTitle>
            <p className="mt-1 font-sans text-sm text-ink-soft">
              Proyección de caja de RODDOS a {horizonte} meses (escenario base),
              contra el mínimo de caja de {formatCOP(base.caja_minima)}.
            </p>

            <div className="mt-4">
              <TitularJuicio data={base} />
            </div>

            <div className="mt-4 grid grid-cols-2 gap-4 md:grid-cols-4">
              <KpiTileV2
                label="Piso de caja"
                valor={base.piso_caja}
                comparacion={{
                  delta: formatDelta(
                    parseMonto(base.piso_caja).minus(
                      parseMonto(base.caja_minima),
                    ),
                  ),
                  contra: "vs. el mínimo de caja",
                }}
                contexto={`en ${formatMesCorto(base.mes_mas_ajustado)}`}
                tono={base.meses_bajo_minimo > 0 ? "critico" : "positivo"}
              />
              <KpiTileV2
                label="Meses bajo el mínimo"
                valor="0"
                valorTexto={`${base.meses_bajo_minimo} de ${base.meses.length}`}
                contexto={
                  base.meses_bajo_minimo === 0
                    ? "ninguno en el horizonte"
                    : `el más ajustado: ${formatMesCorto(base.mes_mas_ajustado)}`
                }
                tono={base.meses_bajo_minimo > 0 ? "critico" : "positivo"}
              />
              <KpiTileV2
                label="Capital requerido"
                valor={base.capital_requerido}
                contexto={`para sostener el mínimo de caja de ${formatCOPCompact(base.caja_minima)}`}
                tono={
                  parseMonto(base.capital_requerido).isZero()
                    ? "positivo"
                    : "atencion"
                }
              />
              {base.runway_meses === null ? (
                <KpiTileV2
                  label="Autonomía de caja"
                  valor="0"
                  valorTexto="Sin límite"
                  contexto="la caja crece al ritmo actual"
                  tono="positivo"
                />
              ) : (
                <KpiTileV2
                  label="Autonomía de caja"
                  valor="0"
                  valorTexto={`${base.runway_meses} meses`}
                  contexto="al ritmo de gasto actual"
                  tono="atencion"
                />
              )}
            </div>
          </Card>

          <ChartCard
            conclusion={
              base.meses_bajo_minimo > 0
                ? `La caja toca su punto más bajo en ${formatMesCorto(base.mes_mas_ajustado)}`
                : "La caja se sostiene sobre el mínimo de caja en todo el horizonte"
            }
            subtitulo={`caja proyectada · escenario base · ${base.meses.length} meses`}
            pie={`Caja final: ${formatCOP(base.caja_final)} · Fuente: motor de proyección de COMPAS`}
            protagonista
          >
            <CashCurve meses={base.meses} umbral={base.caja_minima} anotada />
          </ChartCard>

          <Card className="overflow-hidden p-0">
            <table className="w-full font-sans text-sm">
              <thead>
                <tr className="border-b border-hairline text-left text-ink-faint">
                  <th className="px-4 py-2.5 font-semibold">Escenario</th>
                  <th className="px-4 py-2.5 text-right font-semibold">
                    Caja final
                  </th>
                  <th className="px-4 py-2.5 text-right font-semibold">
                    Piso de caja
                  </th>
                  <th className="px-4 py-2.5 text-right font-semibold">
                    Meses bajo mínimo
                  </th>
                  <th className="px-4 py-2.5 text-right font-semibold">
                    Capital requerido
                  </th>
                </tr>
              </thead>
              <tbody>
                {ESCENARIOS.map((s, i) => {
                  const d = datos[i] as Proyeccion;
                  const perf = d.meses_bajo_minimo > 0;
                  return (
                    <tr
                      key={s.esc}
                      className="border-b border-hairline/60 last:border-0"
                    >
                      <td className="px-4 py-2 font-medium text-ink">
                        {s.label}
                      </td>
                      <td className="tabular px-4 py-2 text-right text-ink">
                        {formatCOPEntero(d.caja_final)}
                      </td>
                      <td
                        className={`tabular px-4 py-2 text-right ${perf ? "text-critico" : "text-ink-soft"}`}
                      >
                        {formatCOPEntero(d.piso_caja)}
                      </td>
                      <td
                        className={`tabular px-4 py-2 text-right ${perf ? "text-critico" : "text-ink-soft"}`}
                      >
                        {d.meses_bajo_minimo}
                      </td>
                      <td className="tabular px-4 py-2 text-right text-ink-soft">
                        {formatCOPEntero(d.capital_requerido)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </Card>
        </>
      )}
    </div>
  );
}
