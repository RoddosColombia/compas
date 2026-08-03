// frontend/src/pages/CabinaMesPage.tsx
//
// C2 "Cabina del mes" (/mes): el ciclo completo vive en una sola vista — de
// abrir mes a cerrar mes sin peregrinar por 5 rutas. INTEGRA (no duplica):
// CicloStepper y ReporteCajaCard son los componentes compartidos, el control
// priorizado es QueExigeAtencion, y el presupuesto enlaza a PresupuestoMesPage
// (C1). El cierre usa el contrato real del backend (dos pasos: conciliación
// compute-only + confirmar con Idempotency-Key, patrón C1). Montos string +
// money.ts (regla 1); botones por capacidad (regla 9).

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Decimal from "decimal.js-light";
import { useState } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "@/auth/AuthContext";
import { ReporteCajaCard } from "@/components/caja/ReporteCajaCard";
import { CicloStepper } from "@/components/ciclo/CicloStepper";
import { EstadoBadge } from "@/components/ciclo/EstadoBadge";
import { QueExigeAtencion } from "@/components/control/QueExigeAtencion";
import { PageHeader } from "@/components/layout/PageHeader";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { Cargando } from "@/components/ui/cargando";
import { ErrorEstado } from "@/components/ui/error-estado";
import { EstadoVacio } from "@/components/ui/estado-vacio";
import { KpiTileV2 } from "@/components/ui/kpi-tile";
import {
  type ConciliacionCierre,
  cierreConciliacion,
  confirmarCierre,
} from "@/lib/cierre";
import { vistaControl } from "@/lib/control";
import {
  type Mes,
  listarMeses,
  mesEnEjecucion,
  mesPendiente,
  mesSiguiente,
} from "@/lib/meses";
import { formatCOP, formatCOPCompact, parseMonto } from "@/lib/money";
import { listarPresupuesto } from "@/lib/presupuesto";

export default function CabinaMesPage() {
  const meses = useQuery({ queryKey: ["meses"], queryFn: listarMeses });
  const items = meses.data?.items ?? [];

  // El aviso de cierre vive AQUÍ (no en TarjetaCierre): tras cerrar, la
  // invalidación re-renderiza la tarjeta a su rama "cerrado" y un estado local
  // se esfumaría con ella (hallazgo QA C2).
  const [avisoCierre, setAvisoCierre] = useState<string | null>(null);

  // Mes de la cabina: el que está OPERANDO; si no hay, el pendiente de aprobar
  // más reciente; si tampoco, el más reciente del historial.
  const activo = mesEnEjecucion(items);
  const pendiente7 = mesPendiente(items);
  const mesCab =
    activo ??
    items.find((m) => m.mes.slice(0, 7) === pendiente7) ??
    [...items].sort((a, b) => b.mes.localeCompare(a.mes))[0];
  const mes7 = mesCab?.mes.slice(0, 7) ?? null;

  const presupuesto = useQuery({
    queryKey: ["presupuesto", mes7],
    queryFn: () => listarPresupuesto(mes7 as string),
    enabled: mes7 !== null,
  });
  const conControl =
    mesCab?.estado === "en_ejecucion" || mesCab?.estado === "cerrado";
  const control = useQuery({
    queryKey: ["mes", mes7, "control"],
    queryFn: () => vistaControl(mes7 as string),
    enabled: mes7 !== null && conControl,
  });

  if (meses.isLoading) {
    return <Cargando variante="card" />;
  }
  if (meses.isError) {
    return (
      <ErrorEstado
        mensaje="No se pudo listar los meses del ciclo."
        onReintentar={() => void meses.refetch()}
      />
    );
  }

  if (!mesCab) {
    return (
      <div className="flex flex-col gap-4">
        <PageHeader
          titulo="Mes en curso"
          descripcion="La cabina del ciclo mensual."
        />
        <EstadoVacio
          mensaje="Aún no hay meses abiertos: el ciclo arranca abriendo el primero."
          accion={{ to: "/meses", label: "Abrir el primer mes" }}
          quien="financiero, directivo o admin"
        />
      </div>
    );
  }

  const lineas = presupuesto.data?.lineas ?? [];
  const sinLineas = lineas.length === 0;

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        titulo={`Mes en curso · ${mes7}`}
        descripcion="El ciclo completo del mes en una sola vista: presupuesto, caja, desvíos y cierre."
      />

      {avisoCierre && <AlertBanner variant="ok">{avisoCierre}</AlertBanner>}

      {/* 1 · Mes y ciclo */}
      <Card className="flex flex-col gap-3">
        <CardTitle>Mes y ciclo</CardTitle>
        <CicloStepper estado={mesCab.estado} sinLineas={sinLineas} />
        <MesesRecientes items={items} mesCabina={mesCab.mes} />
      </Card>

      {/* 2 · Presupuesto */}
      <TarjetaPresupuesto
        mes={mesCab}
        lineas={lineas.length}
        totalDefinido={totalDefinido(presupuesto.data?.lineas)}
        control={control.data ?? null}
      />

      {/* 3 · Caja del día */}
      <Card className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <CardTitle>Caja del día</CardTitle>
          <Link
            to="/caja"
            className="font-sans text-apoyo font-medium text-cyan hover:underline"
          >
            Ver en Caja →
          </Link>
        </div>
        {activo ? (
          <ReporteCajaCard mes={activo} />
        ) : (
          <EstadoVacio
            mensaje="El reporte de caja se habilita cuando el mes esté en ejecución."
            accion={{
              to: `/meses/${mes7}/presupuesto`,
              label: "Aprobar el presupuesto",
            }}
            quien="admin"
          />
        )}
      </Card>

      {/* 4 · Qué exige atención */}
      {activo && control.data && (
        <QueExigeAtencion
          grupos={control.data.grupos}
          mes={mes7 as string}
          max={5}
        />
      )}

      {/* 5 · Cierre */}
      <TarjetaCierre mes={mesCab} meses={items} onCerrado={setAvisoCierre} />
    </div>
  );
}

