// frontend/src/pages/MetasPage.tsx
//
// Metas de ingreso (D2 §6): página de "Planeación y control". Bloque del mes en curso
// (meta · real ejecutado · % · barra), acumulado del año (tabla por mes + totales) y
// CRUD (crear/editar/eliminar) gated por proyeccion:gestionar (regla 9: el backend
// autoriza; el front solo esconde controles). Es INFORMATIVA: no toca el motor ni la
// caja. Montos string (regla 1) + decimal.js-light para las sumas del acumulado.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Decimal from "decimal.js-light";
import { type FormEvent, useState } from "react";

import { useAuth } from "@/auth/AuthContext";
import { PageHeader } from "@/components/layout/PageHeader";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { Cargando } from "@/components/ui/cargando";
import { ErrorEstado } from "@/components/ui/error-estado";
import {
  LINEA_INICIAL,
  LINEA_SEMANAL,
  type LineaMeta,
  type Meta,
  type MetaCrearInput,
  crearMeta,
  editarMeta,
  eliminarMeta,
  listarMetas,
} from "@/lib/metas";
import { formatCOP, parseMonto } from "@/lib/money";

const RE_MONTO = /^\d+(\.\d{1,2})?$/;
const RE_MES = /^\d{4}-(0[1-9]|1[0-2])$/;

function mesCalendarioActual(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export default function MetasPage() {
  const { puede } = useAuth();
  const qc = useQueryClient();
  const gestiona = puede("proyeccion:gestionar");

  const metas = useQuery({ queryKey: ["metas-ingreso"], queryFn: listarMetas });
  const items = metas.data?.items ?? [];

  const mesActual = mesCalendarioActual();
  const anio = mesActual.slice(0, 4);
  const metaActual = items.find((m) => m.mes === mesActual) ?? null;
  const delAnio = items
    .filter((m) => m.mes.startsWith(anio))
    .sort((a, b) => a.mes.localeCompare(b.mes));

  const [dialogo, setDialogo] = useState<
    { modo: "crear"; mes: string } | { modo: "editar"; meta: Meta } | null
  >(null);
  const [aBorrar, setABorrar] = useState<Meta | null>(null);

  const invalidar = () => qc.invalidateQueries({ queryKey: ["metas-ingreso"] });

  const eliminar = useMutation({
    mutationFn: (id: string) => eliminarMeta(id),
    onSuccess: () => {
      setABorrar(null);
      invalidar();
    },
  });

  if (metas.isLoading) return <Cargando variante="card" />;
  if (metas.isError) {
    return (
      <ErrorEstado
        mensaje="No se pudieron cargar las metas de ingreso."
        onReintentar={() => void metas.refetch()}
      />
    );
  }

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        titulo="Metas de ingreso"
        descripcion="La meta de recaudo por mes vs. el ingreso real ejecutado (sin reversas ni tránsito). Informativa: no toca el motor."
        acciones={
          gestiona ? (
            <Button
              variant="cyan"
              onClick={() => setDialogo({ modo: "crear", mes: mesActual })}
            >
              Nueva meta
            </Button>
          ) : undefined
        }
      />

      <BloqueMesActual
        mes={mesActual}
        meta={metaActual}
        puedeDefinir={gestiona}
        onDefinir={() => setDialogo({ modo: "crear", mes: mesActual })}
      />

      <AcumuladoAnio
        anio={anio}
        metas={delAnio}
        gestiona={gestiona}
        onEditar={(m) => setDialogo({ modo: "editar", meta: m })}
        onEliminar={(m) => setABorrar(m)}
      />

      {dialogo && (
        <MetaDialog
          modo={dialogo.modo}
          mesInicial={dialogo.modo === "crear" ? dialogo.mes : dialogo.meta.mes}
          metaInicial={dialogo.modo === "editar" ? dialogo.meta : null}
          onGuardar={async (mes, valor, lineas) => {
            if (dialogo.modo === "crear") {
              const input: MetaCrearInput = { mes, valor, lineas };
              await crearMeta(input);
            } else {
              await editarMeta({ id: dialogo.meta.id, valor, lineas });
            }
            setDialogo(null);
            invalidar();
          }}
          onCerrar={() => setDialogo(null)}
        />
      )}

      {aBorrar && (
        <ConfirmarBorrado
          meta={aBorrar}
          pendiente={eliminar.isPending}
          error={eliminar.isError ? (eliminar.error as Error).message : null}
          onConfirmar={() => eliminar.mutate(aBorrar.id)}
          onCerrar={() => setABorrar(null)}
        />
      )}
    </div>
  );
}

