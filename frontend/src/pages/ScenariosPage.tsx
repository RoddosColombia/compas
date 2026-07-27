// frontend/src/pages/ScenariosPage.tsx
//
// Escenarios — compara los tres futuros del motor (pesimista/base/optimista)
// superpuestos y en tarjetas. Cada escenario cambia mora/recuperación (presets del
// motor); todo lo calcula el backend. El front consulta uno por escenario y los
// presenta juntos para decidir. Montos con formatCOP (regla 1).

import { useQueries } from "@tanstack/react-query";
import { useState } from "react";

import {
  ScenariosChart,
  type SerieColor,
} from "@/components/charts/ScenariosChart";
import { PageHeader } from "@/components/layout/PageHeader";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Card, CardTitle } from "@/components/ui/card";
import { formatCOP, parseMonto } from "@/lib/money";
import {
  type Escenario,
  type Proyeccion,
  obtenerProyeccion,
} from "@/lib/proyeccion";

const HORIZONTES = [12, 24, 36, 60, 120, 180];

const ESCENARIOS: { esc: Escenario; label: string; color: SerieColor }[] = [
  { esc: "pesimista", label: "Pesimista", color: "amber" },
  { esc: "base", label: "Base", color: "cyan" },
  { esc: "optimista", label: "Optimista", color: "green" },
];

const PUNTO: Record<SerieColor, string> = {
  amber: "bg-atencion",
  cyan: "bg-cyan",
  green: "bg-positivo",
};

export default function ScenariosPage() {
  const [horizonte, setHorizonte] = useState(60);

  const resultados = useQueries({
    queries: ESCENARIOS.map((s) => ({
      queryKey: ["proyeccion", s.esc, horizonte],
      queryFn: () =>
        obtenerProyeccion({ escenario: s.esc, horizonteMeses: horizonte }),
    })),
  });

  // Robustez de estado (bug-fix): mostrar SIEMPRE algo. Error si ALGUNO falla
  // (antes exigía que TODOS fallaran → estados mixtos quedaban en blanco).
  const error = resultados.some((r) => r.isError);
  const cargando = resultados.some((r) => r.isPending);
  const datos = resultados.map((r) => r.data);
  const listos = datos.every((d): d is Proyeccion => d !== undefined);

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
        titulo="Escenarios"
        descripcion="Los tres futuros de la caja, uno al lado del otro, para decidir con margen."
        acciones={selectorHorizonte}
      />

      {error ? (
        <AlertBanner variant="danger">
          No se pudieron calcular los escenarios. Verifica que haya modelos de
          moto y parámetros configurados en Datos.
        </AlertBanner>
      ) : cargando ? (
        <p className="font-sans text-sm text-ink-soft">
          Calculando escenarios…
        </p>
      ) : null}

      {listos && (
        <>
          {/* Curvas superpuestas */}
          <Card>
            <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
              <CardTitle>Caja proyectada por escenario</CardTitle>
              <div className="flex items-center gap-4">
                {ESCENARIOS.map((s) => (
                  <span
                    key={s.esc}
                    className="flex items-center gap-1.5 font-sans text-apoyo text-ink-soft"
                  >
                    <span
                      className={`h-2 w-2 rounded-full ${PUNTO[s.color]}`}
                    />
                    {s.label}
                  </span>
                ))}
                <span className="flex items-center gap-1.5 font-sans text-apoyo text-ink-soft">
                  <span className="h-0 w-3 border-t-2 border-critico border-dashed" />
                  Umbral
                </span>
              </div>
            </div>
            <ScenariosChart
              umbral={datos[0].caja_minima}
              series={ESCENARIOS.map((s, i) => ({
                escenario: s.esc,
                color: s.color,
                meses: datos[i].meses,
              }))}
            />
          </Card>

          {/* Tarjetas comparativas */}
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            {ESCENARIOS.map((s, i) => (
              <TarjetaEscenario
                key={s.esc}
                label={s.label}
                color={s.color}
                data={datos[i]}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function TarjetaEscenario({
  label,
  color,
  data,
}: {
  label: string;
  color: SerieColor;
  data: Proyeccion;
}) {
  const perforada = data.meses_bajo_minimo > 0;
  const requiereCapital = !parseMonto(data.capital_requerido).isZero();

  return (
    <Card>
      <div className="mb-3 flex items-center gap-2">
        <span className={`h-2.5 w-2.5 rounded-full ${PUNTO[color]}`} />
        <CardTitle>{label}</CardTitle>
      </div>
      <dl className="flex flex-col gap-2.5">
        <Metrica label="Caja final" valor={formatCOP(data.caja_final)} />
        <Metrica
          label="Piso de caja"
          valor={formatCOP(data.piso_caja)}
          sub={`en ${data.mes_mas_ajustado}`}
          peligro={perforada}
        />
        <Metrica
          label="Meses bajo el mínimo"
          valor={String(data.meses_bajo_minimo)}
          peligro={perforada}
        />
        <Metrica
          label="Capital requerido"
          valor={formatCOP(data.capital_requerido)}
          peligro={requiereCapital}
        />
      </dl>
    </Card>
  );
}

function Metrica({
  label,
  valor,
  sub,
  peligro,
}: {
  label: string;
  valor: string;
  sub?: string;
  peligro?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="font-sans text-apoyo text-ink-soft">{label}</dt>
      <dd className="text-right">
        <span
          className={`tabular font-display text-sm font-semibold ${
            peligro ? "text-critico" : "text-ink"
          }`}
        >
          {valor}
        </span>
        {sub && (
          <span className="ml-1 font-sans text-apoyo text-ink-faint">
            {sub}
          </span>
        )}
      </dd>
    </div>
  );
}
