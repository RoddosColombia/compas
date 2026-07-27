// frontend/src/pages/DashboardsPage.tsx
//
// Dashboards — panel operativo del cockpit. Muestra las series del motor (C7):
// cobranza (recaudo de crédito), cuotas iniciales, ingreso bruto, cartera activa,
// COLOCACIÓN mensual y cartera por AÑADA (cohorte, DASH-01), + la mora por TRAMO
// (aging) DERIVADA del LoanTape real de SISMO-V3 (no inventada). Montos con formatCOP
// (regla 1); .toNumber() SOLO para el ancho de las barras (presentación), nunca cálculo.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { useAuth } from "@/auth/AuthContext";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { Cargando } from "@/components/ui/cargando";
import { ChartCard } from "@/components/ui/chart-card";
import { ErrorEstado } from "@/components/ui/error-estado";
import { EstadoVacio } from "@/components/ui/estado-vacio";
import { KpiTileV2 } from "@/components/ui/kpi-tile";
import { type Aging, cargarLoantape, obtenerAging } from "@/lib/loantape";
import {
  formatCOPCompact,
  formatCOPEntero,
  formatMesCorto,
  parseMonto,
} from "@/lib/money";
import {
  type MesOperacion,
  type MesProyeccion,
  obtenerOperacion,
  obtenerProyeccion,
} from "@/lib/proyeccion";

const HORIZONTES = [12, 24, 36, 60];

/** Conclusión de la cobranza escrita desde los datos (§4). */
function conclusionCobranza(meses: MesProyeccion[]): string {
  const n = meses.length;
  const primera = parseMonto(meses[0].recaudo_credito);
  const ultima = parseMonto(meses[n - 1].recaudo_credito);
  if (primera.lessThanOrEqualTo(0)) {
    return `La cobranza proyectada llega a ${formatCOPCompact(ultima)}/mes en ${n} meses`;
  }
  // QA F1.1 (arrastre): el multiplicador engañaba con el mes 1 parcial y usaba punto
  // decimal ("×104.6"). Se dice "pasa de X a Y" — honesto y en formato es-CO (coma).
  const ratio = ultima.div(primera);
  if (ratio.greaterThan("1.1")) {
    return `La cobranza proyectada pasa de ${formatCOPCompact(primera)} a ${formatCOPCompact(ultima)}/mes en ${n} meses`;
  }
  return `La cobranza proyectada se mantiene estable (~${formatCOPCompact(ultima)}/mes)`;
}

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
  const op = useQuery({
    queryKey: ["operacion", "base", horizonte],
    queryFn: () =>
      obtenerOperacion({ escenario: "base", horizonteMeses: horizonte }),
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
        <>
          <Cargando variante="kpis" />
          <Cargando variante="card" className="h-80" />
        </>
      )}
      {q.isError && (
        <ErrorEstado
          mensaje="No se pudo cargar la operación: verifica que haya modelos de moto y parámetros configurados en Supuestos."
          onReintentar={() => void q.refetch()}
        />
      )}

      {q.data && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <KpiTileV2
              label="Cobranza proyectada"
              valor={suma(q.data.meses, "recaudo_credito")}
              contexto={`en ${q.data.meses.length} meses`}
            />
            <KpiTileV2
              label="Cuotas iniciales"
              valor={suma(q.data.meses, "cuotas_iniciales")}
              contexto="suma del horizonte"
            />
            <KpiTileV2
              label="Ingreso bruto proyectado"
              valor={suma(q.data.meses, "ingreso_bruto")}
              contexto="cobranza + cuotas iniciales"
            />
            <KpiTileV2
              label="Cartera activa al cierre"
              valor="0"
              valorTexto={String(
                q.data.meses[q.data.meses.length - 1]?.cartera ?? 0,
              )}
              contexto="motos pagando al final del horizonte"
            />
          </div>

          <ChartCard
            conclusion={conclusionCobranza(q.data.meses)}
            subtitulo={`recaudo de crédito (cuota a cuota) por mes · escenario base · ${q.data.meses.length} meses`}
            pie="Fuente: motor de proyección (Vía 1, cuota a cuota + cartera previa)"
            protagonista
            lienzo="auto"
          >
            <BarrasCobranza meses={q.data.meses} />
          </ChartCard>

          {op.data && op.data.meses.length > 0 && (
            <>
              <ChartCard
                conclusion={`La colocación pasa de ${op.data.meses[0].colocacion} a ${op.data.meses[op.data.meses.length - 1].colocacion} motos/mes`}
                subtitulo={`motos colocadas por mes (nuevas ventas a crédito) · ${op.data.meses.length} meses`}
                pie="Fuente: motor de proyección (colocación compuesta)"
                lienzo="auto"
              >
                <BarrasMotos meses={op.data.meses} />
              </ChartCard>

              <CarteraPorAnada meses={op.data.meses} />
            </>
          )}

          <MoraPorTramo />
        </>
      )}
    </div>
  );
}

