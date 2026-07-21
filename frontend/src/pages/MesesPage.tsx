// frontend/src/pages/MesesPage.tsx
//
// Ciclo mensual (US-01): historial de meses + diálogo "Abrir mes". El primer mes
// de la historia pide saldo inicial; los siguientes lo ARRASTRAN del cierre
// anterior (F-14) → el formulario oculta ese campo y el backend lo deriva.
// Montos como string + formatCOP (regla 1); estados con color de marca.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";

import { useAuth } from "@/auth/AuthContext";
import { Button } from "@/components/ui/button";
import {
  type AbrirMesInput,
  BANCOS,
  type Mes,
  type SaldoBanco,
  abrirMes,
  listarMeses,
} from "@/lib/meses";
import { formatCOP } from "@/lib/money";

const ESTADO_ESTILO: Record<Mes["estado"], string> = {
  sugerido: "bg-slate-100 text-slate-700",
  propuesto: "bg-turq-soft/30 text-turq",
  definido: "bg-brand-soft/20 text-brand",
  en_ejecucion: "bg-brand-soft/30 text-brand",
  cerrado: "bg-slate-800 text-white",
};

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
      <header className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Ciclo mensual</h2>
        {gestor && <Button onClick={() => setAbierto(true)}>Abrir mes</Button>}
      </header>

      {mensaje && (
        <output className="block rounded-md bg-brand-soft/15 px-3 py-2 text-sm text-brand">
          {mensaje}
        </output>
      )}

      {meses.isLoading && <p className="text-sm text-slate-500">Cargando…</p>}
      {meses.isError && (
        <p className="text-sm text-alert">No se pudo listar los meses.</p>
      )}

      {meses.data && meses.data.items.length === 0 && (
        <p className="text-sm text-slate-500">
          Aún no hay meses abiertos. Abre el primero con el saldo inicial de
          caja y los saldos por banco al corte.
        </p>
      )}

      {meses.data && meses.data.items.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-slate-500">
                <th className="py-2 pr-4">Mes</th>
                <th className="py-2 pr-4">Estado</th>
                <th className="py-2 pr-4 text-right">Saldo inicial caja</th>
                <th className="py-2 pr-4">Bancos al corte</th>
              </tr>
            </thead>
            <tbody>
              {meses.data.items.map((m) => (
                <tr
                  key={m.id}
                  className="border-b border-slate-100 last:border-0"
                >
                  <td className="py-2 pr-4 font-medium">{m.mes.slice(0, 7)}</td>
                  <td className="py-2 pr-4">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ${ESTADO_ESTILO[m.estado]}`}
                    >
                      {m.estado}
                    </span>
                  </td>
                  <td className="py-2 pr-4 text-right font-mono">
                    {formatCOP(m.saldo_inicial_caja)}
                  </td>
                  <td className="py-2 pr-4 text-slate-500">
                    {m.saldos_banco.length === 0
                      ? "—"
                      : m.saldos_banco
                          .map((s) => `${s.banco}: ${formatCOP(s.saldo)}`)
                          .join(" · ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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
      <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-lg">
        <h3 className="mb-1 text-lg font-semibold">Abrir mes</h3>
        <p className="mb-4 text-xs text-slate-500">
          {pedirSaldo
            ? "Primer mes: ingresa el saldo inicial de caja y los saldos por banco al corte."
            : "El saldo inicial se arrastra automáticamente del cierre del mes anterior (F-14)."}
        </p>
        <form onSubmit={onSubmit} className="flex flex-col gap-3 text-sm">
          <label className="font-medium" htmlFor="mes-input">
            Mes
          </label>
          <input
            id="mes-input"
            type="month"
            required
            className="rounded-md border border-slate-300 px-3 py-2"
            value={mes}
            onChange={(e) => setMes(e.target.value)}
          />

          {pedirSaldo && (
            <>
              <label className="font-medium" htmlFor="saldo-caja">
                Saldo inicial de caja (COP)
              </label>
              <input
                id="saldo-caja"
                required
                inputMode="decimal"
                placeholder="24000000"
                className="rounded-md border border-slate-300 px-3 py-2"
                value={saldoCaja}
                onChange={(e) => setSaldoCaja(e.target.value)}
              />
            </>
          )}

          <span className="mt-1 font-medium">Saldos por banco al corte</span>
          {BANCOS.map((b) => (
            <label key={b} className="flex items-center gap-2">
              <span className="w-28 capitalize text-slate-600">{b}</span>
              <input
                inputMode="decimal"
                placeholder="0"
                className="flex-1 rounded-md border border-slate-300 px-3 py-2"
                value={saldos[b] ?? ""}
                onChange={(e) =>
                  setSaldos((s) => ({ ...s, [b]: e.target.value }))
                }
              />
            </label>
          ))}

          {error && <p className="text-alert">{error}</p>}
          <div className="mt-2 flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={alCerrar}>
              Cancelar
            </Button>
            <Button type="submit" disabled={abrir.isPending}>
              {abrir.isPending ? "Abriendo…" : "Abrir mes"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
