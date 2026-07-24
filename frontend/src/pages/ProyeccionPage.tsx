// frontend/src/pages/ProyeccionPage.tsx
//
// Proyecciones — la vista HERO del cockpit (Blueprint): la curva de caja proyectada
// contra el UMBRAL (caja mínima) es la protagonista, con la franja de KPIs del motor
// y el ingreso DISCRIMINADO (recaudo de crédito vs cuota inicial). Escenarios
// Pesimista/Base/Optimista + horizonte configurable. Todo lo calcula el motor (C7);
// el front solo presenta (montos con formatCOP, regla 1; .toNumber() SOLO para la
// geometría del SVG, nunca para cálculo financiero).

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { CashCurve } from "@/components/charts/CashCurve";
import { PageHeader } from "@/components/layout/PageHeader";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Card, CardTitle } from "@/components/ui/card";
import { KpiTile } from "@/components/ui/kpi-tile";
import { ScenarioChip } from "@/components/ui/scenario-chip";
import { formatCOP, parseMonto } from "@/lib/money";
import {
  ESCENARIO_LABEL,
  ESTADO_LABEL,
  type Escenario,
  type EstadoMes,
  type Proyeccion,
  obtenerProyeccion,
} from "@/lib/proyeccion";

const ESCENARIOS: Escenario[] = ["pesimista", "base", "optimista"];
const HORIZONTES = [12, 24, 36, 60, 120, 180];

const ESTADO_ESTILO: Record<EstadoMes, string> = {
  ok: "bg-green/10 text-green",
  critico: "bg-amber/10 text-amber",
  negativo: "bg-red/10 text-red",
};

export default function ProyeccionPage() {
  const [escenario, setEscenario] = useState<Escenario>("base");
  const [horizonte, setHorizonte] = useState(60);

  const q = useQuery({
    queryKey: ["proyeccion", escenario, horizonte],
    queryFn: () => obtenerProyeccion({ escenario, horizonteMeses: horizonte }),
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
            {h >= 12 ? `${h / 12} año${h > 12 ? "s" : ""}` : `${h} m`}
          </option>
        ))}
      </select>
    </label>
  );

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        titulo="Proyecciones"
        descripcion="Caja proyectada mes a mes contra el umbral, por escenario."
        acciones={selectorHorizonte}
      />

      {/* Palancas: escenario */}
      <div className="flex flex-wrap items-center gap-2">
        {ESCENARIOS.map((e) => (
          <ScenarioChip
            key={e}
            label={ESCENARIO_LABEL[e]}
            active={escenario === e}
            onClick={() => setEscenario(e)}
          />
        ))}
      </div>

      {q.isLoading && (
        <p className="font-sans text-sm text-ink-soft">
          Calculando proyección…
        </p>
      )}
      {q.isError && (
        <AlertBanner variant="danger">
          No se pudo calcular la proyección. Verifica que haya modelos de moto y
          parámetros configurados.
        </AlertBanner>
      )}

      {q.data && <ProyeccionContenido data={q.data} />}
    </div>
  );
}

function ProyeccionContenido({ data }: { data: Proyeccion }) {
  const perforada = data.meses_bajo_minimo > 0;
  const requiereCapital = !parseMonto(data.capital_requerido).isZero();

  return (
    <>
      {/* Aviso de estado (rojo = perforación, reservado) */}
      {perforada ? (
        <AlertBanner variant="danger">
          La caja perfora el mínimo en {data.meses_bajo_minimo}{" "}
          {data.meses_bajo_minimo === 1 ? "mes" : "meses"}; el punto más
          ajustado es {data.mes_mas_ajustado} ({formatCOP(data.piso_caja)}).
        </AlertBanner>
      ) : (
        <AlertBanner variant="ok">
          La caja se mantiene por encima del mínimo en todo el horizonte.
        </AlertBanner>
      )}

      {/* Franja de KPIs del motor */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5">
        <KpiTile
          label="Piso de caja"
          value={formatCOP(data.piso_caja)}
          sub={`en ${data.mes_mas_ajustado}`}
          tono={perforada ? "peligro" : "neutro"}
        />
        <KpiTile label="Caja final" value={formatCOP(data.caja_final)} />
        <KpiTile
          label="Capital requerido"
          value={formatCOP(data.capital_requerido)}
          sub="para no cruzar el umbral"
          tono={requiereCapital ? "peligro" : "neutro"}
        />
        <KpiTile
          label="Meses bajo el mínimo"
          value={String(data.meses_bajo_minimo)}
          tono={perforada ? "peligro" : "neutro"}
        />
        <KpiTile
          label="Runway"
          value={data.runway_meses === null ? "—" : `${data.runway_meses} m`}
          sub={
            data.runway_meses === null ? "caja no decrece" : "al ritmo actual"
          }
        />
      </div>

      {/* Hero: la curva */}
      <Card>
        <div className="mb-3 flex items-center justify-between">
          <CardTitle>Caja proyectada vs. umbral</CardTitle>
          <p className="font-sans text-xs text-ink-faint">
            umbral {formatCOP(data.caja_minima)} · {data.meses.length} meses
          </p>
        </div>
        <CashCurve meses={data.meses} umbral={data.caja_minima} />
      </Card>

      {/* Tabla de cierre */}
      <Card className="overflow-hidden p-0">
        <div className="overflow-x-auto">
          <table className="w-full font-sans text-sm">
            <thead>
              <tr className="border-b border-hairline text-left text-ink-faint">
                <th className="px-4 py-2.5 font-semibold">Mes</th>
                <th className="px-4 py-2.5 text-right font-semibold">Motos</th>
                <th className="px-4 py-2.5 text-right font-semibold">
                  Recaudo crédito
                </th>
                <th className="px-4 py-2.5 text-right font-semibold">
                  Cuota inicial
                </th>
                <th className="px-4 py-2.5 text-right font-semibold">
                  Ingreso bruto
                </th>
                <th className="px-4 py-2.5 text-right font-semibold">Flujo</th>
                <th className="px-4 py-2.5 text-right font-semibold">Caja</th>
                <th className="px-4 py-2.5 font-semibold">Estado</th>
              </tr>
            </thead>
            <tbody>
              {data.meses.map((m) => (
                <tr
                  key={m.mes}
                  className="border-b border-hairline/60 last:border-0 hover:bg-surface-muted"
                >
                  <td className="px-4 py-2 font-medium text-ink">{m.mes}</td>
                  <td className="tabular px-4 py-2 text-right text-ink-soft">
                    {m.motos}
                  </td>
                  <td className="tabular px-4 py-2 text-right text-ink-soft">
                    {formatCOP(m.recaudo_credito)}
                  </td>
                  <td className="tabular px-4 py-2 text-right text-ink-soft">
                    {formatCOP(m.cuotas_iniciales)}
                  </td>
                  <td className="tabular px-4 py-2 text-right font-medium text-ink">
                    {formatCOP(m.ingreso_bruto)}
                  </td>
                  <td className="tabular px-4 py-2 text-right text-ink-soft">
                    {formatCOP(m.flujo)}
                  </td>
                  <td className="tabular px-4 py-2 text-right font-medium text-ink">
                    {formatCOP(m.caja)}
                  </td>
                  <td className="px-4 py-2">
                    <span
                      className={`rounded-full px-2 py-0.5 font-sans text-xs font-medium ${ESTADO_ESTILO[m.estado]}`}
                    >
                      {ESTADO_LABEL[m.estado]}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}
