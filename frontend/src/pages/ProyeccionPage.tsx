// frontend/src/pages/ProyeccionPage.tsx
//
// COCK-03: la vista Proyecciones — el corazón visual de COMPAS. Muestra la curva de
// caja proyectada mes a mes contra el UMBRAL (caja mínima), el mes más ajustado, y el
// ingreso DISCRIMINADO (recaudo de crédito vs cuota inicial). Escenarios
// Pesimista/Base/Optimista y horizonte configurable. Todo lo calcula el motor (C7);
// el front solo presenta (montos con formatCOP, regla 1; .toNumber() SOLO para la
// geometría del SVG, nunca para cálculo financiero).

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { formatCOP, parseMonto } from "@/lib/money";
import {
  ESCENARIO_LABEL,
  ESTADO_LABEL,
  type Escenario,
  type EstadoMes,
  type MesProyeccion,
  type Proyeccion,
  obtenerProyeccion,
} from "@/lib/proyeccion";

const ESCENARIOS: Escenario[] = ["pesimista", "base", "optimista"];
const HORIZONTES = [12, 24, 36, 60, 120, 180];

const ESTADO_ESTILO: Record<EstadoMes, string> = {
  ok: "bg-brand-soft/20 text-brand",
  critico: "bg-warn/20 text-warn",
  negativo: "bg-alert/20 text-alert",
};

export default function ProyeccionPage() {
  const [escenario, setEscenario] = useState<Escenario>("base");
  const [horizonte, setHorizonte] = useState(60);

  const q = useQuery({
    queryKey: ["proyeccion", escenario, horizonte],
    queryFn: () => obtenerProyeccion({ escenario, horizonteMeses: horizonte }),
  });

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-semibold">Proyecciones</h2>
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex rounded-md border border-slate-300 text-sm">
            {ESCENARIOS.map((e) => (
              <button
                key={e}
                type="button"
                onClick={() => setEscenario(e)}
                className={`px-3 py-1 first:rounded-l-md last:rounded-r-md ${
                  escenario === e ? "bg-brand text-white" : "text-slate-600"
                }`}
              >
                {ESCENARIO_LABEL[e]}
              </button>
            ))}
          </div>
          <label className="flex items-center gap-2 text-sm">
            <span className="text-slate-500">Horizonte</span>
            <select
              className="rounded-md border border-slate-300 px-3 py-1.5"
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
        </div>
      </header>

      {q.isLoading && (
        <p className="text-sm text-slate-500">Calculando proyección…</p>
      )}
      {q.isError && (
        <p className="text-sm text-alert">
          No se pudo calcular la proyección. Verifica que haya modelos de moto y
          parámetros configurados.
        </p>
      )}

      {q.data && <ProyeccionContenido data={q.data} />}
    </div>
  );
}

