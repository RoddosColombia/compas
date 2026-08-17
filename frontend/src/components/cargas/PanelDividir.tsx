// components/cargas/PanelDividir.tsx
//
// PTS6-B/D-UI — panel de "Transacciones del mes" con la acción DIVIDIR: un movimiento
// bancario que cubre varios conceptos (p. ej. una transferencia = préstamo + garantía
// Auteco) se reparte en partes de clasificación que SUMAN EXACTO su valor. Los
// inmutables (valor/fecha/banco) no cambian (Spec §2.2). Reusa GET /transacciones (sin
// filtro de banco) + POST /{id}/dividir · /{id}/deshacer-division. Montos como string
// (regla 1); decimal.js-light para validar la suma, nunca Number.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Decimal from "decimal.js-light";
import { useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  type ParteTransaccion,
  type TransaccionMovimiento,
  deshacerDivision,
  dividirTransaccion,
  listarTransaccionesMes,
} from "@/lib/cargas";
import { formatCOP, formatFecha, parseMonto } from "@/lib/money";
import { type Rubro, listarRubros } from "@/lib/rubros";

const RE_MONTO = /^\d+(\.\d{1,2})?$/;

function mesCalendarioActual(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function PanelDividir({ gestor }: { gestor: boolean }) {
  const qc = useQueryClient();
  const [mes, setMes] = useState(mesCalendarioActual());
  const [aDividir, setADividir] = useState<TransaccionMovimiento | null>(null);

  const movs = useQuery({
    queryKey: ["transacciones-mes", mes],
    queryFn: () => listarTransaccionesMes(mes),
  });
  const rubrosQ = useQuery({ queryKey: ["rubros"], queryFn: listarRubros });
  const rubros = rubrosQ.data ?? [];
  const nombreRubro = useMemo(
    () => new Map(rubros.map((r) => [r.id, r.nombre])),
    [rubros],
  );

  const items = (movs.data?.items ?? []).filter((m) => !m.es_reverso);

  const invalidar = () => {
    void qc.invalidateQueries({ queryKey: ["transacciones-mes"] });
    void qc.invalidateQueries({ queryKey: ["transacciones-manuales"] });
    void qc.invalidateQueries({ queryKey: ["caja"] });
    void qc.invalidateQueries({ queryKey: ["control"] });
  };

  const deshacer = useMutation({
    mutationFn: (id: string) => deshacerDivision(id),
    onSuccess: invalidar,
  });

  return (
    <Card className="flex flex-col gap-3 p-0">
      <div className="flex flex-wrap items-center justify-between gap-2 px-5 pt-5">
        <div>
          <h3 className="font-display text-base font-semibold text-ink">
            Transacciones del mes
          </h3>
          <p className="font-sans text-apoyo text-ink-soft">
            Divide un movimiento que cubre varios conceptos (p. ej. préstamo +
            garantía Auteco) en partes que suman su valor. No cambia el monto ni
            el banco.
          </p>
        </div>
        <label className="flex items-center gap-2 font-sans text-sm text-ink-soft">
          Mes
          <input
            type="month"
            value={mes}
            onChange={(e) => setMes(e.target.value)}
            className="rounded-md border border-hairline bg-surface px-2 py-1 text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan"
          />
        </label>
      </div>

      {movs.isLoading ? (
        <p className="px-5 pb-5 font-sans text-sm text-ink-soft">Cargando…</p>
      ) : items.length === 0 ? (
        <p className="px-5 pb-5 font-sans text-sm text-ink-soft">
          Sin transacciones en {mes}.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full font-sans text-sm">
            <thead>
              <tr className="border-b border-hairline text-left text-ink-faint">
                <th className="px-5 py-2.5 font-semibold">Fecha</th>
                <th className="px-5 py-2.5 font-semibold">Descripción</th>
                <th className="px-5 py-2.5 font-semibold">Banco</th>
                <th className="px-5 py-2.5 text-right font-semibold">Valor</th>
                <th className="px-5 py-2.5 font-semibold">Clasificación</th>
                {gestor && (
                  <th className="px-5 py-2.5 text-right font-semibold">
                    <span className="sr-only">Acciones</span>
                  </th>
                )}
              </tr>
            </thead>
            <tbody>
              {items.map((m) => (
                <tr
                  key={m.id}
                  className="border-b border-hairline/60 last:border-0"
                  data-testid={`tx-${m.id}`}
                >
                  <td className="px-5 py-2 whitespace-nowrap text-ink-soft">
                    {formatFecha(m.fecha)}
                  </td>
                  <td className="px-5 py-2 text-ink">{m.descripcion}</td>
                  <td className="px-5 py-2 capitalize text-ink-soft">
                    {m.banco}
                  </td>
                  <td className="tabular px-5 py-2 text-right text-ink-soft">
                    {formatCOP(m.valor)}
                  </td>
                  <td className="px-5 py-2 text-ink-soft">
                    {m.dividida && m.partes ? (
                      <span className="flex flex-col gap-0.5">
                        <span className="font-medium text-cyan">
                          Dividida en {m.partes.length}
                        </span>
                        {m.partes.map((p, i) => (
                          <span
                            key={`${p.rubro_id}-${i}`}
                            className="text-apoyo text-ink-faint"
                          >
                            {nombreRubro.get(p.rubro_id) ?? "?"}:{" "}
                            {formatCOP(p.valor)}
                          </span>
                        ))}
                      </span>
                    ) : (
                      (nombreRubro.get(m.rubro_id) ?? "—")
                    )}
                  </td>
                  {gestor && (
                    <td className="px-5 py-2 text-right whitespace-nowrap">
                      {m.dividida ? (
                        <button
                          type="button"
                          className="font-medium text-critico hover:underline disabled:opacity-50"
                          disabled={deshacer.isPending}
                          onClick={() => deshacer.mutate(m.id)}
                        >
                          Deshacer división
                        </button>
                      ) : (
                        <button
                          type="button"
                          className="font-medium text-cyan hover:underline"
                          onClick={() => setADividir(m)}
                        >
                          Dividir
                        </button>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {aDividir && (
        <DividirDialog
          mov={aDividir}
          rubros={rubros}
          onDividir={async (partes) => {
            await dividirTransaccion(aDividir.id, partes);
            setADividir(null);
            invalidar();
          }}
          onCerrar={() => setADividir(null)}
        />
      )}
    </Card>
  );
}

interface FilaParte {
  /** Clave ESTABLE de React: las filas se agregan/quitan y el índice se recicla
   * (noArrayIndexKey) — un contador por diálogo evita estados cruzados. */
  key: number;
  rubro_id: string;
  valor: string;
}

function DividirDialog({
  mov,
  rubros,
  onDividir,
  onCerrar,
}: {
  mov: TransaccionMovimiento;
  rubros: Rubro[];
  onDividir: (partes: ParteTransaccion[]) => Promise<void>;
  onCerrar: () => void;
}) {
  // Rubros candidatos: activos, del mismo tipo_flujo que la transacción (el backend
  // valida además que no sean de sistema no-clasificables).
  const candidatos = rubros.filter(
    (r) => r.activo && r.tipo_flujo === mov.tipo_flujo,
  );
  const [filas, setFilas] = useState<FilaParte[]>([
    { key: 0, rubro_id: mov.rubro_id, valor: "" },
    { key: 1, rubro_id: "", valor: "" },
  ]);
  const siguienteKey = useRef(2);
  const [error, setError] = useState<string | null>(null);
  const [pendiente, setPendiente] = useState(false);

  const total = parseMonto(mov.valor);
  const suma = filas.reduce(
    (a, f) => (RE_MONTO.test(f.valor.trim()) ? a.plus(f.valor.trim()) : a),
    new Decimal(0),
  );
  const restante = total.minus(suma);
  const cuadra = restante.isZero();

  const setFila = (i: number, campo: keyof FilaParte, v: string) =>
    setFilas((prev) =>
      prev.map((f, idx) => (idx === i ? { ...f, [campo]: v } : f)),
    );
  const agregar = () =>
    setFilas((prev) => [
      ...prev,
      { key: siguienteKey.current++, rubro_id: "", valor: "" },
    ]);
  const quitar = (i: number) =>
    setFilas((prev) =>
      prev.length > 2 ? prev.filter((_, idx) => idx !== i) : prev,
    );

  async function onSubmit() {
    setError(null);
    if (filas.some((f) => f.rubro_id === "")) {
      setError("Elige un rubro para cada parte.");
      return;
    }
    if (filas.some((f) => !RE_MONTO.test(f.valor.trim()))) {
      setError("Cada parte debe tener un monto válido (COP).");
      return;
    }
    if (new Set(filas.map((f) => f.rubro_id)).size !== filas.length) {
      setError("No repitas el mismo rubro en dos partes.");
      return;
    }
    if (!cuadra) {
      setError(
        `Las partes deben sumar exacto ${formatCOP(mov.valor)} (faltan ${formatCOP(restante)}).`,
      );
      return;
    }
    setPendiente(true);
    try {
      await onDividir(
        filas.map((f) => ({ rubro_id: f.rubro_id, valor: f.valor.trim() })),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo dividir");
      setPendiente(false);
    }
  }

  return (
    <div className="fixed inset-0 z-20 flex items-center justify-center bg-black/40 p-4">
      <dialog
        open
        aria-label="Dividir transacción"
        className="static w-full max-w-lg rounded-lg border border-hairline bg-surface p-6 text-inherit shadow-lg"
      >
        <h3 className="mb-1 font-display text-lg font-semibold text-ink">
          Dividir transacción
        </h3>
        <p className="mb-4 font-sans text-sm text-ink-soft">
          {formatFecha(mov.fecha)} · {mov.descripcion} ·{" "}
          <span className="tabular font-medium text-ink">
            {formatCOP(mov.valor)}
          </span>
        </p>

        <div className="flex flex-col gap-2 font-sans text-sm">
          {filas.map((f, i) => (
            <div key={f.key} className="flex items-center gap-2">
              <select
                aria-label={`Rubro parte ${i + 1}`}
                className="min-w-0 flex-1 rounded-md border border-hairline bg-surface px-2 py-1.5 text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan"
                value={f.rubro_id}
                onChange={(e) => setFila(i, "rubro_id", e.target.value)}
              >
                <option value="">— rubro —</option>
                {candidatos.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.codigo ? `${r.codigo} · ` : ""}
                    {r.nombre}
                  </option>
                ))}
              </select>
              <input
                inputMode="decimal"
                aria-label={`Monto parte ${i + 1}`}
                placeholder="0"
                className="tabular w-36 rounded-md border border-hairline bg-surface px-2 py-1.5 text-right text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan"
                value={f.valor}
                onChange={(e) => setFila(i, "valor", e.target.value)}
              />
              <button
                type="button"
                aria-label={`Quitar parte ${i + 1}`}
                className="text-ink-faint hover:text-critico disabled:opacity-30"
                disabled={filas.length <= 2}
                onClick={() => quitar(i)}
              >
                ✕
              </button>
            </div>
          ))}
        </div>

        <button
          type="button"
          className="mt-2 font-sans text-sm font-medium text-cyan hover:underline"
          onClick={agregar}
        >
          + Agregar parte
        </button>

        <div className="mt-3 flex items-center justify-between border-t border-hairline pt-2 font-sans text-sm">
          <span className="text-ink-soft">Suma de partes</span>
          <span
            className={`tabular font-medium ${cuadra ? "text-positivo" : "text-critico"}`}
            data-testid="suma-partes"
          >
            {formatCOP(suma)} {cuadra ? "✓" : `(faltan ${formatCOP(restante)})`}
          </span>
        </div>

        {error && (
          <div className="mt-3 rounded-md bg-critico/10 px-3 py-2 font-sans text-sm text-critico">
            {error}
          </div>
        )}

        <div className="mt-4 flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onCerrar}>
            Cancelar
          </Button>
          <Button
            type="button"
            variant="cyan"
            disabled={pendiente || !cuadra}
            onClick={onSubmit}
          >
            {pendiente ? "Dividiendo…" : "Dividir"}
          </Button>
        </div>
      </dialog>
    </div>
  );
}