function pctNumero(meta: Meta): number | null {
  if (meta.pct_cumplimiento === null) return null;
  const n = Number.parseFloat(meta.pct_cumplimiento);
  return Number.isFinite(n) ? n : null;
}

function BloqueMesActual({
  mes,
  meta,
  puedeDefinir,
  onDefinir,
}: {
  mes: string;
  meta: Meta | null;
  puedeDefinir: boolean;
  onDefinir: () => void;
}) {
  if (meta === null) {
    return (
      <Card className="flex flex-col items-start gap-3">
        <CardTitle>Mes en curso · {mes}</CardTitle>
        <p className="font-sans text-cuerpo text-ink-soft">
          Sin meta definida para {mes}.{" "}
          {!puedeDefinir && (
            <span className="text-ink-faint">(financiero o admin)</span>
          )}
        </p>
        {puedeDefinir && (
          <Button variant="cyan" size="sm" onClick={onDefinir}>
            Definir meta
          </Button>
        )}
      </Card>
    );
  }

  const pct = pctNumero(meta);
  const superada = pct !== null && pct > 100;
  const ancho = pct === null ? 0 : Math.min(100, Math.max(0, pct));

  return (
    <Card className="flex flex-col gap-3" data-testid="mes-actual">
      <CardTitle>Mes en curso · {mes}</CardTitle>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Cifra rotulo="Meta del mes" valor={formatCOP(meta.valor)} />
        <Cifra
          rotulo="Real ejecutado"
          valor={
            meta.real_ejecutado !== null ? formatCOP(meta.real_ejecutado) : "—"
          }
        />
        <Cifra
          rotulo="Cumplimiento"
          valor={
            pct !== null ? `${meta.pct_cumplimiento?.replace(".", ",")} %` : "—"
          }
          resaltado={superada}
        />
      </div>
      {pct !== null && (
        <div className="flex flex-col gap-1">
          {/* biome-ignore lint/a11y/useFocusableInteractive: progressbar es un
              indicador de solo lectura, no un control interactivo (no debe estar
              en el orden de tabulación). */}
          <div
            role="progressbar"
            aria-valuenow={Math.round(pct)}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`Cumplimiento ${mes}`}
            className="h-2.5 w-full overflow-hidden rounded-full bg-surface-muted"
          >
            <div
              className={`h-full rounded-full ${superada ? "bg-positivo" : "bg-cyan"}`}
              style={{ width: `${ancho}%` }}
            />
          </div>
          {superada && (
            <span className="font-sans text-apoyo font-medium text-positivo">
              Meta superada
            </span>
          )}
        </div>
      )}
      <DesgloseMeta meta={meta} />
    </Card>
  );
}

/** PTS6-E: las 2 líneas de la meta (Cuota inicial / Cuotas semanales) con su real
 * por concepto. Se muestra solo si la meta trae líneas; el real por concepto puede
 * ser "—" hasta que se clasifiquen los ingresos al rubro 0120. */
