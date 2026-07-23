// frontend/src/pages/ControlPage.tsx
//
// Vista Control (Sprint 4, cara del demo G3): presupuesto definido vs ejecutado
// vs disponible por rubro y grupo, con semáforo (verde/amarillo/rojo). Selector de
// mes (solo meses en ejecución o cerrados). Montos con formatCOP (regla 1); el
// cálculo y el semáforo vienen del backend — el front solo presenta (Spec §17).

import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import {
  BANCO_LABEL,
  type ControlPorCuenta,
  GRUPO_LABEL,
  type Semaforo,
  vistaControl,
  vistaControlPorCuenta,
} from "@/lib/control";
import { listarMeses } from "@/lib/meses";
import { formatCOP } from "@/lib/money";

type Vista = "categoria" | "cuenta";

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
  const [vista, setVista] = useState<Vista>("categoria");

  const control = useQuery({
    queryKey: ["mes", mes, "control"],
    queryFn: () => vistaControl(mes as string),
    enabled: mes !== null && vista === "categoria",
  });

  const porCuenta = useQuery({
    queryKey: ["mes", mes, "control-por-cuenta"],
    queryFn: () => vistaControlPorCuenta(mes as string),
    enabled: mes !== null && vista === "cuenta",
  });

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-4">
          <h2 className="text-xl font-semibold">Vista Control</h2>
          <div className="flex rounded-md border border-slate-300 text-sm">
            <button
              type="button"
              onClick={() => setVista("categoria")}
              className={`rounded-l-md px-3 py-1 ${vista === "categoria" ? "bg-brand text-white" : "text-slate-600"}`}
            >
              Por categoría
            </button>
            <button
              type="button"
              onClick={() => setVista("cuenta")}
              className={`rounded-r-md px-3 py-1 ${vista === "cuenta" ? "bg-brand text-white" : "text-slate-600"}`}
            >
              Por cuenta
            </button>
          </div>
        </div>
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

      {vista === "cuenta" && (
        <MatrizPorCuenta
          cargando={porCuenta.isLoading}
          error={porCuenta.isError}
          data={porCuenta.data}
        />
      )}

      {meses.isLoading && <p className="text-sm text-slate-500">Cargando…</p>}
      {meses.data && disponibles.length === 0 && (
        <p className="text-sm text-slate-500">
          No hay meses en ejecución o cerrados. Aprueba el presupuesto de un mes
          para ver su control.
        </p>
      )}

      {vista === "categoria" && control.isLoading && (
        <p className="text-sm text-slate-500">Cargando control…</p>
      )}
      {vista === "categoria" && control.isError && (
        <p className="text-sm text-alert">
          No se pudo cargar la Vista Control.
        </p>
      )}

      {vista === "categoria" && control.data && (
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

function MatrizPorCuenta({
  cargando,
  error,
  data,
}: {
  cargando: boolean;
  error: boolean;
  data: ControlPorCuenta | undefined;
}) {
  if (cargando)
    return <p className="text-sm text-slate-500">Cargando por cuenta…</p>;
  if (error)
    return (
      <p className="text-sm text-alert">
        No se pudo cargar la vista por cuenta.
      </p>
    );
  if (!data) return null;
  if (data.bancos.length === 0)
    return (
      <p className="text-sm text-slate-500">
        Aún no hay egresos con banco en este mes.
      </p>
    );

  const bancos = data.bancos;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-left text-slate-500">
            <th className="py-2 pr-4">Rubro</th>
            {bancos.map((b) => (
              <th key={b} className="py-2 pr-4 text-right">
                {BANCO_LABEL[b] ?? b}
              </th>
            ))}
            <th className="py-2 pr-4 text-right">Total</th>
          </tr>
        </thead>
        <tbody>
          {data.grupos.map((g) => (
            <MatrizGrupo key={g.grupo} grupo={g} bancos={bancos} />
          ))}
          <tr className="border-t-2 border-slate-300 font-semibold">
            <td className="py-2 pr-4">Total</td>
            {bancos.map((b) => (
              <td key={b} className="py-2 pr-4 text-right font-mono">
                {formatCOP(data.total.por_banco[b])}
              </td>
            ))}
            <td className="py-2 pr-4 text-right font-mono">
              {formatCOP(data.total.total)}
            </td>
          </tr>
        </tbody>
      </table>

      {data.sin_presupuesto.length > 0 && (
        <div className="mt-4 rounded-md bg-warn/10 px-3 py-2 text-sm text-slate-700">
          <span className="font-medium text-warn">Sin presupuesto:</span>{" "}
          {data.sin_presupuesto
            .map(
              (s) =>
                `${s.rubro} (${bancos
                  .filter((b) => s.por_banco[b] && s.por_banco[b] !== "0.00")
                  .map(
                    (b) =>
                      `${BANCO_LABEL[b] ?? b} ${formatCOP(s.por_banco[b])}`,
                  )
                  .join(", ")})`,
            )
            .join(" · ")}
        </div>
      )}
    </div>
  );
}

function MatrizGrupo({
  grupo,
  bancos,
}: {
  grupo: import("@/lib/control").ControlCuentaGrupo;
  bancos: string[];
}) {
  return (
    <>
      <tr className="bg-slate-50">
        <td
          colSpan={bancos.length + 2}
          className="py-1.5 pr-4 text-xs font-semibold uppercase tracking-wide text-slate-500"
        >
          {GRUPO_LABEL[grupo.grupo] ?? grupo.grupo}
        </td>
      </tr>
      {grupo.lineas.map((l) => (
        <tr key={l.rubro_id} className="border-b border-slate-100">
          <td className="py-2 pr-4">{l.rubro}</td>
          {bancos.map((b) => (
            <td key={b} className="py-2 pr-4 text-right font-mono">
              {formatCOP(l.por_banco[b])}
            </td>
          ))}
          <td className="py-2 pr-4 text-right font-mono font-medium">
            {formatCOP(l.total)}
          </td>
        </tr>
      ))}
      <tr className="border-b border-slate-200 text-slate-500">
        <td className="py-1.5 pr-4 text-right text-xs italic">Subtotal</td>
        {bancos.map((b) => (
          <td key={b} className="py-1.5 pr-4 text-right font-mono text-xs">
            {formatCOP(grupo.subtotal.por_banco[b])}
          </td>
        ))}
        <td className="py-1.5 pr-4 text-right font-mono text-xs">
          {formatCOP(grupo.subtotal.total)}
        </td>
      </tr>
    </>
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
