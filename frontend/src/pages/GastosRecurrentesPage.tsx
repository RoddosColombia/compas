// frontend/src/pages/GastosRecurrentesPage.tsx
//
// Gastos recurrentes (decisión CEO 2026-07-26): la plantilla administrable de los
// gastos fijos mensuales — conocer cada uno y cómo administrarlo. Cada gasto apunta a
// un rubro existente (hereda grupo/código del Plan de Cuentas). Es INFORMATIVO (no
// toca el motor). Los controles de mutación solo aparecen con rubros:gestionar
// (regla 9); la autoridad real la impone el backend. Montos con formatCOP (regla 1).

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useMemo, useState } from "react";

import { useAuth } from "@/auth/AuthContext";
import { PageHeader } from "@/components/layout/PageHeader";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { KpiTile } from "@/components/ui/kpi-tile";
import {
  FRECUENCIAS,
  type Frecuencia,
  GRUPO_LABEL,
  type GastoRecurrente,
  crearGasto,
  editarGasto,
  eliminarGasto,
  listarGastos,
} from "@/lib/gastosRecurrentes";
import { formatCOP } from "@/lib/money";
import { type Rubro, agruparRubros, listarRubros } from "@/lib/rubros";

const INPUT_CLASS =
  "w-full rounded-md border border-hairline bg-surface px-3 py-1.5 font-sans text-sm text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan";

const FREC_LABEL: Record<Frecuencia, string> = Object.fromEntries(
  FRECUENCIAS.map((f) => [f.valor, f.label]),
) as Record<Frecuencia, string>;

const montoOk = (s: string) => /^\d+(\.\d{1,2})?$/.test(s.trim());