/** Total definido con respaldo en el sugerido (D2, mismo criterio que C1). */
function totalDefinido(
  lineas:
    | { monto_definido: string | null; monto_sugerido: string }[]
    | undefined,
): Decimal | null {
  if (!lineas || lineas.length === 0) return null;
  let total = new Decimal(0);
  for (const ln of lineas) {
    total = total.plus(parseMonto(ln.monto_definido ?? ln.monto_sugerido));
  }
  return total;
}

function MesesRecientes({
  items,
  mesCabina,
}: {
  items: Mes[];
  mesCabina: string;
}) {
  const recientes = [...items]
    .sort((a, b) => b.mes.localeCompare(a.mes))
    .slice(0, 6);
  if (recientes.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-2 border-t border-hairline pt-3">
      {recientes.map((m) => (
        <Link
          key={m.id}
          to={`/meses/${m.mes.slice(0, 7)}/presupuesto`}
          className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1 font-sans text-apoyo transition-colors hover:bg-surface-muted ${
            m.mes === mesCabina ? "border-cyan" : "border-hairline"
          }`}
        >
          <span className="font-medium text-ink">{m.mes.slice(0, 7)}</span>
          <EstadoBadge estado={m.estado} />
        </Link>
      ))}
      <Link
        to="/meses"
        className="font-sans text-apoyo font-medium text-cyan hover:underline"
      >
        Historial completo y abrir mes →
      </Link>
    </div>
  );
}

function TarjetaPresupuesto({
  mes,
  lineas,
  totalDefinido,
  control,
}: {
  mes: Mes;
  lineas: number;
  totalDefinido: Decimal | null;
  control: { total: { definido: string; ejecutado: string } } | null;
}) {
  const editable = mes.estado === "sugerido" || mes.estado === "propuesto";
  const mes7 = mes.mes.slice(0, 7);

  return (
    <Card className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <CardTitle>Presupuesto</CardTitle>
        <Link
          to={`/meses/${mes7}/presupuesto`}
          className="font-sans text-apoyo font-medium text-cyan hover:underline"
        >
          {editable
            ? lineas === 0
              ? "Generar sugerido →"
              : "Acotar y aprobar →"
            : "Ver el presupuesto →"}
        </Link>
      </div>

      {editable && lineas === 0 && (
        <p className="font-sans text-sm text-ink-soft">
          El mes aún no tiene presupuesto sugerido.
        </p>
      )}

      {lineas > 0 && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <KpiTileV2
            label="Líneas de presupuesto"
            valor="0"
            valorTexto={String(lineas)}
            contexto="rubros con línea vigente"
          />
          {totalDefinido && (
            <KpiTileV2
              label="Total definido"
              valor={totalDefinido}
              contexto="lo aprobado (o por aprobar) del mes"
            />
          )}
          <div className="flex items-center gap-2 font-sans text-cuerpo">
            <span className="text-ink-faint">Estado</span>
            <EstadoBadge estado={mes.estado} />
          </div>
        </div>
      )}

      {/* Aprobado: definido vs ejecutado (mini barra) */}
      {control && <BarraEjecucion total={control.total} />}
    </Card>
  );
}

function BarraEjecucion({
  total,
}: {
  total: { definido: string; ejecutado: string };
}) {
  const definido = parseMonto(total.definido);
  const ejecutado = parseMonto(total.ejecutado);
  if (!definido.greaterThan(0)) return null;
  const pct = ejecutado.div(definido).times(100);
  const ancho = Math.min(100, Number(pct.toDecimalPlaces(1).toString()));
  const pasado = pct.greaterThan(100);
  return (
    <div className="flex flex-col gap-1">
      <div className="flex justify-between font-sans text-apoyo text-ink-soft">
        <span>
          Ejecutado{" "}
          <span
            className="tabular font-medium text-ink"
            title={formatCOP(ejecutado)}
          >
            {formatCOPCompact(ejecutado)}
          </span>
        </span>
        <span className={pasado ? "font-semibold text-critico" : undefined}>
          de{" "}
          <span
            className="tabular font-medium text-ink"
            title={formatCOP(definido)}
          >
            {formatCOPCompact(definido)}
          </span>{" "}
          ({pct.toDecimalPlaces(0).toString()} %
          {pasado ? " ✗ sobre lo aprobado" : ""})
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-surface-muted">
        <div
          className={`h-full rounded-full ${pasado ? "bg-critico" : "bg-cyan"}`}
          style={{ width: `${ancho}%` }}
        />
      </div>
    </div>
  );
}

// ── 5 · Cierre — contrato real del backend (dos pasos) ──────────────────────

function TarjetaCierre({
  mes,
  meses,
  onCerrado,
}: {
  mes: Mes;
  meses: Mes[];
  /** el aviso de éxito lo conserva el padre (sobrevive el re-render a "cerrado") */
  onCerrado: (msg: string) => void;
}) {
  const { puede } = useAuth();
  const qc = useQueryClient();
  const mes7 = mes.mes.slice(0, 7);

  const [conc, setConc] = useState<ConciliacionCierre | null>(null);
  const [concError, setConcError] = useState<string | null>(null);
  const verificar = useMutation({
    mutationFn: () => cierreConciliacion(mes7),
    onSuccess: (r) => {
      setConcError(null);
      setConc(r);
    },
    onError: (e) =>
      setConcError(e instanceof Error ? e.message : "Error al conciliar"),
  });

  // Cierre con Idempotency-Key generada UNA vez al abrir el diálogo (patrón C1).
  const [cerrarKey, setCerrarKey] = useState<string | null>(null);
  const [cerrarError, setCerrarError] = useState<string | null>(null);
  // CR-WAVA: dinero en tránsito (Wava) declarado al cerrar (default 0).
  const [transito, setTransito] = useState("0");
  const cerrar = useMutation({
    mutationFn: () =>
      confirmarCierre(mes7, cerrarKey as string, transito.trim()),
    onSuccess: (r) => {
      setCerrarKey(null);
      onCerrado(
        `Mes ${r.mes} cerrado. Saldo inicial del siguiente: ${formatCOP(r.saldo_inicial_siguiente)}.`,
      );
      qc.invalidateQueries({ queryKey: ["meses"] });
    },
    onError: (e) =>
      setCerrarError(e instanceof Error ? e.message : "Error al cerrar"),
  });

  if (mes.estado === "cerrado") {
    return (
      <Card className="flex flex-col gap-2">
        <CardTitle>Cierre</CardTitle>
        <p className="font-sans text-sm text-ink-soft">
          El mes {mes7} está cerrado: el histórico es inmutable (regla 4).
        </p>
      </Card>
    );
  }

  if (mes.estado !== "en_ejecucion") {
    return (
      <Card className="flex flex-col gap-2">
        <CardTitle>Cierre</CardTitle>
        <EstadoVacio
          mensaje="El cierre se habilita cuando el mes esté en ejecución."
          accion={{
            to: `/meses/${mes7}/presupuesto`,
            label: "Ir al presupuesto del mes",
          }}
        />
      </Card>
    );
  }

  const siguienteAbierto = meses.some((m) => m.mes === mesSiguiente(mes.mes));
  const concOk = conc?.dentro_de_umbral ?? false;

  return (
    <Card className="flex flex-col gap-3">
      <CardTitle>Cierre</CardTitle>

      <ul className="flex flex-col gap-1.5 font-sans text-sm">
        <li className="flex items-start gap-2">
          <Precondicion ok={siguienteAbierto} />
          <span className="text-ink">
            Mes siguiente abierto ({mesSiguiente(mes.mes).slice(0, 7)}) — el
            ajuste de conciliación se imputa al mes que abre.{" "}
            {!siguienteAbierto && (
              <Link
                to="/meses"
                className="font-medium text-cyan hover:underline"
              >
                Abrir mes →
              </Link>
            )}
          </span>
        </li>
        <li className="flex items-start gap-2">
          <Precondicion ok={conc === null ? null : concOk} />
          <span className="text-ink">
            Conciliación dentro del umbral y sin bancos sin dato.
            {conc !== null && (
              <span className="text-ink-soft">
                {" "}
                Diferencia {formatCOP(conc.diferencia)} (umbral{" "}
                {formatCOP(conc.umbral)})
                {conc.sin_dato.length > 0 &&
                  ` · sin dato: ${conc.sin_dato.join(", ")}`}
              </span>
            )}
          </span>
        </li>
      </ul>

      {concError && <AlertBanner variant="danger">{concError}</AlertBanner>}

      <div className="flex flex-wrap gap-2">
        {puede("ciclo:cierre_operativo") && (
          <Button
            variant="outline"
            size="sm"
            disabled={verificar.isPending}
            onClick={() => verificar.mutate()}
          >
            {verificar.isPending ? "Verificando…" : "Verificar conciliación"}
          </Button>
        )}
        {puede("ciclo:confirmar_cierre") && (
          <Button
            variant="cyan"
            size="sm"
            disabled={!siguienteAbierto}
            onClick={() => {
              setCerrarError(null);
              setTransito("0");
              setCerrarKey(crypto.randomUUID());
            }}
          >
            Cerrar mes
          </Button>
        )}
      </div>

      {cerrarKey && (
        <CerrarDialog
          mes={mes7}
          conc={conc}
          transito={transito}
          onTransito={setTransito}
          pendiente={cerrar.isPending}
          error={cerrarError}
          alConfirmar={() => {
            if (!/^\d+(\.\d{1,2})?$/.test(transito.trim())) {
              setCerrarError(
                "El dinero en tránsito debe ser un número positivo (COP).",
              );
              return;
            }
            cerrar.mutate();
          }}
          alCerrar={() => {
            setCerrarKey(null);
            setCerrarError(null);
          }}
        />
      )}
    </Card>
  );
}

function Precondicion({ ok }: { ok: boolean | null }) {
  if (ok === null)
    return <span className="mt-0.5 shrink-0 text-ink-faint">•</span>;
  return ok ? (
    <span className="mt-0.5 shrink-0 font-semibold text-positivo">✓</span>
  ) : (
    <span className="mt-0.5 shrink-0 font-semibold text-critico">✗</span>
  );
}

function CerrarDialog({
  mes,
  conc,
  transito,
  onTransito,
  pendiente,
  error,
  alConfirmar,
  alCerrar,
}: {
  mes: string;
  conc: ConciliacionCierre | null;
  transito: string;
  onTransito: (v: string) => void;
  pendiente: boolean;
  error: string | null;
  alConfirmar: () => void;
  alCerrar: () => void;
}) {
  // CR-WAVA: total = bancos + tránsito (nunca sumado dentro de un banco). Preview con
  // Decimal (regla 1); si el input aún no es válido, el total muestra solo bancos.
  const transitoOk = /^\d+(\.\d{1,2})?$/.test(transito.trim());
  const bancos = conc !== null ? parseMonto(conc.consolidado_reportado) : null;
  const total =
    bancos !== null && transitoOk
      ? bancos.plus(parseMonto(transito.trim()))
      : bancos;
  return (
    <div className="fixed inset-0 z-20 flex items-center justify-center bg-black/40 p-4">
      <dialog
        open
        aria-label="Cerrar mes"
        className="static w-full max-w-md rounded-lg border border-hairline bg-surface p-6 text-inherit shadow-lg"
      >
        <h3 className="mb-1 font-display text-lg font-semibold text-ink">
          Cerrar el mes {mes}
        </h3>
        <p className="mb-4 font-sans text-apoyo text-ink-faint">
          El mes queda inmutable y el saldo inicial del siguiente se ancla al
          consolidado de bancos. El backend valida la conciliación antes de
          cerrar. Esta acción queda auditada.
        </p>
        {conc !== null && (
          <dl className="mb-4 flex flex-col gap-1.5 font-sans text-sm">
            <div className="flex justify-between">
              <dt className="text-ink-soft">Consolidado bancos</dt>
              <dd className="tabular font-medium text-ink">
                {formatCOP(conc.consolidado_reportado)}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-ink-soft">Caja del libro</dt>
              <dd className="tabular font-medium text-ink">
                {formatCOP(conc.caja_libro)}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-ink-soft">Diferencia</dt>
              <dd className="tabular font-medium text-ink">
                {formatCOP(conc.diferencia)}
              </dd>
            </div>
          </dl>
        )}

        {/* CR-WAVA: dinero en tránsito (Wava) + caja en tres líneas nombradas */}
        <label className="mb-3 flex flex-col gap-1 font-sans text-sm">
          <span className="text-ink-soft">Dinero en tránsito (Wava)</span>
          <input
            aria-label="Dinero en tránsito (Wava)"
            inputMode="decimal"
            placeholder="0"
            className="tabular w-full rounded-md border border-hairline bg-surface px-3 py-1.5 text-right text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan"
            value={transito}
            onChange={(e) => onTransito(e.target.value)}
          />
        </label>
        {bancos !== null && (
          <dl className="mb-4 flex flex-col gap-1.5 border-t border-hairline pt-3 font-sans text-sm">
            <div className="flex justify-between">
              <dt className="text-ink-soft">Consolidado bancos</dt>
              <dd className="tabular font-medium text-ink">
                {formatCOP(bancos)}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-ink-soft">En tránsito</dt>
              <dd className="tabular font-medium text-ink">
                {transitoOk ? formatCOP(parseMonto(transito.trim())) : "—"}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="font-semibold text-ink">Total caja</dt>
              <dd className="tabular font-semibold text-ink">
                {total !== null ? formatCOP(total) : "—"}
              </dd>
            </div>
          </dl>
        )}
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
            {pendiente ? "Cerrando…" : "Cerrar mes"}
          </Button>
        </div>
      </dialog>
    </div>
  );
}