// Mora por TRAMO (aging) derivada del LoanTape real de SISMO-V3. Incluye la carga
// (upload CSV/Excel) para quien tenga cargas:gestionar.
function MoraPorTramo() {
  const { puede } = useAuth();
  const qc = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [mensaje, setMensaje] = useState<string | null>(null);

  const q = useQuery({ queryKey: ["aging"], queryFn: obtenerAging });
  const subir = useMutation({
    mutationFn: cargarLoantape,
    onSuccess: (r) => {
      setMensaje(`LoanTape cargado: ${r.cargados} créditos.`);
      qc.invalidateQueries({ queryKey: ["aging"] });
    },
    onError: (e) =>
      setMensaje(e instanceof Error ? e.message : "Error cargando el LoanTape"),
  });

  function onArchivo(files: FileList | null) {
    setMensaje(null);
    const f = files?.[0];
    if (f) subir.mutate(f);
    if (inputRef.current) inputRef.current.value = "";
  }

  const gestor = puede("cargas:gestionar");
  const cargar = gestor && (
    <div className="flex items-center gap-2">
      <input
        ref={inputRef}
        type="file"
        accept=".csv,.xlsx"
        className="hidden"
        data-testid="input-loantape"
        onChange={(e) => onArchivo(e.target.files)}
      />
      <Button
        variant="cyan"
        onClick={() => inputRef.current?.click()}
        disabled={subir.isPending}
      >
        {subir.isPending ? "Cargando…" : "Cargar LoanTape"}
      </Button>
    </div>
  );

  return (
    <Card>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <CardTitle>Mora por tramo</CardTitle>
          <p className="mt-0.5 font-sans text-apoyo text-ink-faint">
            {q.data?.fecha_corte
              ? `aging del LoanTape de SISMO-V3 · corte ${q.data.fecha_corte}`
              : "cartera morosa por días de atraso (LoanTape de SISMO-V3)"}
          </p>
        </div>
        {cargar}
      </div>
      {mensaje && (
        <p className="mb-3 font-sans text-sm text-ink-soft">{mensaje}</p>
      )}
      {q.isLoading && (
        <p className="font-sans text-sm text-ink-soft">Cargando aging…</p>
      )}
      {q.data && !q.data.fecha_corte && (
        <EstadoVacio
          mensaje="Aún no hay LoanTape cargado: la mora por tramo se construye del archivo semanal de SISMO-V3."
          quien={
            gestor
              ? "súbelo con «Cargar LoanTape», aquí arriba"
              : "financiero o admin, con «Cargar LoanTape»"
          }
        />
      )}
      {q.data?.fecha_corte && <TramosAging aging={q.data} />}
    </Card>
  );
}