function ProyeccionContenido({ data }: { data: Proyeccion }) {
  const pisoTono =
    data.meses_bajo_minimo > 0
      ? parseMonto(data.piso_caja).isNegative()
        ? "alert"
        : "warn"
      : "brand";
  return (
    <>
      <div className="flex flex-wrap gap-4">
        <Kpi
          titulo="Piso de caja"
          valor={formatCOP(data.piso_caja)}
          sub={`en ${data.mes_mas_ajustado}`}
          acento={pisoTono}
        />
        <Kpi
          titulo="Caja final"
          valor={formatCOP(data.caja_final)}
          acento="turq"
        />
        <Kpi
          titulo="Capital requerido"
          valor={formatCOP(data.capital_requerido)}
          sub="para no cruzar el umbral"
          acento={
            parseMonto(data.capital_requerido).isZero() ? "brand" : "alert"
          }
        />
        <Kpi
          titulo="Meses bajo el mínimo"
          valor={String(data.meses_bajo_minimo)}
          acento={data.meses_bajo_minimo > 0 ? "warn" : "brand"}
        />
        <Kpi
          titulo="Runway"
          valor={data.runway_meses === null ? "—" : `${data.runway_meses} m`}
          sub={
            data.runway_meses === null ? "caja no decrece" : "al ritmo actual"
          }
        />
      </div>

      <CurvaCaja meses={data.meses} umbral={data.caja_minima} />

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-slate-500">
              <th className="py-2 pr-4">Mes</th>
              <th className="py-2 pr-4 text-right">Motos</th>
              <th className="py-2 pr-4 text-right">Recaudo crédito</th>
              <th className="py-2 pr-4 text-right">Cuota inicial</th>
              <th className="py-2 pr-4 text-right">Ingreso bruto</th>
              <th className="py-2 pr-4 text-right">Flujo</th>
              <th className="py-2 pr-4 text-right">Caja</th>
              <th className="py-2 pr-4">Estado</th>
            </tr>
          </thead>
          <tbody>
            {data.meses.map((m) => (
              <tr key={m.mes} className="border-b border-slate-100">
                <td className="py-2 pr-4 font-medium">{m.mes}</td>
                <td className="py-2 pr-4 text-right font-mono">{m.motos}</td>
                <td className="py-2 pr-4 text-right font-mono">
                  {formatCOP(m.recaudo_credito)}
                </td>
                <td className="py-2 pr-4 text-right font-mono">
                  {formatCOP(m.cuotas_iniciales)}
                </td>
                <td className="py-2 pr-4 text-right font-mono font-medium">
                  {formatCOP(m.ingreso_bruto)}
                </td>
                <td className="py-2 pr-4 text-right font-mono">
                  {formatCOP(m.flujo)}
                </td>
                <td className="py-2 pr-4 text-right font-mono font-medium">
                  {formatCOP(m.caja)}
                </td>
                <td className="py-2 pr-4">
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs font-medium ${ESTADO_ESTILO[m.estado]}`}
                  >
                    {ESTADO_LABEL[m.estado]}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function Kpi({
  titulo,
  valor,
  sub,
  acento,
}: {
  titulo: string;
  valor: string;
  sub?: string;
  acento?: "brand" | "turq" | "warn" | "alert";
}) {
  const color =
    acento === "brand"
      ? "text-brand"
      : acento === "turq"
        ? "text-turq"
        : acento === "warn"
          ? "text-warn"
          : acento === "alert"
            ? "text-alert"
            : "text-slate-800";
  return (
    <div className="min-w-40 flex-1 rounded-lg border border-slate-200 px-4 py-3">
      <p className="text-xs text-slate-500">{titulo}</p>
      <p className={`mt-1 font-mono text-lg font-semibold ${color}`}>{valor}</p>
      {sub && <p className="mt-0.5 text-xs text-slate-400">{sub}</p>}
    </div>
  );
}

// Curva de caja proyectada vs. umbral — SVG inline (sin dependencia de gráficos).
// .toNumber() aquí es SOLO geometría de presentación (como formatCOP), no cálculo.
function CurvaCaja({
  meses,
  umbral,
}: {
  meses: MesProyeccion[];
  umbral: string;
}) {
  const W = 900;
  const H = 220;
  const P = 8; // padding vertical
  if (meses.length < 2) return null;

  const cajas = meses.map((m) => parseMonto(m.caja).toNumber());
  const u = parseMonto(umbral).toNumber();
  const min = Math.min(...cajas, u, 0);
  const max = Math.max(...cajas, u);
  const span = max - min || 1;
  const x = (i: number) => (i / (meses.length - 1)) * W;
  const y = (v: number) => P + (1 - (v - min) / span) * (H - 2 * P);

  const linea = cajas.map((v, i) => `${x(i)},${y(v)}`).join(" ");
  const area = `0,${y(min)} ${linea} ${W},${y(min)}`;
  const yUmbral = y(u);
  const yCero = y(0);

  return (
    <div className="rounded-lg border border-slate-200 p-4">
      <div className="mb-2 flex items-center justify-between">
        <p className="text-sm font-medium text-slate-700">
          Caja proyectada vs. umbral
        </p>
        <p className="text-xs text-slate-400">
          umbral {formatCOP(umbral)} · {meses.length} meses
        </p>
      </div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="h-56 w-full"
        preserveAspectRatio="none"
        role="img"
        aria-label="Curva de caja proyectada contra el umbral de caja mínima"
      >
        <title>Caja proyectada vs. umbral</title>
        <polygon points={area} className="fill-brand-soft/15" />
        {/* línea de cero (si el rango la cruza) */}
        {min < 0 && (
          <line
            x1={0}
            x2={W}
            y1={yCero}
            y2={yCero}
            className="stroke-slate-300"
            strokeWidth={1}
          />
        )}
        {/* umbral (caja mínima) */}
        <line
          x1={0}
          x2={W}
          y1={yUmbral}
          y2={yUmbral}
          className="stroke-alert"
          strokeWidth={1.5}
          strokeDasharray="6 4"
        />
        {/* curva de caja */}
        <polyline
          points={linea}
          fill="none"
          className="stroke-brand"
          strokeWidth={2}
          vectorEffect="non-scaling-stroke"
        />
        {/* marcadores de meses bajo el mínimo */}
        {cajas.map((v, i) =>
          v < u ? (
            <circle
              key={meses[i].mes}
              cx={x(i)}
              cy={y(v)}
              r={2.5}
              className="fill-alert"
            />
          ) : null,
        )}
      </svg>
    </div>
  );
}
