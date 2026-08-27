// ReporteCajaCard — el bloque de reporte diario de caja (C4/CR-S6), extraído de
// CajaPage en C2 para reusarlo en la Cabina del mes. Saldos por banco con fecha
// del último reporte, formulario de reporte (solo con caja:reportar — regla 9) y
// la conciliación ("¿cuadra?") que devuelve el backend. Montos con formatCOP
// (regla 1); las guardas viven en el backend, aquí solo se muestra su detail.

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";

import { useAuth } from "@/auth/AuthContext";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { KpiTileV2 } from "@/components/ui/kpi-tile";
import {
  type Conciliacion,
  type ReporteSaldosResultado,
  reportarSaldos,
} from "@/lib/caja";
import { BANCOS, type Mes } from "@/lib/meses";
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

/** Bloque completo de caja del día para un mes EN EJECUCIÓN. */
export function ReporteCajaCard({ mes }: { mes: Mes }) {
  const { puede } = useAuth();
  const reporta = puede("caja:reportar");
  const qc = useQueryClient();
  const [mensaje, setMensaje] = useState<string | null>(null);
  const [conciliacion, setConciliacion] = useState<Conciliacion | null>(null);

  const mesCorto = mes.mes.slice(0, 7);

  const reportar = useMutation({
    mutationFn: (
      saldos: { banco: string; saldo: string; fecha_reporte: string }[],
    ) => reportarSaldos(mesCorto, saldos),
    onSuccess: (r: ReporteSaldosResultado) => {
      setMensaje(null);
      setConciliacion(r.conciliacion);
      qc.invalidateQueries({ queryKey: ["meses"] });
      // Reportar un saldo re-ancla el disponible en vivo (CEO 2026-08-24).
      qc.invalidateQueries({ queryKey: ["caja"] });
    },
    onError: (e: unknown) =>
      setMensaje(e instanceof Error ? e.message : "Error"),
  });

  const saldoPorBanco = new Map(mes.saldos_banco.map((s) => [s.banco, s]));

  return (
    <div className="flex flex-col gap-6">
      {mensaje && <AlertBanner variant="danger">{mensaje}</AlertBanner>}

      <Card className="overflow-hidden p-0">
        <div className="overflow-x-auto">
          <table className="w-full font-sans text-sm">
            <thead>
              <tr className="border-b border-hairline text-left text-ink-faint">
                <th className="px-4 py-2.5 font-semibold">Banco</th>
                <th className="px-4 py-2.5 text-right font-semibold">
                  Saldo reportado
                </th>
                <th className="px-4 py-2.5 font-semibold">Fecha del reporte</th>
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

      {reporta && (
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
        <label className="flex flex-col gap-1 font-sans text-apoyo font-medium text-ink-soft">
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
        <label className="flex flex-col gap-1 font-sans text-apoyo font-medium text-ink-soft">
          Saldo (COP)
          <input
            className="tabular w-40 rounded-md border border-hairline bg-surface px-3 py-1.5 text-right text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan"
            value={saldo}
            inputMode="decimal"
            placeholder="0.00"
            onChange={(e) => setSaldo(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1 font-sans text-apoyo font-medium text-ink-soft">
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
          <span className="rounded-full bg-positivo/10 px-3 py-0.5 font-sans text-apoyo font-medium text-positivo">
            Cuadra (dentro del margen)
          </span>
        ) : (
          <span className="rounded-full bg-critico/10 px-3 py-0.5 font-sans text-apoyo font-medium text-critico">
            No cuadra — diferencia {formatCOP(conc.diferencia)}
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiTileV2
          label="Reportado (bancos)"
          valor="0"
          valorTexto={formatCOP(conc.consolidado_reportado)}
          contexto="suma de los saldos reportados"
        />
        <KpiTileV2
          label="Caja del libro"
          valor="0"
          valorTexto={formatCOP(conc.caja_libro)}
          contexto="saldo inicial + movimientos"
        />
        <KpiTileV2
          label="Diferencia"
          valor="0"
          valorTexto={formatCOP(conc.diferencia)}
          contexto="reportado menos libro, al centavo"
          tono={conc.dentro_de_umbral ? "positivo" : "critico"}
        />
        <KpiTileV2
          label="Margen"
          valor="0"
          valorTexto={formatCOP(conc.umbral)}
          contexto="tolerancia aceptada al cierre"
        />
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
