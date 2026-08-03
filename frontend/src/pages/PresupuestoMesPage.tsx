// frontend/src/pages/PresupuestoMesPage.tsx
//
// Sprint C1 "cerrar el ciclo": generar sugerido → acotar líneas → aprobar (US-02).
// Solo frontend: los 3 endpoints ya existen y el backend impone las reglas de
// estado; aquí no hay optimistic UI — el monto es sagrado, se muestra lo que
// devuelva el backend. Montos como string + money.ts (regla 1); botones según
// capacidades (regla 9); aprobar con Idempotency-Key generada UNA vez por
// apertura del diálogo (reintentos del mismo diálogo la reusan — replay §1.12).

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Decimal from "decimal.js-light";
import { type FormEvent, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { useAuth } from "@/auth/AuthContext";
import { CicloStepper } from "@/components/ciclo/CicloStepper";
import { PageHeader } from "@/components/layout/PageHeader";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { GRUPO_LABEL } from "@/lib/control";
import { listarMeses } from "@/lib/meses";
import { formatCOP, parseMonto } from "@/lib/money";
import {
  type LineaPresupuesto,
  acotarLinea,
  aprobarPresupuesto,
  generarSugerido,
  listarPresupuesto,
} from "@/lib/presupuesto";
import { type Rubro, listarRubros } from "@/lib/rubros";

// Orden canónico de los grupos del plan de cuentas (mismo agrupado que Categorías).
const ORDEN_GRUPOS = [
  "ingresos_operativos",
  "costo_producto",
  "operacion",
  "nomina",
  "deudas_obligaciones",
  "otros",
];

export default function PresupuestoMesPage() {
  const { mes } = useParams(); // YYYY-MM
  const { puede } = useAuth();
  const qc = useQueryClient();
  const navigate = useNavigate();

  const meses = useQuery({ queryKey: ["meses"], queryFn: listarMeses });
  const mesCtl = meses.data?.items.find((m) => m.mes === `${mes}-01`);

  const presupuesto = useQuery({
    queryKey: ["presupuesto", mes],
    queryFn: () => listarPresupuesto(mes as string),
    enabled: !!mesCtl,
  });
  const rubros = useQuery({ queryKey: ["rubros"], queryFn: listarRubros });

  // FIX-G1: el presupuesto se acota en sugerido/propuesto (pre-aprobación) Y en
  // ejecución (re-acotación de un presupuesto ya aprobado, con comentario obligatorio).
  // Solo cerrado —y el legado definido— quedan de solo lectura.
  const estado = mesCtl?.estado;
  const preAprobacion = estado === "sugerido" || estado === "propuesto";
  const enEjecucion = estado === "en_ejecucion";
  const acotable = preAprobacion || enEjecucion;
  const lineas = presupuesto.data?.lineas ?? [];
  const sinLineas = lineas.length === 0;

  // Totales con decimal.js-light sobre los string de la API (regla 1: sin float).
  // "Definido" usa el sugerido como respaldo porque al aprobar el backend fija
  // monto_definido = monto_sugerido donde siga en null (D2).
  const totales = useMemo(() => {
    let sugerido = new Decimal(0);
    let definido = new Decimal(0);
    for (const ln of lineas) {
      sugerido = sugerido.plus(parseMonto(ln.monto_sugerido));
      definido = definido.plus(
        parseMonto(ln.monto_definido ?? ln.monto_sugerido),
      );
    }
    return { sugerido, definido, diferencia: definido.minus(sugerido) };
  }, [lineas]);

  // Agrupar líneas por grupo del rubro, en el orden del plan de cuentas.
  const grupos = useMemo(() => {
    const porId = new Map<string, Rubro>(
      (rubros.data ?? []).map((r) => [r.id, r]),
    );
    const out = new Map<string, { linea: LineaPresupuesto; rubro?: Rubro }[]>();
    for (const ln of lineas) {
      const rubro = porId.get(ln.rubro_id);
      const grupo = rubro?.grupo ?? "otros";
      if (!out.has(grupo)) out.set(grupo, []);
      out.get(grupo)?.push({ linea: ln, rubro });
    }
    for (const filas of out.values()) {
      filas.sort((a, b) => (a.rubro?.orden ?? 9999) - (b.rubro?.orden ?? 9999));
    }
    return ORDEN_GRUPOS.filter((g) => out.has(g)).map((g) => ({
      grupo: g,
      filas: out.get(g) ?? [],
    }));
  }, [lineas, rubros.data]);

  // Aprobación: key idempotente generada UNA vez al abrir el diálogo.
  const [aprobarKey, setAprobarKey] = useState<string | null>(null);
  const [aprobarError, setAprobarError] = useState<string | null>(null);
  const aprobar = useMutation({
    mutationFn: () => aprobarPresupuesto(mes as string, aprobarKey as string),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["meses"] });
      qc.invalidateQueries({ queryKey: ["presupuesto", mes] });
      navigate("/control");
    },
    onError: (e) =>
      setAprobarError(e instanceof Error ? e.message : "Error al aprobar"),
  });

  if (meses.isLoading) {
    return <p className="p-1 font-sans text-sm text-ink-soft">Cargando…</p>;
  }
  if (meses.isError) {
    return (
      <AlertBanner variant="danger">No se pudo listar los meses.</AlertBanner>
    );
  }
  if (meses.data && !mesCtl) {
    return (
      <div className="flex flex-col gap-4">
        <PageHeader
          titulo={`Presupuesto ${mes}`}
          descripcion="Este mes no está abierto."
        />
        <p className="font-sans text-sm text-ink-soft">
          Abre el mes primero en{" "}
          <Link to="/meses" className="font-medium text-cyan underline">
            Ciclo mensual
          </Link>
          .
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5 pb-24">
      <PageHeader
        titulo={`Presupuesto ${mes}`}
        descripcion="Genera el sugerido, acota los rubros y aprueba para poner el mes en ejecución."
      />

      {/* Stepper del ciclo (compartido con la Cabina, C2) */}
      <Card className="px-4 py-3">
        <CicloStepper
          estado={mesCtl?.estado ?? "sugerido"}
          sinLineas={sinLineas}
        />
      </Card>

      {/* Estado sugerido sin líneas → CTA generar */}
      {preAprobacion && sinLineas && !presupuesto.isLoading && (
        <GenerarSugeridoCard
          mes={mes as string}
          puedeGenerar={puede("ciclo:abrir")}
          alGenerar={() => {
            qc.invalidateQueries({ queryKey: ["presupuesto", mes] });
            qc.invalidateQueries({ queryKey: ["meses"] });
          }}
        />
      )}

      {!acotable && (
        <AlertBanner variant="ok">
          {estado === "cerrado"
            ? "El mes está cerrado: el presupuesto es inmutable."
            : "El presupuesto ya fue aprobado: solo lectura."}{" "}
          <Link to="/control" className="font-semibold underline">
            Ver el control del mes →
          </Link>
        </AlertBanner>
      )}

      {/* FIX-G1: en ejecución la re-acotación está permitida, pero justificada. */}
      {enEjecucion && (
        <AlertBanner variant="warn">
          El presupuesto está en ejecución: puedes ajustar montos, pero cada
          cambio requiere un comentario que lo justifique.{" "}
          <Link to="/control" className="font-semibold underline">
            Ver el control del mes →
          </Link>
        </AlertBanner>
      )}

      {presupuesto.isLoading && mesCtl && (
        <p className="font-sans text-sm text-ink-soft">Cargando presupuesto…</p>
      )}
      {presupuesto.isError && (
        <AlertBanner variant="danger">
          No se pudo cargar el presupuesto del mes.
        </AlertBanner>
      )}

      {!sinLineas && (
        <Card className="overflow-hidden p-0">
          <div className="overflow-x-auto">
            <table className="w-full font-sans text-sm">
              <thead>
                <tr className="border-b border-hairline text-left text-ink-faint">
                  <th className="px-4 py-2.5 font-semibold">Rubro</th>
                  <th className="px-4 py-2.5 text-right font-semibold">
                    Sugerido
                  </th>
                  <th className="px-4 py-2.5 text-right font-semibold">
                    Definido
                  </th>
                  <th className="px-4 py-2.5 font-semibold" />
                </tr>
              </thead>
              <tbody>
                {grupos.map((g) => (
                  <GrupoLineas
                    key={g.grupo}
                    grupo={g.grupo}
                    filas={g.filas}
                    mes={mes as string}
                    acotable={acotable && puede("presupuesto:acotar")}
                    comentarioRequerido={enEjecucion}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Barra de resumen fija + aprobar */}
      {!sinLineas && (
        <div className="fixed inset-x-0 bottom-0 z-10 border-t border-hairline bg-surface/95 px-6 py-3 backdrop-blur md:left-60">
          <div className="flex flex-wrap items-center justify-between gap-3 font-sans text-sm">
            <div className="flex flex-wrap items-center gap-5">
              <Resumen label="Total sugerido" valor={totales.sugerido} />
              <Resumen label="Total definido" valor={totales.definido} />
              <Resumen label="Diferencia" valor={totales.diferencia} conSigno />
            </div>
            {preAprobacion && puede("ciclo:aprobar") && (
              <Button
                variant="green"
                onClick={() => {
                  setAprobarError(null);
                  setAprobarKey(crypto.randomUUID());
                }}
              >
                Aprobar presupuesto
              </Button>
            )}
          </div>
        </div>
      )}

      {aprobarKey && (
        <AprobarDialog
          nLineas={lineas.length}
          totalSugerido={totales.sugerido}
          totalDefinido={totales.definido}
          pendiente={aprobar.isPending}
          error={aprobarError}
          alConfirmar={() => aprobar.mutate()}
          alCerrar={() => {
            setAprobarKey(null);
            setAprobarError(null);
          }}
        />
      )}
    </div>
  );
}

function Resumen({
  label,
  valor,
  conSigno = false,
}: {
  label: string;
  valor: Decimal;
  conSigno?: boolean;
}) {
  const signo = conSigno && valor.greaterThan(0) ? "+" : "";
  return (
    <span className="flex items-baseline gap-1.5">
      <span className="text-ink-faint">{label}</span>
      <span className="tabular font-semibold text-ink">
        {signo}
        {formatCOP(valor)}
      </span>
    </span>
  );
}

function GenerarSugeridoCard({
  mes,
  puedeGenerar,
  alGenerar,
}: {
  mes: string;
  puedeGenerar: boolean;
  alGenerar: () => void;
}) {
  const [pct, setPct] = useState("0");
  const [error, setError] = useState<string | null>(null);

  const generar = useMutation({
    // Entrada humana "15" (%) → fracción exacta "0.15" con Decimal (sin float).
    mutationFn: () =>
      generarSugerido(mes, new Decimal(pct).div(100).toString()),
    onSuccess: alGenerar,
    onError: (e) =>
      setError(e instanceof Error ? e.message : "Error generando el sugerido"),
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!/^\d+(\.\d+)?$/.test(pct.trim())) {
      setError("El % de crecimiento debe ser un número positivo (ej: 15).");
      return;
    }
    generar.mutate();
  }

  if (!puedeGenerar) {
    return (
      <Card>
        <p className="font-sans text-sm text-ink-soft">
          El mes aún no tiene presupuesto sugerido. Pídele a un usuario con
          permiso de abrir ciclo que lo genere.
        </p>
      </Card>
    );
  }

  return (
    <Card className="flex flex-col gap-3">
      <p className="font-sans text-sm text-ink-soft">
        Se calcula con el promedio de los últimos 3 meses + tendencia + % de
        crecimiento.
      </p>
      <form
        onSubmit={onSubmit}
        className="flex flex-wrap items-end gap-3 font-sans text-sm"
      >
        <label className="flex flex-col gap-1">
          <span className="font-medium text-ink">% crecimiento</span>
          <div className="flex items-center gap-1">
            <input
              inputMode="decimal"
              className="tabular w-24 rounded-md border border-hairline bg-surface px-3 py-1.5 text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan"
              value={pct}
              onChange={(e) => setPct(e.target.value)}
            />
            <span className="text-ink-soft">%</span>
          </div>
        </label>
        <Button type="submit" variant="cyan" disabled={generar.isPending}>
          {generar.isPending ? "Generando…" : "Generar presupuesto sugerido"}
        </Button>
      </form>
      {error && <AlertBanner variant="danger">{error}</AlertBanner>}
    </Card>
  );
}

function GrupoLineas({
  grupo,
  filas,
  mes,
  acotable,
  comentarioRequerido,
}: {
  grupo: string;
  filas: { linea: LineaPresupuesto; rubro?: Rubro }[];
  mes: string;
  acotable: boolean;
  comentarioRequerido: boolean;
}) {
  return (
    <>
      <tr className="bg-surface-muted">
        <td
          colSpan={4}
          className="px-4 py-1.5 font-sans text-apoyo font-semibold tracking-wide text-ink-faint uppercase"
        >
          {GRUPO_LABEL[grupo] ?? grupo}
        </td>
      </tr>
      {filas.map(({ linea, rubro }) => (
        <FilaLinea
          key={linea.rubro_id}
          linea={linea}
          nombre={rubro?.nombre ?? linea.rubro_id}
          mes={mes}
          acotable={acotable}
          comentarioRequerido={comentarioRequerido}
        />
      ))}
    </>
  );
}

function FilaLinea({
  linea,
  nombre,
  mes,
  acotable,
  comentarioRequerido,
}: {
  linea: LineaPresupuesto;
  nombre: string;
  mes: string;
  acotable: boolean;
  comentarioRequerido: boolean;
}) {
  const qc = useQueryClient();
  const [expandida, setExpandida] = useState(false);
  const [monto, setMonto] = useState(linea.monto_definido ?? "");
  const [comentario, setComentario] = useState("");
  const [error, setError] = useState<string | null>(null);

  const acotar = useMutation({
    mutationFn: () =>
      acotarLinea(
        mes,
        linea.rubro_id,
        monto.trim(),
        comentario.trim() || undefined,
      ),
    onSuccess: (ln) => {
      setError(null);
      setComentario("");
      // Sincronizar el draft con el monto NORMALIZADO del backend ("1200000" →
      // "1200000.00"); si no, `cambiado` queda true y "Guardar" persiste (QA C2).
      setMonto(ln.monto_definido ?? "");
      // Sin optimistic UI: se refresca la línea con lo que devuelva el backend.
      qc.invalidateQueries({ queryKey: ["presupuesto", mes] });
      qc.invalidateQueries({ queryKey: ["meses"] });
    },
    onError: (e) =>
      setError(e instanceof Error ? e.message : "Error al acotar la línea"),
  });

  function guardar() {
    setError(null);
    if (!/^\d+(\.\d{1,2})?$/.test(monto.trim())) {
      setError("El monto definido debe ser un número positivo (COP).");
      return;
    }
    // FIX-G1: en ejecución el backend exige comentario (422). Se valida aquí antes de
    // llamar y se abre la fila para que el campo sea visible.
    if (comentarioRequerido && !comentario.trim()) {
      setError("En ejecución, describe el motivo del ajuste en el comentario.");
      setExpandida(true);
      return;
    }
    acotar.mutate();
  }

  const cambiado = monto.trim() !== (linea.monto_definido ?? "");

  return (
    <>
      <tr className="border-b border-hairline/60">
        <td className="px-4 py-2 text-ink">
          <button
            type="button"
            onClick={() => setExpandida((v) => !v)}
            aria-expanded={expandida}
            className="flex items-center gap-1.5 text-left hover:text-cyan"
          >
            <span className="text-apoyo text-ink-faint">
              {expandida ? "▾" : "▸"}
            </span>
            {nombre}
          </button>
          {linea.historia_incompleta && (
            <span className="ml-2 rounded-full bg-atencion/10 px-2 py-0.5 font-sans text-apoyo font-medium text-atencion">
              historia incompleta
            </span>
          )}
        </td>
        <td className="tabular px-4 py-2 text-right text-ink-soft">
          {formatCOP(linea.monto_sugerido)}
        </td>
        <td className="px-4 py-2 text-right">
          {acotable ? (
            <input
              aria-label={`Definido ${nombre}`}
              inputMode="decimal"
              placeholder={linea.monto_sugerido}
              className="tabular w-36 rounded-md border border-hairline bg-surface px-2 py-1 text-right text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan"
              value={monto}
              onChange={(e) => setMonto(e.target.value)}
            />
          ) : (
            <span className="tabular text-ink">
              {linea.monto_definido !== null
                ? formatCOP(linea.monto_definido)
                : "—"}
            </span>
          )}
        </td>
        <td className="px-4 py-2 text-right">
          {acotable && cambiado && (
            <Button
              size="sm"
              variant="cyan"
              disabled={acotar.isPending}
              onClick={guardar}
            >
              {acotar.isPending ? "Guardando…" : "Guardar"}
            </Button>
          )}
        </td>
      </tr>
      {expandida && (
        <tr className="border-b border-hairline/60 bg-surface-muted/50">
          <td colSpan={4} className="px-4 py-2">
            <div className="flex flex-wrap items-center gap-5 font-sans text-apoyo text-ink-soft">
              <span>
                Prom. 3m:{" "}
                <span className="tabular font-medium text-ink">
                  {formatCOP(linea.prom_3m)}
                </span>
              </span>
              <span>
                Tendencia:{" "}
                <span className="tabular font-medium text-ink">
                  {formatCOP(linea.tendencia_mes)}
                </span>
              </span>
              <span>
                % crecimiento:{" "}
                <span className="tabular font-medium text-ink">
                  {new Decimal(linea.crec_pct).times(100).toString()}%
                </span>
              </span>
              <span title="Fila informativa: NO entra en la fórmula del sugerido">
                Compromisos programados:{" "}
                <span className="tabular font-medium text-ink">
                  {formatCOP(linea.compromisos_programados)}
                </span>
              </span>
            </div>
            {acotable && (
              <label className="mt-2 flex items-center gap-2 font-sans text-apoyo">
                <span className="text-ink-soft">
                  Comentario{comentarioRequerido ? " *" : ""}
                </span>
                <input
                  aria-label={`Comentario ${nombre}`}
                  maxLength={300}
                  placeholder={
                    comentarioRequerido
                      ? "obligatorio: motivo del ajuste"
                      : "opcional (se guarda al acotar)"
                  }
                  className="w-full max-w-md rounded-md border border-hairline bg-surface px-2 py-1 text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan"
                  value={comentario}
                  onChange={(e) => setComentario(e.target.value)}
                />
              </label>
            )}
          </td>
        </tr>
      )}
      {error && (
        <tr>
          <td colSpan={4} className="px-4 pb-2">
            <AlertBanner variant="danger">{error}</AlertBanner>
          </td>
        </tr>
      )}
    </>
  );
}

function AprobarDialog({
  nLineas,
  totalSugerido,
  totalDefinido,
  pendiente,
  error,
  alConfirmar,
  alCerrar,
}: {
  nLineas: number;
  totalSugerido: Decimal;
  totalDefinido: Decimal;
  pendiente: boolean;
  error: string | null;
  alConfirmar: () => void;
  alCerrar: () => void;
}) {
  return (
    <div className="fixed inset-0 z-20 flex items-center justify-center bg-black/40 p-4">
      <dialog
        open
        aria-label="Aprobar presupuesto"
        className="static w-full max-w-md rounded-lg border border-hairline bg-surface p-6 text-inherit shadow-lg"
      >
        <h3 className="mb-1 font-display text-lg font-semibold text-ink">
          Aprobar presupuesto
        </h3>
        <p className="mb-4 font-sans text-apoyo text-ink-faint">
          El mes pasa a ejecución y las líneas sin monto definido toman el
          sugerido. Esta acción queda auditada.
        </p>
        <dl className="mb-4 flex flex-col gap-1.5 font-sans text-sm">
          <div className="flex justify-between">
            <dt className="text-ink-soft">Líneas de presupuesto</dt>
            <dd className="font-medium text-ink">{nLineas}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-ink-soft">Total sugerido</dt>
            <dd className="tabular font-medium text-ink">
              {formatCOP(totalSugerido)}
            </dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-ink-soft">Total definido</dt>
            <dd className="tabular font-medium text-ink">
              {formatCOP(totalDefinido)}
            </dd>
          </div>
        </dl>
        {error && (
          <div className="mb-3">
            <AlertBanner variant="warn">{error}</AlertBanner>
          </div>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={alCerrar}>
            Cancelar
          </Button>
          <Button
            type="button"
            variant="green"
            disabled={pendiente}
            onClick={alConfirmar}
          >
            {pendiente ? "Aprobando…" : "Aprobar"}
          </Button>
        </div>
      </dialog>
    </div>
  );
}