export default function GastosRecurrentesPage() {
  const { puede } = useAuth();
  const gestiona = puede("rubros:gestionar");
  const qc = useQueryClient();
  const [mensaje, setMensaje] = useState<string | null>(null);
  const [dialogo, setDialogo] = useState<
    { modo: "crear" } | { modo: "editar"; gasto: GastoRecurrente } | null
  >(null);

  const gastos = useQuery({
    queryKey: ["gastos-recurrentes"],
    queryFn: listarGastos,
  });
  const rubros = useQuery({ queryKey: ["rubros"], queryFn: listarRubros });

  const alTerminar = {
    onSuccess: () => {
      setMensaje(null);
      setDialogo(null);
      qc.invalidateQueries({ queryKey: ["gastos-recurrentes"] });
    },
    onError: (e: unknown) =>
      setMensaje(e instanceof Error ? e.message : "Error"),
  };
  const crear = useMutation({ mutationFn: crearGasto, ...alTerminar });
  const editar = useMutation({ mutationFn: editarGasto, ...alTerminar });
  const eliminar = useMutation({ mutationFn: eliminarGasto, ...alTerminar });

  const items = gastos.data?.items ?? [];
  const resumen = gastos.data?.resumen;

  const gruposConTotal = useMemo(
    () => Object.entries(resumen?.por_grupo ?? {}),
    [resumen],
  );
  const activos = items.filter((g) => g.activo).length;

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        titulo="Gastos recurrentes"
        descripcion="La plantilla de todos tus gastos fijos: cuánto, con qué frecuencia y cómo administrarlos."
        acciones={
          gestiona ? (
            <Button
              variant="cyan"
              onClick={() => setDialogo({ modo: "crear" })}
            >
              Agregar gasto
            </Button>
          ) : undefined
        }
      />

      {mensaje && <AlertBanner variant="danger">{mensaje}</AlertBanner>}
      {gastos.isError && (
        <AlertBanner variant="danger">
          No se pudo cargar la plantilla de gastos.
        </AlertBanner>
      )}

      {/* KPIs */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
        <KpiTile
          label="Total mensual"
          value={resumen ? formatCOP(resumen.total) : "—"}
          sub="equivalente por mes"
        />
        <KpiTile label="Gastos activos" value={String(activos)} />
        <KpiTile label="Gastos en la plantilla" value={String(items.length)} />
      </div>

      {/* Resumen por grupo */}
      {gruposConTotal.length > 0 && (
        <Card>
          <CardTitle>Gasto mensual por grupo</CardTitle>
          <div className="mt-3 flex flex-col gap-1.5">
            {gruposConTotal.map(([grupo, total]) => (
              <div
                key={grupo}
                className="flex items-baseline justify-between border-b border-hairline/60 py-1.5 last:border-0"
              >
                <span className="font-sans text-sm text-ink-soft">
                  {GRUPO_LABEL[grupo] ?? grupo}
                </span>
                <span className="tabular font-medium text-ink">
                  {formatCOP(total)}
                </span>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Tabla */}
      {gastos.isLoading && (
        <p className="font-sans text-sm text-ink-soft">Cargando…</p>
      )}
      {gastos.data && items.length === 0 && (
        <p className="font-sans text-sm text-ink-soft">
          Aún no hay gastos en la plantilla.
          {gestiona ? " Agrega el primero con “Agregar gasto”." : ""}
        </p>
      )}

      {items.length > 0 && (
        <Card className="overflow-hidden p-0">
          <div className="overflow-x-auto">
            <table className="w-full font-sans text-sm">
              <thead>
                <tr className="border-b border-hairline text-left text-ink-faint">
                  <th className="px-4 py-2.5 font-semibold">Gasto</th>
                  <th className="px-4 py-2.5 font-semibold">Grupo / rubro</th>
                  <th className="px-4 py-2.5 text-right font-semibold">
                    Monto
                  </th>
                  <th className="px-4 py-2.5 font-semibold">Frecuencia</th>
                  <th className="px-4 py-2.5 text-right font-semibold">
                    Mensual
                  </th>
                  <th className="px-4 py-2.5 text-right font-semibold">Día</th>
                  {gestiona && <th className="px-4 py-2.5 font-semibold" />}
                </tr>
              </thead>
              <tbody>
                {items.map((g) => (
                  <tr
                    key={g.id}
                    className={`border-b border-hairline/60 last:border-0 ${
                      g.activo ? "" : "opacity-50"
                    }`}
                  >
                    <td className="px-4 py-2">
                      <div className="font-medium text-ink">
                        {g.descripcion}
                        {g.hasta && (
                          <span className="ml-2 rounded-full bg-amber/10 px-2 py-0.5 font-sans text-[10px] font-medium text-amber">
                            hasta {g.hasta}
                          </span>
                        )}
                      </div>
                      {g.notas && (
                        <div className="font-sans text-xs text-ink-faint">
                          {g.notas}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-2 text-ink-soft">
                      <div>{GRUPO_LABEL[g.rubro_grupo ?? ""] ?? "—"}</div>
                      <div className="font-sans text-xs text-ink-faint">
                        {g.rubro_codigo ? `${g.rubro_codigo} · ` : ""}
                        {g.rubro_nombre ?? "sin rubro"}
                      </div>
                    </td>
                    <td className="tabular px-4 py-2 text-right text-ink-soft">
                      {formatCOP(g.monto)}
                    </td>
                    <td className="px-4 py-2 text-ink-soft">
                      {FREC_LABEL[g.frecuencia]}
                    </td>
                    <td className="tabular px-4 py-2 text-right font-medium text-ink">
                      {formatCOP(g.monto_mensual)}
                    </td>
                    <td className="tabular px-4 py-2 text-right text-ink-soft">
                      {g.dia_pago ?? "—"}
                    </td>
                    {gestiona && (
                      <td className="px-4 py-2">
                        <div className="flex justify-end gap-2">
                          <button
                            type="button"
                            className="font-sans text-xs font-semibold text-cyan hover:underline"
                            onClick={() =>
                              setDialogo({ modo: "editar", gasto: g })
                            }
                          >
                            Editar
                          </button>
                          <button
                            type="button"
                            className="font-sans text-xs font-semibold text-ink-soft hover:underline"
                            onClick={() =>
                              editar.mutate({ id: g.id, activo: !g.activo })
                            }
                          >
                            {g.activo ? "Desactivar" : "Activar"}
                          </button>
                          <button
                            type="button"
                            className="font-sans text-xs font-semibold text-red hover:underline"
                            onClick={() => {
                              if (
                                window.confirm(
                                  `¿Eliminar “${g.descripcion}” de la plantilla?`,
                                )
                              )
                                eliminar.mutate(g.id);
                            }}
                          >
                            Eliminar
                          </button>
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {dialogo && (
        <GastoDialog
          rubros={rubros.data ?? []}
          gasto={dialogo.modo === "editar" ? dialogo.gasto : null}
          onCerrar={() => setDialogo(null)}
          onGuardar={(input) =>
            dialogo.modo === "editar"
              ? editar.mutate({ id: dialogo.gasto.id, ...input })
              : crear.mutate(input)
          }
          guardando={crear.isPending || editar.isPending}
        />
      )}
    </div>
  );
}

interface DialogInput {
  rubro_id: string;
  descripcion: string;
  monto: string;
  frecuencia: Frecuencia;
  dia_pago: number | null;
  hasta: string | null;
  notas: string | null;
}

function GastoDialog({
  rubros,
  gasto,
  onCerrar,
  onGuardar,
  guardando,
}: {
  rubros: Rubro[];
  gasto: GastoRecurrente | null;
  onCerrar: () => void;
  onGuardar: (input: DialogInput) => void;
  guardando: boolean;
}) {
  const activos = useMemo(
    () => agruparRubros(rubros.filter((r) => r.activo)),
    [rubros],
  );
  const [rubroId, setRubroId] = useState(gasto?.rubro_id ?? "");
  const [descripcion, setDescripcion] = useState(gasto?.descripcion ?? "");
  const [monto, setMonto] = useState(gasto?.monto ?? "");
  const [frecuencia, setFrecuencia] = useState<Frecuencia>(
    gasto?.frecuencia ?? "mensual",
  );
  const [diaPago, setDiaPago] = useState(
    gasto?.dia_pago != null ? String(gasto.dia_pago) : "",
  );
  const [hasta, setHasta] = useState(gasto?.hasta ?? "");
  const [notas, setNotas] = useState(gasto?.notas ?? "");
  const [error, setError] = useState<string | null>(null);

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!rubroId) return setError("Elige un rubro.");
    if (!descripcion.trim()) return setError("La descripción es obligatoria.");
    if (!montoOk(monto))
      return setError("El monto debe ser un número positivo.");
    let dia: number | null = null;
    if (diaPago.trim() !== "") {
      dia = Number(diaPago);
      if (!Number.isInteger(dia) || dia < 1 || dia > 31)
        return setError("El día de pago debe estar entre 1 y 31.");
    }
    onGuardar({
      rubro_id: rubroId,
      descripcion: descripcion.trim(),
      monto: monto.trim(),
      frecuencia,
      dia_pago: dia,
      hasta: hasta.trim() === "" ? null : hasta.trim(),
      notas: notas.trim() === "" ? null : notas.trim(),
    });
  }

  return (
    <div className="fixed inset-0 z-10 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-lg border border-hairline bg-surface p-6 shadow-lg">
        <h3 className="mb-4 font-display text-lg font-semibold text-ink">
          {gasto ? "Editar gasto" : "Agregar gasto recurrente"}
        </h3>
        <form
          onSubmit={onSubmit}
          className="flex flex-col gap-3 font-sans text-sm"
        >
          <label className="font-medium text-ink" htmlFor="g-rubro">
            Rubro (categoría del Plan de Cuentas)
          </label>
          <select
            id="g-rubro"
            className={INPUT_CLASS}
            value={rubroId}
            onChange={(e) => setRubroId(e.target.value)}
          >
            <option value="">— elige un rubro —</option>
            {[...activos.entries()].map(([grupo, lista]) => (
              <optgroup key={grupo} label={GRUPO_LABEL[grupo] ?? grupo}>
                {lista.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.codigo ? `${r.codigo} · ` : ""}
                    {r.nombre}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>

          <label className="font-medium text-ink" htmlFor="g-desc">
            Descripción
          </label>
          <input
            id="g-desc"
            className={INPUT_CLASS}
            placeholder="Arriendo oficina"
            value={descripcion}
            onChange={(e) => setDescripcion(e.target.value)}
          />

          <div className="flex gap-3">
            <div className="flex-1">
              <label className="font-medium text-ink" htmlFor="g-monto">
                Monto (COP)
              </label>
              <input
                id="g-monto"
                inputMode="decimal"
                className={`tabular ${INPUT_CLASS}`}
                placeholder="3614953"
                value={monto}
                onChange={(e) => setMonto(e.target.value)}
              />
            </div>
            <div className="flex-1">
              <label className="font-medium text-ink" htmlFor="g-frec">
                Frecuencia
              </label>
              <select
                id="g-frec"
                className={INPUT_CLASS}
                value={frecuencia}
                onChange={(e) => setFrecuencia(e.target.value as Frecuencia)}
              >
                {FRECUENCIAS.map((f) => (
                  <option key={f.valor} value={f.valor}>
                    {f.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="flex gap-3">
            <div className="flex-1">
              <label className="font-medium text-ink" htmlFor="g-dia">
                Día de pago (opcional)
              </label>
              <input
                id="g-dia"
                inputMode="numeric"
                className={`tabular ${INPUT_CLASS}`}
                placeholder="5"
                value={diaPago}
                onChange={(e) => setDiaPago(e.target.value)}
              />
            </div>
            <div className="flex-1">
              <label className="font-medium text-ink" htmlFor="g-hasta">
                Hasta (opcional)
              </label>
              <input
                id="g-hasta"
                type="month"
                className={INPUT_CLASS}
                value={hasta}
                onChange={(e) => setHasta(e.target.value)}
              />
            </div>
          </div>

          <label className="font-medium text-ink" htmlFor="g-notas">
            Cómo administrarlo (opcional)
          </label>
          <textarea
            id="g-notas"
            className={INPUT_CLASS}
            rows={2}
            placeholder="Proveedor, contrato, si es cancelable…"
            value={notas}
            onChange={(e) => setNotas(e.target.value)}
          />

          {error && <AlertBanner variant="danger">{error}</AlertBanner>}
          <div className="mt-2 flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onCerrar}>
              Cancelar
            </Button>
            <Button type="submit" variant="cyan" disabled={guardando}>
              {guardando ? "Guardando…" : "Guardar"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
