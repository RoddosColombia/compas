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
import { AlertBanner } from "@/components/ui/alert-banner";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { KpiTileV2 } from "@/components/ui/kpi-tile";
import { formatCOP, parseMonto } from "@/lib/money";
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
        <p className="font-sans text-sm text-ink-soft">Armando el reporte…</p>
      )}
      {error && (
        <AlertBanner variant="danger">
          No se pudo armar el reporte. Verifica que haya modelos de moto y
          parámetros configurados en Datos.
        </AlertBanner>
      )}

      {listos && base && (
        <>
          <Card>
            <CardTitle>Resumen ejecutivo</CardTitle>
            <p className="mt-1 font-sans text-sm text-ink-soft">
              Proyección de caja de RODDOS a {horizonte} meses (escenario base),
              contra el umbral de {formatCOP(base.caja_minima)}.
            </p>

            {base.meses_bajo_minimo > 0 ? (
              <div className="mt-4">
                <AlertBanner variant="danger">
                  En el escenario base la caja perfora el mínimo en{" "}
                  {base.meses_bajo_minimo}{" "}
                  {base.meses_bajo_minimo === 1 ? "mes" : "meses"}; el punto más
                  ajustado es {base.mes_mas_ajustado} (
                  {formatCOP(base.piso_caja)}
                  ). Capital requerido para sostener el umbral:{" "}
                  {formatCOP(base.capital_requerido)}.
                </AlertBanner>
              </div>
            ) : (
              <div className="mt-4">
                <AlertBanner variant="ok">
                  En el escenario base la caja se mantiene por encima del mínimo
                  en todo el horizonte.
                </AlertBanner>
              </div>
            )}

            <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
              <KpiTileV2
                label="Caja final (base)"
                valor={base.caja_final}
                contexto="al final del horizonte"
              />
              <KpiTileV2
                label="Piso de caja"
                valor={base.piso_caja}
                contexto={`en ${base.mes_mas_ajustado}`}
                tono={base.meses_bajo_minimo > 0 ? "critico" : "positivo"}
              />
              <KpiTileV2
                label="Capital requerido"
                valor={base.capital_requerido}
                contexto="para sostener el umbral"
                tono={
                  parseMonto(base.capital_requerido).isZero()
                    ? "positivo"
                    : "atencion"
                }
              />
              <KpiTileV2
                label="Runway"
                valor="0"
                valorTexto={
                  base.runway_meses === null ? "—" : `${base.runway_meses} m`
                }
                contexto={
                  base.runway_meses === null
                    ? "caja no decrece"
                    : "al ritmo actual"
                }
              />
            </div>
          </Card>

          <Card>
            <CardTitle>Trayectoria de caja (base)</CardTitle>
            <div className="mt-3">
              <CashCurve meses={base.meses} umbral={base.caja_minima} />
            </div>
          </Card>

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
                        {formatCOP(d.caja_final)}
                      </td>
                      <td
                        className={`tabular px-4 py-2 text-right ${perf ? "text-critico" : "text-ink-soft"}`}
                      >
                        {formatCOP(d.piso_caja)}
                      </td>
                      <td
                        className={`tabular px-4 py-2 text-right ${perf ? "text-critico" : "text-ink-soft"}`}
                      >
                        {d.meses_bajo_minimo}
                      </td>
                      <td className="tabular px-4 py-2 text-right text-ink-soft">
                        {formatCOP(d.capital_requerido)}
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