function TramosAging({ aging }: { aging: Aging }) {
  const montos = aging.tramos.map((t) =>
    parseMonto(t.saldo_en_mora).toNumber(),
  );
  const max = Math.max(...montos, 1);
  const TONO: Record<string, string> = {
    al_dia: "bg-positivo",
    "1_30": "bg-cyan",
    "31_60": "bg-atencion",
    "61_90": "bg-atencion",
    "90_mas": "bg-critico",
  };
  return (
    <div className="flex flex-col gap-1.5">
      {aging.tramos.map((t, i) => {
        const pct = Math.max(2, (montos[i] / max) * 100);
        return (
          <div key={t.tramo} className="flex items-center gap-3">
            <span className="w-24 shrink-0 font-sans text-apoyo text-ink-soft">
              {t.etiqueta}
            </span>
            <div className="h-4 flex-1 overflow-hidden rounded bg-surface-muted">
              <div
                className={`h-full rounded ${TONO[t.tramo] ?? "bg-cyan"}`}
                style={{ width: `${pct}%` }}
              />
            </div>
            <span className="tabular w-10 shrink-0 text-right font-sans text-apoyo text-ink-soft">
              {t.n_creditos}
            </span>
            <span className="tabular w-32 shrink-0 text-right font-sans text-apoyo text-ink">
              {formatCOPEntero(t.saldo_en_mora)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// Barras de colocación (conteo de motos). Ancho = geometría de presentación.
function BarrasMotos({ meses }: { meses: MesOperacion[] }) {
  const max = Math.max(...meses.map((m) => m.colocacion), 1);
  return (
    <div className="flex flex-col gap-1.5">
      {meses.map((m) => {
        const pct = Math.max(2, (m.colocacion / max) * 100);
        return (
          <div key={m.mes} className="flex items-center gap-3">
            <span className="tabular w-16 shrink-0 font-sans text-apoyo text-ink-soft">
              {m.mes}
            </span>
            <div className="h-4 flex-1 overflow-hidden rounded bg-surface-muted">
              <div
                className="h-full rounded bg-positivo"
                style={{ width: `${pct}%` }}
              />
            </div>
            <span className="tabular w-12 shrink-0 text-right font-sans text-apoyo text-ink">
              {m.colocacion}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// Cartera activa del ÚLTIMO mes desglosada por añada (cohorte de colocación).
function CarteraPorAnada({ meses }: { meses: MesOperacion[] }) {
  const ultimo = meses[meses.length - 1];
  const max = Math.max(...ultimo.por_anada.map((a) => a.activos), 1);
  return (
    <ChartCard
      conclusion={`${ultimo.cartera} motos pagando en ${formatMesCorto(ultimo.mes)}, por cohorte de colocación`}
      subtitulo="«previa» = los 111 créditos preexistentes"
      pie="Las cohortes aún no terminan su plazo: el desglose igualará a la colocación hasta ~dic-2027. Fuente: motor de proyección."
      lienzo="auto"
    >
      <div className="flex flex-col gap-1.5">
        {ultimo.por_anada.map((a) => {
          const pct = Math.max(2, (a.activos / max) * 100);
          return (
            <div key={a.anada} className="flex items-center gap-3">
              <span className="tabular w-20 shrink-0 font-sans text-apoyo text-ink-soft">
                {a.anada}
              </span>
              <div className="h-4 flex-1 overflow-hidden rounded bg-surface-muted">
                <div
                  className={`h-full rounded ${
                    a.anada === "previa" ? "bg-atencion" : "bg-cyan"
                  }`}
                  style={{ width: `${pct}%` }}
                />
              </div>
              <span className="tabular w-12 shrink-0 text-right font-sans text-apoyo text-ink">
                {a.activos}
              </span>
            </div>
          );
        })}
      </div>
    </ChartCard>
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
            <span className="tabular w-16 shrink-0 font-sans text-apoyo text-ink-soft">
              {m.mes}
            </span>
            <div className="h-4 flex-1 overflow-hidden rounded bg-surface-muted">
              <div
                className="h-full rounded bg-cyan"
                style={{ width: `${pct}%` }}
              />
            </div>
            <span className="tabular w-32 shrink-0 text-right font-sans text-apoyo text-ink">
              {formatCOPEntero(m.recaudo_credito)}
            </span>
          </div>
        );
      })}
    </div>
  );
}