function DesgloseMeta({ meta }: { meta: Meta }) {
  const lineaMeta = (nombre: string): string | null =>
    meta.lineas.find((l) => l.nombre === nombre)?.valor ?? null;
  const filas: { nombre: string; meta: string | null; real: string | null }[] =
    [
      {
        nombre: LINEA_INICIAL,
        meta: lineaMeta(LINEA_INICIAL),
        real: meta.real_inicial,
      },
      {
        nombre: LINEA_SEMANAL,
        meta: lineaMeta(LINEA_SEMANAL),
        real: meta.real_semanal,
      },
    ];
  // sin líneas canónicas ni desglose real → no aporta (candado)
  if (filas.every((f) => f.meta === null) && meta.real_inicial === null)
    return null;
  return (
    <div className="mt-1 border-t border-hairline pt-3">
      <div className="mb-2 font-sans text-apoyo text-ink-faint uppercase tracking-wide">
        Desglose: cuota inicial vs. cuotas semanales
      </div>
      <div className="overflow-x-auto">
        <table className="w-full font-sans text-sm">
          <thead>
            <tr className="text-left text-ink-faint">
              <th className="py-1 pr-4 font-semibold">Concepto</th>
              <th className="py-1 px-4 text-right font-semibold">Meta</th>
              <th className="py-1 pl-4 text-right font-semibold">Real</th>
            </tr>
          </thead>
          <tbody>
            {filas.map((f) => (
              <tr key={f.nombre} className="border-t border-hairline/50">
                <td className="py-1.5 pr-4 text-ink">{f.nombre}</td>
                <td className="tabular py-1.5 px-4 text-right text-ink-soft">
                  {f.meta !== null ? formatCOP(f.meta) : "—"}
                </td>
                <td className="tabular py-1.5 pl-4 text-right text-ink-soft">
                  {f.real !== null ? formatCOP(f.real) : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Cifra({
  rotulo,
  valor,
  resaltado,
}: {
  rotulo: string;
  valor: string;
  resaltado?: boolean;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="font-sans text-apoyo text-ink-faint">{rotulo}</span>
      <span
        className={`tabular font-display text-xl font-semibold ${resaltado ? "text-positivo" : "text-ink"}`}
      >
        {valor}
      </span>
    </div>
  );
}

function AcumuladoAnio({
  anio,
  metas,
  gestiona,
  onEditar,
  onEliminar,
}: {
  anio: string;
  metas: Meta[];
  gestiona: boolean;
  onEditar: (m: Meta) => void;
  onEliminar: (m: Meta) => void;
}) {
  const totalMeta = metas.reduce(
    (a, m) => a.plus(parseMonto(m.valor)),
    new Decimal(0),
  );
  const totalReal = metas.reduce(
    (a, m) =>
      a.plus(m.real_ejecutado !== null ? parseMonto(m.real_ejecutado) : 0),
    new Decimal(0),
  );
  const pctTotal = totalMeta.greaterThan(0)
    ? totalReal.div(totalMeta).times(100)
    : null;

  return (
    <Card className="flex flex-col gap-3 p-0">
      <div className="px-5 pt-5">
        <CardTitle>Acumulado {anio}</CardTitle>
      </div>
      {metas.length === 0 ? (
        <div className="px-5 pb-5">
          <p className="font-sans text-sm text-ink-soft">
            Aún no hay metas registradas para {anio}.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full font-sans text-sm">
            <thead>
              <tr className="border-b border-hairline text-left text-ink-faint">
                <th className="px-5 py-2.5 font-semibold">Mes</th>
                <th className="px-5 py-2.5 text-right font-semibold">Meta</th>
                <th className="px-5 py-2.5 text-right font-semibold">Real</th>
                <th className="px-5 py-2.5 text-right font-semibold">%</th>
                {gestiona && (
                  <th className="px-5 py-2.5 text-right font-semibold">
                    <span className="sr-only">Acciones</span>
                  </th>
                )}
              </tr>
            </thead>
            <tbody>
              {metas.map((m) => {
                const pct = pctNumero(m);
                return (
                  <tr
                    key={m.id}
                    className="border-b border-hairline/60 last:border-0"
                  >
                    <td className="px-5 py-2 font-medium text-ink">{m.mes}</td>
                    <td className="tabular px-5 py-2 text-right text-ink-soft">
                      {formatCOP(m.valor)}
                    </td>
                    <td className="tabular px-5 py-2 text-right text-ink-soft">
                      {m.real_ejecutado !== null
                        ? formatCOP(m.real_ejecutado)
                        : "—"}
                    </td>
                    <td
                      className={`tabular px-5 py-2 text-right font-medium ${pct !== null && pct > 100 ? "text-positivo" : "text-ink-soft"}`}
                    >
                      {m.pct_cumplimiento !== null
                        ? `${m.pct_cumplimiento.replace(".", ",")} %`
                        : "—"}
                    </td>
                    {gestiona && (
                      <td className="px-5 py-2 text-right whitespace-nowrap">
                        <button
                          type="button"
                          className="font-medium text-cyan hover:underline"
                          onClick={() => onEditar(m)}
                        >
                          Editar
                        </button>
                        <button
                          type="button"
                          className="ml-3 font-medium text-critico hover:underline"
                          onClick={() => onEliminar(m)}
                        >
                          Eliminar
                        </button>
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
            <tfoot>
              <tr
                data-testid="acumulado-totales"
                className="border-t border-hairline font-medium text-ink"
              >
                <td className="px-5 py-2.5">Total</td>
                <td className="tabular px-5 py-2.5 text-right">
                  {formatCOP(totalMeta)}
                </td>
                <td className="tabular px-5 py-2.5 text-right">
                  {formatCOP(totalReal)}
                </td>
                <td className="tabular px-5 py-2.5 text-right">
                  {pctTotal !== null
                    ? `${pctTotal.toFixed(1).replace(".", ",")} %`
                    : "—"}
                </td>
                {gestiona && <td />}
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </Card>
  );
}

function MetaDialog({
  modo,
  mesInicial,
  metaInicial,
  onGuardar,
  onCerrar,
}: {
  modo: "crear" | "editar";
  mesInicial: string;
  metaInicial: Meta | null;
  onGuardar: (mes: string, valor: string, lineas: LineaMeta[]) => Promise<void>;
  onCerrar: () => void;
}) {
  const lineaInicial = (nombre: string) =>
    metaInicial?.lineas.find((l) => l.nombre === nombre)?.valor ?? "";
  const [mes, setMes] = useState(mesInicial);
  const [inicial, setInicial] = useState(lineaInicial(LINEA_INICIAL));
  const [semanal, setSemanal] = useState(lineaInicial(LINEA_SEMANAL));
  const [error, setError] = useState<string | null>(null);
  const [pendiente, setPendiente] = useState(false);

  // El total de la meta es la SUMA de las 2 líneas (no se teclea aparte): así la
  // meta siempre está partida y cuadra por construcción.
  const total =
    RE_MONTO.test(inicial.trim()) && RE_MONTO.test(semanal.trim())
      ? parseMonto(inicial.trim()).plus(semanal.trim())
      : null;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (modo === "crear" && !RE_MES.test(mes)) {
      setError("El mes debe tener el formato YYYY-MM.");
      return;
    }
    if (!RE_MONTO.test(inicial.trim()) || !RE_MONTO.test(semanal.trim())) {
      setError(
        "Cuota inicial y Cuotas semanales deben ser números válidos (COP).",
      );
      return;
    }
    if (total === null || total.lessThanOrEqualTo(0)) {
      setError("El total de la meta (inicial + semanales) debe ser mayor a 0.");
      return;
    }
    const lineas: LineaMeta[] = [
      { nombre: LINEA_INICIAL, valor: inicial.trim() },
      { nombre: LINEA_SEMANAL, valor: semanal.trim() },
    ];
    setPendiente(true);
    try {
      await onGuardar(mes, total.toString(), lineas);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "No se pudo guardar la meta",
      );
      setPendiente(false);
    }
  }

  return (
    <div className="fixed inset-0 z-20 flex items-center justify-center bg-black/40 p-4">
      <dialog
        open
        aria-label={modo === "crear" ? "Nueva meta" : "Editar meta"}
        className="static w-full max-w-md rounded-lg border border-hairline bg-surface p-6 text-inherit shadow-lg"
      >
        <h3 className="mb-4 font-display text-lg font-semibold text-ink">
          {modo === "crear"
            ? "Nueva meta de ingreso"
            : `Editar meta ${mesInicial}`}
        </h3>
        <form
          onSubmit={onSubmit}
          className="flex flex-col gap-3 font-sans text-sm"
        >
          {modo === "crear" ? (
            <label className="flex flex-col gap-1">
              <span className="font-medium text-ink">Mes (YYYY-MM)</span>
              <input
                type="month"
                required
                className="rounded-md border border-hairline bg-surface px-3 py-1.5 text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan"
                value={mes}
                onChange={(e) => setMes(e.target.value)}
              />
            </label>
          ) : (
            <p className="text-ink-soft">
              Mes <span className="font-medium text-ink">{mesInicial}</span>
            </p>
          )}
          <label className="flex flex-col gap-1">
            <span className="font-medium text-ink">Cuota inicial (COP)</span>
            <input
              inputMode="decimal"
              placeholder="60000000"
              aria-label="Cuota inicial"
              className="tabular rounded-md border border-hairline bg-surface px-3 py-1.5 text-right text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan"
              value={inicial}
              onChange={(e) => setInicial(e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="font-medium text-ink">Cuotas semanales (COP)</span>
            <input
              inputMode="decimal"
              placeholder="200000000"
              aria-label="Cuotas semanales"
              className="tabular rounded-md border border-hairline bg-surface px-3 py-1.5 text-right text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan"
              value={semanal}
              onChange={(e) => setSemanal(e.target.value)}
            />
          </label>
          <div className="flex items-center justify-between border-t border-hairline pt-2 font-medium text-ink">
            <span>Total de la meta</span>
            <span className="tabular" data-testid="meta-total">
              {total !== null ? formatCOP(total) : "—"}
            </span>
          </div>

          {error && <AlertBanner variant="danger">{error}</AlertBanner>}

          <div className="mt-2 flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onCerrar}>
              Cancelar
            </Button>
            <Button type="submit" variant="cyan" disabled={pendiente}>
              {pendiente ? "Guardando…" : "Guardar"}
            </Button>
          </div>
        </form>
      </dialog>
    </div>
  );
}

function ConfirmarBorrado({
  meta,
  pendiente,
  error,
  onConfirmar,
  onCerrar,
}: {
  meta: Meta;
  pendiente: boolean;
  error: string | null;
  onConfirmar: () => void;
  onCerrar: () => void;
}) {
  return (
    <div className="fixed inset-0 z-20 flex items-center justify-center bg-black/40 p-4">
      <dialog
        open
        aria-label="Eliminar meta"
        className="static w-full max-w-sm rounded-lg border border-hairline bg-surface p-6 text-inherit shadow-lg"
      >
        <h3 className="mb-2 font-display text-lg font-semibold text-ink">
          Eliminar meta {meta.mes}
        </h3>
        <p className="mb-4 font-sans text-sm text-ink-soft">
          La meta de {meta.mes} ({formatCOP(meta.valor)}) se dará de baja. Es
          reversible creando una nueva.
        </p>
        {error && (
          <AlertBanner variant="danger">
            <span className="text-sm">{error}</span>
          </AlertBanner>
        )}
        <div className="mt-4 flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onCerrar}>
            Cancelar
          </Button>
          <Button
            type="button"
            variant="outline"
            className="border-critico/40 text-critico hover:bg-critico/10"
            disabled={pendiente}
            onClick={onConfirmar}
          >
            {pendiente ? "Eliminando…" : "Eliminar"}
          </Button>
        </div>
      </dialog>
    </div>
  );
}
