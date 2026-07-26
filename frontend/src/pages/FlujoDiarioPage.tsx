// frontend/src/pages/FlujoDiarioPage.tsx
//
// Flujo de caja DIARIO — la evolución día a día del dinero para administrar la caja.
// Lee las transacciones reales (GET /caja/diaria); NO depende del motor ni del ciclo
// presupuestal, así que muestra la data cargada de inmediato. El saldo inicial es
// configurable (0 = saldo relativo desde el inicio del rango). Montos como string
// (regla 1) → formatCOP; parseMonto solo para escalar barras/colores, nunca Number.

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { PageHeader } from "@/components/layout/PageHeader";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Card } from "@/components/ui/card";
import { KpiTile } from "@/components/ui/kpi-tile";
import { type DiaCaja, obtenerCajaDiaria } from "@/lib/caja";
import { formatCOP, formatFecha, parseMonto } from "@/lib/money";

export default function FlujoDiarioPage() {
  const [desde, setDesde] = useState("2026-03-01");
  const [hasta, setHasta] = useState("2026-07-31");
  const [cajaInicial, setCajaInicial] = useState("0");

  const q = useQuery({
    queryKey: ["caja-diaria", desde, hasta, cajaInicial],
    queryFn: () => obtenerCajaDiaria({ desde, hasta, cajaInicial }),
  });

  const dias = q.data?.dias ?? [];
  // escala para las barras del saldo (presentación; Decimal → number solo aquí)
  const maxCaja = dias.reduce((m, d) => {
    const v = parseMonto(d.caja).abs().toNumber();
    return v > m ? v : m;
  }, 1);

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        titulo="Flujo de caja diario"
        descripcion="Evolución del dinero día a día: ingresos, egresos y saldo corriendo, con la data real cargada."
      />

      <Card>
        <div className="flex flex-wrap items-end gap-4">
          <label className="flex flex-col gap-1 font-sans text-xs text-ink-soft">
            Desde
            <input
              type="date"
              value={desde}
              onChange={(e) => setDesde(e.target.value)}
              className="rounded-md border border-line px-2 py-1 text-sm text-ink"
            />
          </label>
          <label className="flex flex-col gap-1 font-sans text-xs text-ink-soft">
            Hasta
            <input
              type="date"
              value={hasta}
              onChange={(e) => setHasta(e.target.value)}
              className="rounded-md border border-line px-2 py-1 text-sm text-ink"
            />
          </label>
          <label className="flex flex-col gap-1 font-sans text-xs text-ink-soft">
            Saldo inicial (COP)
            <input
              type="number"
              value={cajaInicial}
              onChange={(e) => setCajaInicial(e.target.value || "0")}
              className="w-44 rounded-md border border-line px-2 py-1 text-sm text-ink"
            />
          </label>
        </div>
      </Card>

      {q.isLoading && (
        <p className="font-sans text-sm text-ink-soft">
          Cargando flujo diario…
        </p>
      )}
      {q.isError && (
        <AlertBanner variant="danger">
          No se pudo cargar el flujo de caja diario. Revisa el rango de fechas.
        </AlertBanner>
      )}

      {q.data && dias.length === 0 && (
        <Card>
          <p className="font-sans text-sm text-ink-soft">
            No hay movimientos en este rango. Ajusta las fechas (hoy hay data
            cargada de marzo a julio 2026).
          </p>
        </Card>
      )}

      {q.data && dias.length > 0 && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <KpiTile
              label="Ingresos"
              value={formatCOP(q.data.total_ingresos)}
            />
            <KpiTile label="Egresos" value={formatCOP(q.data.total_egresos)} />
            <KpiTile
              label="Flujo neto"
              value={formatCOP(q.data.flujo_neto)}
              sub={`${dias.length} días con movimiento`}
            />
            <KpiTile
              label="Saldo final"
              value={formatCOP(q.data.caja_final)}
              sub={`inicial ${formatCOP(q.data.caja_inicial)}`}
            />
          </div>

          <Card>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] border-collapse font-sans text-sm">
                <thead>
                  <tr className="border-b border-line text-left text-xs text-ink-soft">
                    <th className="py-2 pr-3">Día</th>
                    <th className="py-2 pr-3 text-right">Ingresos</th>
                    <th className="py-2 pr-3 text-right">Egresos</th>
                    <th className="py-2 pr-3 text-right">Flujo</th>
                    <th className="py-2 pr-3 text-right">Saldo</th>
                    <th className="py-2 pl-3">Evolución del saldo</th>
                  </tr>
                </thead>
                <tbody>
                  {dias.map((d) => (
                    <FilaDia key={d.fecha} d={d} maxCaja={maxCaja} />
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

function FilaDia({ d, maxCaja }: { d: DiaCaja; maxCaja: number }) {
  const flujoNeg = parseMonto(d.flujo).isNegative();
  const caja = parseMonto(d.caja);
  const cajaNeg = caja.isNegative();
  const ancho = Math.max(2, (caja.abs().toNumber() / maxCaja) * 100);
  return (
    <tr className="border-b border-line/50">
      <td className="py-1.5 pr-3 whitespace-nowrap">{formatFecha(d.fecha)}</td>
      <td className="py-1.5 pr-3 text-right tabular-nums text-emerald-700">
        {formatCOP(d.ingresos)}
      </td>
      <td className="py-1.5 pr-3 text-right tabular-nums text-ink-soft">
        {formatCOP(d.egresos)}
      </td>
      <td
        className={`py-1.5 pr-3 text-right tabular-nums ${
          flujoNeg ? "text-rose-600" : "text-emerald-700"
        }`}
      >
        {formatCOP(d.flujo)}
      </td>
      <td className="py-1.5 pr-3 text-right font-medium tabular-nums text-ink">
        {formatCOP(d.caja)}
      </td>
      <td className="py-1.5 pl-3">
        <div className="h-2.5 w-full rounded bg-line/40">
          <div
            className={`h-2.5 rounded ${cajaNeg ? "bg-rose-400" : "bg-teal-500"}`}
            style={{ width: `${ancho}%` }}
          />
        </div>
      </td>
    </tr>
  );
}
