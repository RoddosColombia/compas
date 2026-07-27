// frontend/src/pages/FlujoDiarioPage.tsx
//
// Flujo de caja DIARIO — la evolución día a día del dinero para administrar la caja.
// Lee las transacciones reales (GET /caja/diaria); NO depende del motor ni del ciclo
// presupuestal, así que muestra la data cargada de inmediato. El saldo inicial es
// configurable (0 = saldo relativo desde el inicio del rango). Montos como string
// (regla 1) → formatCOP; parseMonto solo para escalar barras/colores, nunca Number.

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { CashCurve } from "@/components/charts/CashCurve";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Cargando } from "@/components/ui/cargando";
import { ChartCard } from "@/components/ui/chart-card";
import { ErrorEstado } from "@/components/ui/error-estado";
import { EstadoVacio } from "@/components/ui/estado-vacio";
import { KpiTileV2 } from "@/components/ui/kpi-tile";
import { type DiaCaja, obtenerCajaDiaria } from "@/lib/caja";
import {
  formatCOP,
  formatCOPCompact,
  formatFecha,
  parseMonto,
} from "@/lib/money";

const DEFAULTS = { desde: "2026-03-01", hasta: "2026-07-31", caja: "0" };

export default function FlujoDiarioPage() {
  const [desde, setDesde] = useState(DEFAULTS.desde);
  const [hasta, setHasta] = useState(DEFAULTS.hasta);
  const [cajaInicial, setCajaInicial] = useState(DEFAULTS.caja);
  const sucio =
    desde !== DEFAULTS.desde ||
    hasta !== DEFAULTS.hasta ||
    cajaInicial !== DEFAULTS.caja;

  const q = useQuery({
    queryKey: ["caja-diaria", desde, hasta, cajaInicial],
    queryFn: () => obtenerCajaDiaria({ desde, hasta, cajaInicial }),
  });

  const dias = q.data?.dias ?? [];

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        titulo="Flujo de caja diario"
        descripcion="Evolución del dinero día a día: ingresos, egresos y saldo corriendo, con la data real cargada."
      />

      <Card>
        <div className="flex flex-wrap items-end gap-4">
          <label className="flex flex-col gap-1 font-sans text-apoyo text-ink-soft">
            Desde
            <input
              type="date"
              value={desde}
              onChange={(e) => setDesde(e.target.value)}
              className="rounded-md border border-hairline px-2 py-1 text-cuerpo text-ink"
            />
          </label>
          <label className="flex flex-col gap-1 font-sans text-apoyo text-ink-soft">
            Hasta
            <input
              type="date"
              value={hasta}
              onChange={(e) => setHasta(e.target.value)}
              className="rounded-md border border-hairline px-2 py-1 text-cuerpo text-ink"
            />
          </label>
          <label className="flex flex-col gap-1 font-sans text-apoyo text-ink-soft">
            Saldo inicial (COP)
            <input
              type="number"
              value={cajaInicial}
              onChange={(e) => setCajaInicial(e.target.value || "0")}
              className="w-44 rounded-md border border-hairline px-2 py-1 text-cuerpo text-ink"
            />
          </label>
          {sucio && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => {
                setDesde(DEFAULTS.desde);
                setHasta(DEFAULTS.hasta);
                setCajaInicial(DEFAULTS.caja);
              }}
            >
              Limpiar
            </Button>
          )}
        </div>
      </Card>

      {q.isLoading && (
        <>
          <Cargando variante="kpis" />
          <Cargando variante="tabla" />
        </>
      )}
      {q.isError && (
        <ErrorEstado
          mensaje="No se pudo cargar el flujo de caja diario: revisa el rango de fechas."
          onReintentar={() => void q.refetch()}
        />
      )}

      {q.data && dias.length === 0 && (
        <Card>
          <EstadoVacio mensaje="No hay movimientos en este rango. Ajusta las fechas: hoy hay data cargada de marzo a julio 2026." />
        </Card>
      )}

      {q.data && dias.length > 0 && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <KpiTileV2
              label="Ingresos"
              valor={q.data.total_ingresos}
              contexto="entradas del período"
            />
            <KpiTileV2
              label="Egresos"
              valor={q.data.total_egresos}
              contexto="salidas del período"
            />
            <KpiTileV2
              label="Flujo neto"
              valor={q.data.flujo_neto}
              contexto={`${dias.length} días con movimiento`}
            />
            <KpiTileV2
              label="Saldo final"
              valor={q.data.caja_final}
              contexto={`arrancó en ${formatCOPCompact(q.data.caja_inicial)}`}
            />
          </div>

          <ChartCard
            conclusion={`El saldo pasó de ${formatCOPCompact(dias[0].caja)} a ${formatCOPCompact(q.data.caja_final)} en el período`}
            subtitulo={`saldo corriendo día a día · ${dias.length} días con movimiento`}
            pie="Fuente: transacciones reales cargadas (no depende del motor)"
          >
            <CashCurve
              meses={dias.map((d) => ({ mes: d.fecha, caja: d.caja }))}
              umbral="0"
              className="h-full"
            />
          </ChartCard>

          <Card>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] border-collapse font-sans text-sm">
                <thead>
                  <tr className="border-b border-hairline text-left text-apoyo text-ink-soft">
                    <th className="py-2 pr-3">Día</th>
                    <th className="py-2 pr-3 text-right">Ingresos</th>
                    <th className="py-2 pr-3 text-right">Egresos</th>
                    <th className="py-2 pr-3 text-right">Flujo</th>
                    <th className="py-2 pr-3 text-right">Saldo</th>
                  </tr>
                </thead>
                <tbody>
                  {dias.map((d) => (
                    <FilaDia key={d.fecha} d={d} />
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}

function FilaDia({ d }: { d: DiaCaja }) {
  const flujoNeg = parseMonto(d.flujo).isNegative();
  return (
    <tr className="border-b border-hairline/50">
      <td className="py-1.5 pr-3 whitespace-nowrap">{formatFecha(d.fecha)}</td>
      <td className="py-1.5 pr-3 text-right tabular-nums text-positivo">
        {formatCOP(d.ingresos)}
      </td>
      <td className="py-1.5 pr-3 text-right tabular-nums text-ink-soft">
        {formatCOP(d.egresos)}
      </td>
      <td
        className={`py-1.5 pr-3 text-right tabular-nums ${
          flujoNeg ? "text-critico" : "text-positivo"
        }`}
      >
        {formatCOP(d.flujo)}
      </td>
      <td className="py-1.5 pr-3 text-right font-medium tabular-nums text-ink">
        {formatCOP(d.caja)}
      </td>
    </tr>
  );
}
