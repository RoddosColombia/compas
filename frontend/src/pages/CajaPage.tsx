// frontend/src/pages/CajaPage.tsx
//
// C4 ajuste diario de caja (CR-S6): reportar el saldo disponible por banco sobre el
// mes EN EJECUCIÓN y ver al instante si la información cuadra (conciliación D4). Es la
// segunda entrada diaria del norte (la otra es la carga de movimientos). Montos con
// formatCOP (regla 1); el cálculo y el "¿cuadra?" vienen del backend. El formulario
// solo aparece con caja:reportar (regla 9); la autoridad real la impone el backend.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "@/auth/AuthContext";
import { PageHeader } from "@/components/layout/PageHeader";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { KpiTile } from "@/components/ui/kpi-tile";
import {
  type Conciliacion,
  type ReporteSaldosResultado,
  reportarSaldos,
} from "@/lib/caja";
import { BANCOS, listarMeses } from "@/lib/meses";
import { formatCOP, formatFecha } from "@/lib/money";

const BANCO_LABEL: Record<string, string> = {
  bancolombia: "Bancolombia",
  bbva: "BBVA",
  global66: "Global66",
};

function hoyLocal(): string {
  const d = new Date();
  const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}

export default function CajaPage() {
  const { puede } = useAuth();
  const reporta = puede("caja:reportar");
  const qc = useQueryClient();
  const [mensaje, setMensaje] = useState<string | null>(null);
  const [conciliacion, setConciliacion] = useState<Conciliacion | null>(null);

  const meses = useQuery({ queryKey: ["meses"], queryFn: listarMeses });

  // El reporte diario es del mes OPERANDO (D3). Debe haber uno solo en ejecución.
  const mesActivo = useMemo(
    () => (meses.data?.items ?? []).find((m) => m.estado === "en_ejecucion"),
    [meses.data],
  );

  // Mes más reciente pendiente de aprobar (para el vacío accionable, C1).
  const mesPendiente = useMemo(() => {
    const items = meses.data?.items ?? [];
    return (
      items
        .filter((m) => m.estado === "sugerido" || m.estado === "propuesto")
        .map((m) => m.mes.slice(0, 7))
        .sort()
        .reverse()[0] ?? null
    );
  }, [meses.data]);
  const mesCorto = mesActivo?.mes.slice(0, 7) ?? null;

  const reportar = useMutation({
    mutationFn: (
      saldos: { banco: string; saldo: string; fecha_reporte: string }[],
    ) => reportarSaldos(mesCorto as string, saldos),
    onSuccess: (r: ReporteSaldosResultado) => {
      setMensaje(null);
      setConciliacion(r.conciliacion);
      qc.invalidateQueries({ queryKey: ["meses"] });
    },
    onError: (e: unknown) =>
      setMensaje(e instanceof Error ? e.message : "Error"),
  });

  const saldoPorBanco = new Map(
    (mesActivo?.saldos_banco ?? []).map((s) => [s.banco, s]),
  );

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        titulo="Caja"
        descripcion={`Reporta el saldo de cada banco para que la información siempre cuadre${
          mesCorto ? ` · mes ${mesCorto}` : ""
        }`}
      />

      {meses.isLoading && (
        <p className="font-sans text-sm text-ink-soft">Cargando…</p>
      )}
      {meses.data && !mesActivo && (
        <p className="font-sans text-sm text-ink-soft">
          No hay ningún mes en ejecución.{" "}
          {mesPendiente ? (
            <Link
              to={`/meses/${mesPendiente}/presupuesto`}
              className="font-medium text-cyan hover:underline"
            >
              Aprueba el presupuesto de {mesPendiente} →
            </Link>
          ) : (
            <Link to="/meses" className="font-medium text-cyan hover:underline">
              Abre un mes para empezar el ciclo →
            </Link>
          )}
        </p>
      )}

      {mensaje && <AlertBanner variant="danger">{mensaje}</AlertBanner>}

      {mesActivo && (
        <Card className="overflow-hidden p-0">
          <div className="overflow-x-auto">
            <table className="w-full font-sans text-sm">
              <thead>
                <tr className="border-b border-hairline text-left text-ink-faint">
                  <th className="px-4 py-2.5 font-semibold">Banco</th>
                  <th className="px-4 py-2.5 text-right font-semibold">
                    Saldo reportado
                  </th>
                  <th className="px-4 py-2.5 font-semibold">
                    Fecha del reporte
                  </th>
                </tr>
              </thead>
              <tbody>
                {BANCOS.map((b) => {
                  const sb = saldoPorBanco.get(b);
                  return (
                    <tr
                      key={b}
                      className="border-b border-hairline/60 last:border-0"
                    >
                      <td className="px-4 py-2 text-ink">
                        {BANCO_LABEL[b] ?? b}
                      </td>
                      <td className="tabular px-4 py-2 text-right text-ink-soft">
                        {sb ? formatCOP(sb.saldo) : "—"}
                      </td>
                      <td className="px-4 py-2 text-ink-soft">
                        {sb ? formatFecha(sb.fecha_reporte) : "sin reporte"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {mesActivo && reporta && (
        <FormReporte
          reportando={reportar.isPending}
          onReportar={(i) => reportar.mutate([i])}
        />
      )}

      {conciliacion && <PanelConciliacion conc={conciliacion} />}
    </div>
  );
}

function FormReporte({
  reportando,
  onReportar,
}: {
  reportando: boolean;
  onReportar: (input: {
    banco: string;
    saldo: string;
    fecha_reporte: string;
  }) => void;
}) {
  const [banco, setBanco] = useState<string>(BANCOS[0]);
  const [saldo, setSaldo] = useState("");
  const [fecha, setFecha] = useState(hoyLocal());

  const valido = saldo.trim() !== "" && fecha !== "";

  function enviar(e: FormEvent) {
    e.preventDefault();
    if (!valido) return;
    onReportar({ banco, saldo: saldo.trim(), fecha_reporte: fecha });
    setSaldo("");
  }

  return (
    <Card>
      <form onSubmit={enviar} className="flex flex-wrap items-end gap-3">
        <p className="w-full font-display text-base font-semibold text-ink">
          Reportar saldo
        </p>
        <label className="flex flex-col gap-1 font-sans text-xs font-medium text-ink-soft">
          Banco
          <select
            className="rounded-md border border-hairline bg-surface px-3 py-1.5 text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan"
            value={banco}
            onChange={(e) => setBanco(e.target.value)}
          >
            {BANCOS.map((b) => (
              <option key={b} value={b}>
                {BANCO_LABEL[b] ?? b}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 font-sans text-xs font-medium text-ink-soft">
          Saldo (COP)
          <input
            className="tabular w-40 rounded-md border border-hairline bg-surface px-3 py-1.5 text-right text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan"
            value={saldo}
            inputMode="decimal"
            placeholder="0.00"
            onChange={(e) => setSaldo(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1 font-sans text-xs font-medium text-ink-soft">
          Fecha del reporte
          <input
            type="date"
            className="rounded-md border border-hairline bg-surface px-3 py-1.5 text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan"
            value={fecha}
            onChange={(e) => setFecha(e.target.value)}
          />
        </label>
        <Button
          type="submit"
          variant="cyan"
          size="sm"
          disabled={reportando || !valido}
        >
          {reportando ? "Reportando…" : "Reportar"}
        </Button>
      </form>
    </Card>
  );
}

function PanelConciliacion({ conc }: { conc: Conciliacion }) {
  return (
    <Card className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="font-display text-base font-semibold text-ink">
          Conciliación
        </p>
        {conc.dentro_de_umbral ? (
          <span className="rounded-full bg-green/10 px-3 py-0.5 font-sans text-xs font-medium text-green">
            Cuadra (dentro del umbral)
          </span>
        ) : (
          <span className="rounded-full bg-red/10 px-3 py-0.5 font-sans text-xs font-medium text-red">
            No cuadra — diferencia {formatCOP(conc.diferencia)}
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiTile
          label="Reportado (bancos)"
          value={formatCOP(conc.consolidado_reportado)}
        />
        <KpiTile label="Caja del libro" value={formatCOP(conc.caja_libro)} />
        <KpiTile label="Diferencia" value={formatCOP(conc.diferencia)} />
        <KpiTile label="Umbral" value={formatCOP(conc.umbral)} />
      </div>

      {conc.por_banco.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full font-sans text-sm">
            <thead>
              <tr className="border-b border-hairline text-left text-ink-faint">
                <th className="px-4 py-2 font-semibold">Banco</th>
                <th className="px-4 py-2 text-right font-semibold">
                  Reportado
                </th>
                <th className="px-4 py-2 text-right font-semibold">
                  Calculado
                </th>
              </tr>
            </thead>
            <tbody>
              {conc.por_banco.map((b) => (
                <tr
                  key={b.banco}
                  className="border-b border-hairline/60 last:border-0"
                >
                  <td className="px-4 py-2 text-ink">
                    {BANCO_LABEL[b.banco] ?? b.banco}
                  </td>
                  <td className="tabular px-4 py-2 text-right text-ink-soft">
                    {formatCOP(b.reportado)}
                  </td>
                  <td className="tabular px-4 py-2 text-right text-ink-soft">
                    {formatCOP(b.calculado)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {conc.sin_dato.length > 0 && (
        <AlertBanner variant="warn">
          <span className="font-semibold">Sin saldo reportado:</span>{" "}
          {conc.sin_dato.map((b) => BANCO_LABEL[b] ?? b).join(" · ")} — tienen
          movimientos pero no se ha reportado su saldo.
        </AlertBanner>
      )}
    </Card>
  );
}
