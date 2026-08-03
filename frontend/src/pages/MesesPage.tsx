// frontend/src/pages/MesesPage.tsx
//
// Ciclo mensual (US-01): historial de meses + diálogo "Abrir mes". El primer mes
// de la historia pide saldo inicial; los siguientes lo ARRASTRAN del cierre
// anterior (F-14) → el formulario oculta ese campo y el backend lo deriva.
// Montos como string + formatCOP (regla 1); estados con color de marca.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "@/auth/AuthContext";
import { EstadoBadge } from "@/components/ciclo/EstadoBadge";
import { PageHeader } from "@/components/layout/PageHeader";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  type AbrirMesInput,
  BANCOS,
  type Mes,
  type SaldoBanco,
  abrirMes,
  listarMeses,
} from "@/lib/meses";
import { formatCOP, parseMonto } from "@/lib/money";

export default function MesesPage() {
  const { puede } = useAuth();
  const qc = useQueryClient();
  const [abierto, setAbierto] = useState(false);
  const [mensaje, setMensaje] = useState<string | null>(null);

  const meses = useQuery({ queryKey: ["meses"], queryFn: listarMeses });
  const hayHistoria = (meses.data?.items.length ?? 0) > 0;
  const gestor = puede("ciclo:abrir");

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        titulo="Meses"
        descripcion="Historial de meses. Abre el mes con el saldo inicial de caja y los saldos por banco al corte."
        acciones={
          gestor ? (
            <Button variant="cyan" onClick={() => setAbierto(true)}>
              Abrir mes
            </Button>
          ) : undefined
        }
      />

      {mensaje && (
        <output className="block rounded-md bg-positivo/10 px-3 py-2 font-sans text-sm text-positivo">
          {mensaje}
        </output>
      )}

      {meses.isLoading && (
        <p className="font-sans text-sm text-ink-soft">Cargando…</p>
      )}
      {meses.isError && (
        <AlertBanner variant="danger">No se pudo listar los meses.</AlertBanner>
      )}

      {meses.data && meses.data.items.length === 0 && (
        <p className="font-sans text-sm text-ink-soft">
          Aún no hay meses abiertos. Abre el primero con el saldo inicial de
          caja y los saldos por banco al corte.
        </p>
      )}

      {meses.data && meses.data.items.length > 0 && (
        <Card className="overflow-hidden p-0">
          <div className="overflow-x-auto">
            <table className="w-full font-sans text-sm">
              <thead>
                <tr className="border-b border-hairline text-left text-ink-faint">
                  <th className="px-4 py-2.5 font-semibold">Mes</th>
                  <th className="px-4 py-2.5 font-semibold">Estado</th>
                  <th className="px-4 py-2.5 text-right font-semibold">
                    Saldo inicial caja
                  </th>
                  <th className="px-4 py-2.5 font-semibold">Bancos al corte</th>
                  <th className="px-4 py-2.5 font-semibold">
                    <span className="sr-only">Acciones</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {meses.data.items.map((m) => (
                  <tr
                    key={m.id}
                    className="border-b border-hairline/60 last:border-0"
                  >
                    <td className="px-4 py-2 font-medium text-ink">
                      {m.mes.slice(0, 7)}
                    </td>
                    <td className="px-4 py-2">
                      <EstadoBadge estado={m.estado} />
                    </td>
                    <td className="tabular px-4 py-2 text-right text-ink-soft">
                      {formatCOP(m.saldo_inicial_caja)}
                      {/* CR-WAVA: tránsito heredado (solo cuando > 0) */}
                      {m.transito_heredado &&
                        parseMonto(m.transito_heredado).greaterThan(0) && (
                          <span className="block text-apoyo text-ink-faint">
                            Tránsito Wava: {formatCOP(m.transito_heredado)} ·
                            Total:{" "}
                            {formatCOP(
                              m.caja_inicial_total ?? m.saldo_inicial_caja,
                            )}
                          </span>
                        )}
                    </td>
                    <td className="px-4 py-2 text-ink-soft">
                      {m.saldos_banco.length === 0
                        ? "—"
                        : m.saldos_banco
                            .map((s) => `${s.banco}: ${formatCOP(s.saldo)}`)
                            .join(" · ")}
                    </td>
                    <td className="px-4 py-2 text-right">
                      <Link
                        to={`/meses/${m.mes.slice(0, 7)}/presupuesto`}
                        className="font-medium whitespace-nowrap text-cyan hover:underline"
                      >
                        Gestionar presupuesto →
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {abierto && (
        <AbrirMesDialog
          pedirSaldo={!hayHistoria}
          alCerrar={() => setAbierto(false)}
          alAbrir={(m) => {
            setMensaje(
              `Mes ${m.mes.slice(0, 7)} abierto (saldo inicial ${formatCOP(m.saldo_inicial_caja)}).`,
            );
            qc.invalidateQueries({ queryKey: ["meses"] });
            setAbierto(false);
          }}
        />
      )}
    </div>
  );
}

function AbrirMesDialog({
  pedirSaldo,
  alCerrar,
  alAbrir,
}: {
  pedirSaldo: boolean;
  alCerrar: () => void;
  alAbrir: (m: Mes) => void;
}) {
  const hoy = new Date();
  const [mes, setMes] = useState(
    `${hoy.getFullYear()}-${String(hoy.getMonth() + 1).padStart(2, "0")}`,
  );
  const [saldoCaja, setSaldoCaja] = useState("");
  const [saldos, setSaldos] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  const abrir = useMutation({
    mutationFn: () => {
      const fecha = `${mes}-01`;
      const saldos_banco: SaldoBanco[] = BANCOS.filter(
        (b) => (saldos[b] ?? "").trim() !== "",
      ).map((b) => ({ banco: b, saldo: saldos[b], fecha_reporte: fecha }));
      const input: AbrirMesInput = { mes: fecha, saldos_banco };
      if (pedirSaldo) input.saldo_inicial_caja = saldoCaja;
      return abrirMes(input);
    },
    onSuccess: alAbrir,
    onError: (e) =>
      setError(e instanceof Error ? e.message : "Error abriendo el mes"),
  });

  const montoOk = (s: string) => /^\d+(\.\d{1,2})?$/.test(s);

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (pedirSaldo && !montoOk(saldoCaja)) {
      setError("El saldo inicial de caja debe ser un monto positivo.");
      return;
    }
    for (const b of BANCOS) {
      const v = saldos[b] ?? "";
      if (v.trim() !== "" && !montoOk(v)) {
        setError(`El saldo de ${b} no es un monto válido.`);
        return;
      }
    }
    abrir.mutate();
  }

  return (
    <div className="fixed inset-0 z-10 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-lg border border-hairline bg-surface p-6 shadow-lg">
        <h3 className="mb-1 font-display text-lg font-semibold text-ink">
          Abrir mes
        </h3>
        <p className="mb-4 font-sans text-apoyo text-ink-faint">
          {pedirSaldo
            ? "Primer mes: ingresa el saldo inicial de caja y los saldos por banco al corte."
            : "El saldo inicial se arrastra automáticamente del cierre del mes anterior (F-14)."}
        </p>
        <form
          onSubmit={onSubmit}
          className="flex flex-col gap-3 font-sans text-sm"
        >
          <label className="font-medium text-ink" htmlFor="mes-input">
            Mes
          </label>
          <input
            id="mes-input"
            type="month"
            required
            className="rounded-md border border-hairline bg-surface px-3 py-1.5 text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan"
            value={mes}
            onChange={(e) => setMes(e.target.value)}
          />

          {pedirSaldo && (
            <>
              <label className="font-medium text-ink" htmlFor="saldo-caja">
                Saldo inicial de caja (COP)
              </label>
              <input
                id="saldo-caja"
                required
                inputMode="decimal"
                placeholder="24000000"
                className="tabular rounded-md border border-hairline bg-surface px-3 py-1.5 text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan"
                value={saldoCaja}
                onChange={(e) => setSaldoCaja(e.target.value)}
              />
            </>
          )}

          <span className="mt-1 font-medium text-ink">
            Saldos por banco al corte
          </span>
          {BANCOS.map((b) => (
            <label key={b} className="flex items-center gap-2">
              <span className="w-28 capitalize text-ink-soft">{b}</span>
              <input
                inputMode="decimal"
                placeholder="0"
                className="tabular flex-1 rounded-md border border-hairline bg-surface px-3 py-1.5 text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan"
                value={saldos[b] ?? ""}
                onChange={(e) =>
                  setSaldos((s) => ({ ...s, [b]: e.target.value }))
                }
              />
            </label>
          ))}

          {error && <AlertBanner variant="danger">{error}</AlertBanner>}
          <div className="mt-2 flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={alCerrar}>
              Cancelar
            </Button>
            <Button type="submit" variant="cyan" disabled={abrir.isPending}>
              {abrir.isPending ? "Abriendo…" : "Abrir mes"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
