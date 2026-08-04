// frontend/src/pages/CajaPage.tsx
//
// C4 ajuste diario de caja (CR-S6): reportar el saldo disponible por banco sobre el
// mes EN EJECUCIÓN y ver al instante si la información cuadra (conciliación D4). Es la
// segunda entrada diaria del norte (la otra es la carga de movimientos). El bloque de
// reporte vive en ReporteCajaCard (extraído en C2 para reusarlo en la Cabina).
//
// FIX-F: override del saldo inicial de caja (solo admin, ciclo:config + step-up MFA en
// el backend) — corrige el saldo de apertura del mes en ejecución con motivo auditado.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "@/auth/AuthContext";
import { ReporteCajaCard } from "@/components/caja/ReporteCajaCard";
import { PageHeader } from "@/components/layout/PageHeader";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { editarSaldoInicial } from "@/lib/caja";
import { type Mes, listarMeses } from "@/lib/meses";
import { formatCOP } from "@/lib/money";

export default function CajaPage() {
  const { puede } = useAuth();
  const meses = useQuery({ queryKey: ["meses"], queryFn: listarMeses });

  // El reporte diario es del mes OPERANDO (D3). Debe haber uno solo en ejecución.
  const mesActivo = useMemo(
    () => (meses.data?.items ?? []).find((m) => m.estado === "en_ejecucion"),
    [meses.data],
  );
  const mesCorto = mesActivo?.mes.slice(0, 7) ?? null;

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

      {mesActivo && <ReporteCajaCard mes={mesActivo} />}

      {mesActivo && puede("ciclo:config") && (
        <SaldoInicialCard mes={mesActivo} />
      )}
    </div>
  );
}

function SaldoInicialCard({ mes }: { mes: Mes }) {
  const qc = useQueryClient();
  const mes7 = mes.mes.slice(0, 7);
  const [abierto, setAbierto] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);

  return (
    <Card className="flex flex-col items-start gap-2">
      <CardTitle>Saldo inicial de caja</CardTitle>
      <p className="font-sans text-sm text-ink-soft">
        Apertura del mes {mes7}:{" "}
        <span className="tabular font-medium text-ink">
          {formatCOP(mes.saldo_inicial_caja)}
        </span>
        . Corrige el saldo de apertura (queda auditado con motivo).
      </p>
      {aviso && <AlertBanner variant="ok">{aviso}</AlertBanner>}
      <Button variant="outline" size="sm" onClick={() => setAbierto(true)}>
        Editar saldo inicial
      </Button>
      {abierto && (
        <EditarSaldoDialog
          mes7={mes7}
          actual={mes.saldo_inicial_caja}
          onCerrar={() => setAbierto(false)}
          onListo={(nuevo) => {
            setAviso(
              `Saldo inicial de ${mes7} actualizado a ${formatCOP(nuevo)}.`,
            );
            qc.invalidateQueries({ queryKey: ["meses"] });
            setAbierto(false);
          }}
        />
      )}
    </Card>
  );
}

function EditarSaldoDialog({
  mes7,
  actual,
  onCerrar,
  onListo,
}: {
  mes7: string;
  actual: string;
  onCerrar: () => void;
  onListo: (nuevo: string) => void;
}) {
  const [saldo, setSaldo] = useState(actual);
  const [motivo, setMotivo] = useState("");
  const [error, setError] = useState<string | null>(null);

  const guardar = useMutation({
    mutationFn: () => editarSaldoInicial(mes7, saldo.trim(), motivo.trim()),
    onSuccess: (r) => onListo(r.saldo_inicial_caja),
    onError: (e) =>
      setError(
        e instanceof Error ? e.message : "No se pudo editar el saldo inicial",
      ),
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!/^\d+(\.\d{1,2})?$/.test(saldo.trim())) {
      setError("El saldo inicial debe ser un número positivo (COP).");
      return;
    }
    if (motivo.trim() === "") {
      setError("El motivo es obligatorio (queda en la auditoría).");
      return;
    }
    guardar.mutate();
  }

  return (
    <div className="fixed inset-0 z-20 flex items-center justify-center bg-black/40 p-4">
      <dialog
        open
        aria-label="Editar saldo inicial"
        className="static w-full max-w-md rounded-lg border border-hairline bg-surface p-6 text-inherit shadow-lg"
      >
        <h3 className="mb-1 font-display text-lg font-semibold text-ink">
          Editar saldo inicial · {mes7}
        </h3>
        <p className="mb-4 font-sans text-apoyo text-ink-faint">
          Cambio sensible de dinero: requiere MFA reciente y queda auditado con
          el motivo. Actual: {formatCOP(actual)}.
        </p>
        <form
          onSubmit={onSubmit}
          className="flex flex-col gap-3 font-sans text-sm"
        >
          <label className="flex flex-col gap-1">
            <span className="font-medium text-ink">
              Nuevo saldo inicial (COP)
            </span>
            <input
              inputMode="decimal"
              className="tabular rounded-md border border-hairline bg-surface px-3 py-1.5 text-right text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan"
              value={saldo}
              onChange={(e) => setSaldo(e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="font-medium text-ink">Motivo</span>
            <input
              placeholder="Motivo del ajuste"
              className="rounded-md border border-hairline bg-surface px-3 py-1.5 text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan"
              value={motivo}
              onChange={(e) => setMotivo(e.target.value)}
            />
          </label>

          {error && <AlertBanner variant="danger">{error}</AlertBanner>}

          <div className="mt-2 flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onCerrar}>
              Cancelar
            </Button>
            <Button type="submit" variant="cyan" disabled={guardar.isPending}>
              {guardar.isPending ? "Guardando…" : "Guardar"}
            </Button>
          </div>
        </form>
      </dialog>
    </div>
  );
}
