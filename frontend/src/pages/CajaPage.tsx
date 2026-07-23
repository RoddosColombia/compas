// frontend/src/pages/CajaPage.tsx
//
// C4 ajuste diario de caja (CR-S6): reportar el saldo disponible por banco sobre el
// mes EN EJECUCIÓN y ver al instante si la información cuadra (conciliación D4). Es la
// segunda entrada diaria del norte (la otra es la carga de movimientos). Montos con
// formatCOP (regla 1); el cálculo y el "¿cuadra?" vienen del backend. El formulario
// solo aparece con caja:reportar (regla 9); la autoridad real la impone el backend.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useMemo, useState } from "react";

import { useAuth } from "@/auth/AuthContext";
import { Button } from "@/components/ui/button";
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
      <header>
        <h2 className="text-xl font-semibold">Caja disponible</h2>
        <p className="text-xs text-slate-400">
          Reporta el saldo de cada banco para que la información siempre cuadre
          {mesCorto ? ` · mes ${mesCorto}` : ""}
        </p>
      </header>

      {meses.isLoading && <p className="text-sm text-slate-500">Cargando…</p>}
      {meses.data && !mesActivo && (
        <p className="text-sm text-slate-500">
          No hay ningún mes en ejecución. Aprueba el presupuesto de un mes para
          reportar su caja.
        </p>
      )}

      {mensaje && (
        <p className="rounded-md bg-alert/10 px-3 py-2 text-sm text-alert">
          {mensaje}
        </p>
      )}

      {mesActivo && (
        <section className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-slate-500">
                <th className="py-2 pr-4">Banco</th>
                <th className="py-2 pr-4 text-right">Saldo reportado</th>
                <th className="py-2 pr-4">Fecha del reporte</th>
              </tr>
            </thead>
            <tbody>
              {BANCOS.map((b) => {
                const sb = saldoPorBanco.get(b);
                return (
                  <tr key={b} className="border-b border-slate-100">
                    <td className="py-2 pr-4">{BANCO_LABEL[b] ?? b}</td>
                    <td className="py-2 pr-4 text-right font-mono">
                      {sb ? formatCOP(sb.saldo) : "—"}
                    </td>
                    <td className="py-2 pr-4 text-slate-500">
                      {sb ? formatFecha(sb.fecha_reporte) : "sin reporte"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
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
    <form
      onSubmit={enviar}
      className="flex flex-wrap items-end gap-3 rounded-lg border border-slate-200 p-4"
    >
      <p className="w-full text-sm font-medium">Reportar saldo</p>
      <label className="flex flex-col gap-1 text-xs text-slate-500">
        Banco
        <select
          className="rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800"
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
      <label className="flex flex-col gap-1 text-xs text-slate-500">
        Saldo (COP)
        <input
          className="w-40 rounded-md border border-slate-300 px-2 py-1.5 text-right text-sm text-slate-800"
          value={saldo}
          inputMode="decimal"
          placeholder="0.00"
          onChange={(e) => setSaldo(e.target.value)}
        />
      </label>
      <label className="flex flex-col gap-1 text-xs text-slate-500">
        Fecha del reporte
        <input
          type="date"
          className="rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800"
          value={fecha}
          onChange={(e) => setFecha(e.target.value)}
        />
      </label>
      <Button type="submit" size="sm" disabled={reportando || !valido}>
        {reportando ? "Reportando…" : "Reportar"}
      </Button>
    </form>
  );
}

function PanelConciliacion({ conc }: { conc: Conciliacion }) {
  return (
    <section className="flex flex-col gap-3 rounded-lg border border-slate-200 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm font-medium">Conciliación</p>
        {conc.dentro_de_umbral ? (
          <span className="rounded-full bg-brand-soft/20 px-3 py-0.5 text-xs font-medium text-brand">
            Cuadra (dentro del umbral)
          </span>
        ) : (
          <span className="rounded-full bg-alert/20 px-3 py-0.5 text-xs font-medium text-alert">
            No cuadra — diferencia {formatCOP(conc.diferencia)}
          </span>
        )}
      </div>

      <div className="flex flex-wrap gap-4 text-sm">
        <Dato
          titulo="Reportado (bancos)"
          valor={formatCOP(conc.consolidado_reportado)}
        />
        <Dato titulo="Caja del libro" valor={formatCOP(conc.caja_libro)} />
        <Dato titulo="Diferencia" valor={formatCOP(conc.diferencia)} />
        <Dato titulo="Umbral" valor={formatCOP(conc.umbral)} />
      </div>

      {conc.por_banco.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-slate-500">
                <th className="py-1.5 pr-4">Banco</th>
                <th className="py-1.5 pr-4 text-right">Reportado</th>
                <th className="py-1.5 pr-4 text-right">Calculado</th>
              </tr>
            </thead>
            <tbody>
              {conc.por_banco.map((b) => (
                <tr key={b.banco} className="border-b border-slate-100">
                  <td className="py-1.5 pr-4">
                    {BANCO_LABEL[b.banco] ?? b.banco}
                  </td>
                  <td className="py-1.5 pr-4 text-right font-mono">
                    {formatCOP(b.reportado)}
                  </td>
                  <td className="py-1.5 pr-4 text-right font-mono">
                    {formatCOP(b.calculado)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {conc.sin_dato.length > 0 && (
        <p className="rounded-md bg-warn/10 px-3 py-2 text-xs text-slate-700">
          <span className="font-medium text-warn">Sin saldo reportado:</span>{" "}
          {conc.sin_dato.map((b) => BANCO_LABEL[b] ?? b).join(" · ")} — tienen
          movimientos pero no se ha reportado su saldo.
        </p>
      )}
    </section>
  );
}

function Dato({ titulo, valor }: { titulo: string; valor: string }) {
  return (
    <div className="min-w-36 flex-1 rounded-md border border-slate-200 px-3 py-2">
      <p className="text-xs text-slate-500">{titulo}</p>
      <p className="mt-0.5 font-mono text-sm font-semibold text-slate-800">
        {valor}
      </p>
    </div>
  );
}
