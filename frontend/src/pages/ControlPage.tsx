// frontend/src/pages/ControlPage.tsx
//
// Vista Control (Sprint 4, cara del demo G3): presupuesto definido vs ejecutado
// vs disponible por rubro y grupo, con semáforo (verde/amarillo/rojo). Selector de
// mes (solo meses en ejecución o cerrados). Montos con formatCOP (regla 1); el
// cálculo y el semáforo vienen del backend — el front solo presenta (Spec §17).

import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { GRUPO_LABEL, type Semaforo, vistaControl } from "@/lib/control";
import { listarMeses } from "@/lib/meses";
import { formatCOP } from "@/lib/money";

const SEMAFORO_ESTILO: Record<Semaforo, string> = {
  verde: "bg-brand-soft/20 text-brand",
  amarillo: "bg-warn/20 text-warn",
  rojo: "bg-alert/20 text-alert",
};

const SEMAFORO_LABEL: Record<Semaforo, string> = {
  verde: "En rango",
  amarillo: "Cerca del límite",
  rojo: "Sobre-ejecutado",
};

export default function ControlPage() {
  const meses = useQuery({ queryKey: ["meses"], queryFn: listarMeses });

  // Solo meses con presupuesto vivo (en ejecución o cerrado), más reciente primero.
  const disponibles = useMemo(() => {
    const items = meses.data?.items ?? [];
    return items
      .filter((m) => m.estado === "en_ejecucion" || m.estado === "cerrado")
      .map((m) => m.mes.slice(0, 7))
      .sort()
      .reverse();
  }, [meses.data]);

  const [mesSel, setMesSel] = useState<string | null>(null);
  const mes = mesSel ?? disponibles[0] ?? null;

  const control = useQuery({
    queryKey: ["mes", mes, "control"],
    queryFn: () => vistaControl(mes as string),
    enabled: mes !== null,
  });

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-semibold">Vista Control</h2>
        {disponibles.length > 0 && (
          <label className="flex items-center gap-2 text-sm">
            <span className="text-slate-500">Mes</span>
            <select
              className="rounded-md border border-slate-300 px-3 py-1.5"
              value={mes ?? ""}
              onChange={(e) => setMesSel(e.target.value)}
            >
              {disponibles.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </label>
        )}
      </header>

      {meses.isLoading && <p className="text-sm text-slate-500">Cargando…</p>}
      {meses.data && disponibles.length === 0 && (
        <p className="text-sm text-slate-500">
          No hay meses en ejecución o cerrados. Aprueba el presupuesto de un mes
          para ver su control.
        </p>
      )}

      {control.isLoading && (
        <p className="text-sm text-slate-500">Cargando control…</p>
      )}
      {control.isError && (
        <p className="text-sm text-alert">
          No se pudo cargar la Vista Control.
        </p>
      )}

      {control.data && (
        <>
          <div className="flex flex-wrap gap-4">
            <TarjetaResumen
              titulo="Caja disponible"
              valor={formatCOP(control.data.caja_disponible)}
              acento="turq"
            />
            <TarjetaResumen
              titulo="Presupuesto definido"
              valor={formatCOP(control.data.total.definido)}
            />
            <TarjetaResumen
              titulo="Ejecutado"
              valor={formatCOP(control.data.total.ejecutado)}
            />
            <TarjetaResumen
              titulo="Disponible"
              valor={formatCOP(control.data.total.disponible)}
              acento="brand"
            />
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-slate-500">
                  <th className="py-2 pr-4">Rubro</th>
                  <th className="py-2 pr-4 text-right">Definido</th>
                  <th className="py-2 pr-4 text-right">Ejecutado</th>
                  <th className="py-2 pr-4 text-right">Disponible</th>
                  <th className="py-2 pr-4 text-right">% ejec.</th>
                  <th className="py-2 pr-4">Semáforo</th>
                </tr>
              </thead>
              <tbody>
                {control.data.grupos.map((g) => (
                  <GrupoBloque key={g.grupo} grupo={g} />
                ))}
                <tr className="border-t-2 border-slate-300 font-semibold">
                  <td className="py-2 pr-4">Total</td>
                  <td className="py-2 pr-4 text-right font-mono">
                    {formatCOP(control.data.total.definido)}
                  </td>
                  <td className="py-2 pr-4 text-right font-mono">
                    {formatCOP(control.data.total.ejecutado)}
                  </td>
                  <td className="py-2 pr-4 text-right font-mono">
                    {formatCOP(control.data.total.disponible)}
                  </td>
                  <td className="py-2 pr-4" />
                  <td className="py-2 pr-4" />
                </tr>
              </tbody>
            </table>
          </div>

          {control.data.sin_presupuesto.length > 0 && (
            <div className="rounded-md bg-warn/10 px-3 py-2 text-sm text-slate-700">
              <span className="font-medium text-warn">Sin presupuesto:</span>{" "}
              gastos en rubros sin línea definida este mes —{" "}
              {control.data.sin_presupuesto
                .map((s) => `${s.rubro} (${formatCOP(s.ejecutado)})`)
                .join(" · ")}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function TarjetaResumen({
  titulo,
  valor,
  acento,
}: {
  titulo: string;
  valor: string;
  acento?: "brand" | "turq";
}) {
  const color =
    acento === "brand"
      ? "text-brand"
      : acento === "turq"
        ? "text-turq"
        : "text-slate-800";
  return (
    <div className="min-w-40 flex-1 rounded-lg border border-slate-200 px-4 py-3">
      <p className="text-xs text-slate-500">{titulo}</p>
      <p className={`mt-1 font-mono text-lg font-semibold ${color}`}>{valor}</p>
    </div>
  );
}

function GrupoBloque({
  grupo,
}: {
  grupo: import("@/lib/control").ControlGrupo;
}) {
  return (
    <>
      <tr className="bg-slate-50">
        <td
          colSpan={6}
          className="py-1.5 pr-4 text-xs font-semibold uppercase tracking-wide text-slate-500"
        >
          {GRUPO_LABEL[grupo.grupo] ?? grupo.grupo}
        </td>
      </tr>
      {grupo.lineas.map((l) => (
        <tr key={l.rubro_id} className="border-b border-slate-100">
          <td className="py-2 pr-4">{l.rubro}</td>
          <td className="py-2 pr-4 text-right font-mono">
            {formatCOP(l.definido)}
          </td>
          <td className="py-2 pr-4 text-right font-mono">
            {formatCOP(l.ejecutado)}
          </td>
          <td className="py-2 pr-4 text-right font-mono">
            {formatCOP(l.disponible)}
          </td>
          <td className="py-2 pr-4 text-right font-mono text-slate-600">
            {l.pct_ejecutado === null ? "—" : `${l.pct_ejecutado}%`}
          </td>
          <td className="py-2 pr-4">
            <span
              title={SEMAFORO_LABEL[l.semaforo]}
              className={`rounded-full px-2 py-0.5 text-xs font-medium ${SEMAFORO_ESTILO[l.semaforo]}`}
            >
              {SEMAFORO_LABEL[l.semaforo]}
            </span>
          </td>
        </tr>
      ))}
      <tr className="border-b border-slate-200 text-slate-500">
        <td className="py-1.5 pr-4 text-right text-xs italic">Subtotal</td>
        <td className="py-1.5 pr-4 text-right font-mono text-xs">
          {formatCOP(grupo.subtotal.definido)}
        </td>
        <td className="py-1.5 pr-4 text-right font-mono text-xs">
          {formatCOP(grupo.subtotal.ejecutado)}
        </td>
        <td className="py-1.5 pr-4 text-right font-mono text-xs">
          {formatCOP(grupo.subtotal.disponible)}
        </td>
        <td className="py-1.5 pr-4" />
        <td className="py-1.5 pr-4" />
      </tr>
    </>
  );
}
