// frontend/src/pages/DashboardsPage.tsx
//
// Dashboards — panel operativo del cockpit. Muestra las series que el motor (C7)
// YA proyecta: cobranza (recaudo de crédito), cartera activa, cuotas iniciales e
// ingreso bruto por mes. NO inventa cifras: cartera por añada, mora por tramo y
// colocación mensual requieren un motor de agregación adicional (CR pendiente) y
// se marcan como tal. Montos con formatCOP (regla 1); .toNumber() SOLO para el
// ancho de las barras (presentación), nunca cálculo.

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { PageHeader } from "@/components/layout/PageHeader";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Card, CardTitle } from "@/components/ui/card";
import { KpiTile } from "@/components/ui/kpi-tile";
import { formatCOP, parseMonto } from "@/lib/money";
import { type MesProyeccion, obtenerProyeccion } from "@/lib/proyeccion";

const HORIZONTES = [12, 24, 36, 60];

function suma(meses: MesProyeccion[], campo: keyof MesProyeccion): string {
  return meses
    .reduce((acc, m) => acc.add(parseMonto(String(m[campo]))), parseMonto("0"))
    .toFixed(2);
}

export default function DashboardsPage() {
  const [horizonte, setHorizonte] = useState(24);
  const q = useQuery({
    queryKey: ["proyeccion", "base", horizonte],
    queryFn: () =>
      obtenerProyeccion({ escenario: "base", horizonteMeses: horizonte }),
  });

  const selectorHorizonte = (
    <label className="flex items-center gap-2 font-sans text-sm">
      <span className="text-ink-soft">Horizonte</span>
      <select
        className="rounded-md border border-hairline bg-surface px-3 py-1.5 text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan"
        value={horizonte}
        onChange={(e) => setHorizonte(Number(e.target.value))}
      >
        {HORIZONTES.map((h) => (
          <option key={h} value={h}>
            {`${h / 12} año${h > 12 ? "s" : ""}`}
          </option>
        ))}
      </select>
    </label>
  );

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        titulo="Dashboards"
        descripcion="Operación proyectada: cobranza, cartera y colocación."
        acciones={selectorHorizonte}
      />

      {q.isLoading && (
        <p className="font-sans text-sm text-ink-soft">Cargando operación…</p>
      )}
      {q.isError && (
        <AlertBanner variant="danger">
          No se pudo cargar la operación. Verifica que haya modelos de moto y
          parámetros configurados en Datos.
        </AlertBanner>
      )}

      {q.data && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <KpiTile
              label="Cobranza proyectada"
              value={formatCOP(suma(q.data.meses, "recaudo_credito"))}
              sub={`${q.data.meses.length} meses`}
            />
            <KpiTile
              label="Cuotas iniciales"
              value={formatCOP(suma(q.data.meses, "cuotas_iniciales"))}
            />
            <KpiTile
              label="Ingreso bruto proyectado"
              value={formatCOP(suma(q.data.meses, "ingreso_bruto"))}
            />
            <KpiTile
              label="Cartera activa al cierre"
              value={String(
                q.data.meses[q.data.meses.length - 1]?.cartera ?? 0,
              )}
              sub="motos pagando"
            />
          </div>

          <Card>
            <CardTitle>Cobranza mensual proyectada</CardTitle>
            <p className="mt-0.5 font-sans text-xs text-ink-faint">
              recaudo de crédito (cuota a cuota) por mes
            </p>
            <div className="mt-4">
              <BarrasCobranza meses={q.data.meses} />
            </div>
          </Card>

          <AlertBanner variant="warn">
            Cartera <span className="font-semibold">por añada</span>, mora{" "}
            <span className="font-semibold">por tramo</span> y colocación
            mensual requieren un motor de agregación adicional (CR pendiente).
            Este panel muestra las series que el motor ya proyecta.
          </AlertBanner>
        </>
      )}
    </div>
  );
}

// Barras horizontales de cobranza mensual. El ancho es geometría de presentación
// (.toNumber() como formatCOP), no cálculo financiero.
function BarrasCobranza({ meses }: { meses: MesProyeccion[] }) {
  const valores = meses.map((m) => parseMonto(m.recaudo_credito).toNumber());
  const max = Math.max(...valores, 1);
  return (
    <div className="flex flex-col gap-1.5">
      {meses.map((m, i) => {
        const pct = Math.max(2, (valores[i] / max) * 100);
        return (
          <div key={m.mes} className="flex items-center gap-3">
            <span className="tabular w-16 shrink-0 font-sans text-xs text-ink-soft">
              {m.mes}
            </span>
            <div className="h-4 flex-1 overflow-hidden rounded bg-surface-muted">
              <div
                className="h-full rounded bg-cyan"
                style={{ width: `${pct}%` }}
              />
            </div>
            <span className="tabular w-32 shrink-0 text-right font-sans text-xs text-ink">
              {formatCOP(m.recaudo_credito)}
            </span>
          </div>
        );
      })}
    </div>
  );
}
