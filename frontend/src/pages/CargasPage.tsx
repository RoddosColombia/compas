// frontend/src/pages/CargasPage.tsx
//
// Pantalla de cargas (PRD M7 / Spec §1.6): subir extracto (F-22), historial con
// conteos, detalle de errores por fila (regla 7: el texto crudo se muestra al
// Financiero) y registro de transacción manual (US-10) con Idempotency-Key.
// Los montos son strings; formato SOLO con formatCOP (regla 1).

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useRef, useState } from "react";

import { useAuth } from "@/auth/AuthContext";
import { Button } from "@/components/ui/button";
import {
  type Carga,
  type TransaccionManualInput,
  crearTransaccionManual,
  detalleCarga,
  listarCargas,
  subirExtracto,
  validarArchivo,
} from "@/lib/cargas";
import { formatCOP, formatFecha } from "@/lib/money";

const ESTADO_ESTILO: Record<Carga["estado"], string> = {
  completada: "bg-emerald-100 text-emerald-800",
  procesando: "bg-amber-100 text-amber-800",
  fallida: "bg-red-100 text-red-800",
};

export default function CargasPage() {
  const { puede } = useAuth();
  const qc = useQueryClient();
  const [mensaje, setMensaje] = useState<string | null>(null);
  const [detalleId, setDetalleId] = useState<string | null>(null);
  const [manualAbierto, setManualAbierto] = useState(false);
  const inputArchivo = useRef<HTMLInputElement>(null);

  const cargas = useQuery({
    queryKey: ["cargas"],
    queryFn: () => listarCargas(),
  });
  const detalle = useQuery({
    queryKey: ["cargas", detalleId],
    queryFn: () => detalleCarga(detalleId as string),
    enabled: detalleId !== null,
  });

  const subir = useMutation({
    mutationFn: subirExtracto,
    onSuccess: (c) => {
      setMensaje(
        `Carga ${c.estado}: ${c.nuevas} nuevas, ${c.duplicadas} duplicadas, ${c.errores} errores.`,
      );
      qc.invalidateQueries({ queryKey: ["cargas"] });
    },
    onError: (e) =>
      setMensaje(e instanceof Error ? e.message : "Error en la carga"),
  });

  function onArchivo(files: FileList | null) {
    setMensaje(null);
    const f = files?.[0];
    if (!f) return;
    const problema = validarArchivo(f.name, f.size);
    if (problema) {
      setMensaje(problema);
    } else {
      subir.mutate(f);
    }
    if (inputArchivo.current) inputArchivo.current.value = "";
  }

  const gestor = puede("cargas:gestionar");

  return (
    <div className="flex flex-col gap-6">
      <header className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Cargas bancarias</h2>
        {gestor && (
          <div className="flex gap-2">
            <input
              ref={inputArchivo}
              type="file"
              accept=".xlsx,.xls"
              className="hidden"
              data-testid="input-extracto"
              onChange={(e) => onArchivo(e.target.files)}
            />
            <Button
              onClick={() => inputArchivo.current?.click()}
              disabled={subir.isPending}
            >
              {subir.isPending ? "Procesando…" : "Subir extracto"}
            </Button>
            <Button variant="outline" onClick={() => setManualAbierto(true)}>
              Transacción manual
            </Button>
          </div>
        )}
      </header>

      {mensaje && (
        <output className="block rounded-md bg-slate-100 px-3 py-2 text-sm">
          {mensaje}
        </output>
      )}

      {cargas.isLoading && <p className="text-sm text-slate-500">Cargando…</p>}
      {cargas.isError && (
        <p className="text-sm text-red-600">No se pudo listar las cargas.</p>
      )}

      {cargas.data && cargas.data.items.length === 0 && (
        <p className="text-sm text-slate-500">
          Sin cargas todavía. Sube el primer extracto (.xlsx de Bancolombia,
          BBVA o Global66).
        </p>
      )}

      {cargas.data && cargas.data.items.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-slate-500">
                <th className="py-2 pr-4">Fecha</th>
                <th className="py-2 pr-4">Banco</th>
                <th className="py-2 pr-4">Archivo</th>
                <th className="py-2 pr-4">Estado</th>
                <th className="py-2 pr-4 text-right">Nuevas</th>
                <th className="py-2 pr-4 text-right">Duplicadas</th>
                <th className="py-2 pr-4 text-right">Errores</th>
                <th className="py-2" />
              </tr>
            </thead>
            <tbody>
              {cargas.data.items.map((c) => (
                <tr key={c.id} className="border-b last:border-0">
                  <td className="py-2 pr-4 whitespace-nowrap">
                    {formatFecha(c.created_at.slice(0, 10))}
                  </td>
                  <td className="py-2 pr-4 capitalize">{c.banco}</td>
                  <td className="py-2 pr-4">{c.archivo_nombre}</td>
                  <td className="py-2 pr-4">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ${ESTADO_ESTILO[c.estado]}`}
                    >
                      {c.estado}
                    </span>
                  </td>
                  <td className="py-2 pr-4 text-right">{c.nuevas}</td>
                  <td className="py-2 pr-4 text-right">{c.duplicadas}</td>
                  <td className="py-2 pr-4 text-right">{c.errores}</td>
                  <td className="py-2 text-right">
                    <button
                      type="button"
                      className="text-xs text-slate-500 underline"
                      onClick={() =>
                        setDetalleId(detalleId === c.id ? null : c.id)
                      }
                    >
                      {detalleId === c.id ? "ocultar" : "detalle"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {detalleId && detalle.data && (
        <section className="rounded-md border border-slate-200 p-4">
          <h3 className="mb-2 text-sm font-semibold">
            Errores de {detalle.data.archivo_nombre}
          </h3>
          {detalle.data.motivo_fallo && (
            <p className="mb-2 text-sm text-red-600">
              {detalle.data.motivo_fallo}
            </p>
          )}
          {(detalle.data.errores_detalle ?? []).length === 0 ? (
            <p className="text-sm text-slate-500">Sin errores de fila.</p>
          ) : (
            <ul className="flex flex-col gap-1 text-sm">
              {(detalle.data.errores_detalle ?? []).map((e) => (
                <li key={`${e.fila}-${e.motivo}`}>
                  <span className="font-mono text-slate-500">
                    {e.fila >= 0 ? `fila ${e.fila}` : "archivo"}
                  </span>{" "}
                  — {e.motivo}
                  {e.valor_crudo && (
                    <span className="font-mono text-slate-500">
                      {" "}
                      · «{e.valor_crudo}»
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {manualAbierto && (
        <ManualDialog
          alCerrar={() => setManualAbierto(false)}
          alCrear={(msg) => {
            setMensaje(msg);
            setManualAbierto(false);
          }}
        />
      )}
    </div>
  );
}

function ManualDialog({
  alCerrar,
  alCrear,
}: {
  alCerrar: () => void;
  alCrear: (mensaje: string) => void;
}) {
  // Una key por APERTURA del formulario: reintentos del mismo submit → replay
  // (no duplica); abrir de nuevo → transacción nueva (§1.12).
  const [idemKey] = useState(() => crypto.randomUUID());
  const [form, setForm] = useState<TransaccionManualInput>({
    fecha: new Date().toISOString().slice(0, 10),
    descripcion: "",
    valor: "",
    tipo_flujo: "egreso",
  });
  const [error, setError] = useState<string | null>(null);

  const crear = useMutation({
    mutationFn: () => crearTransaccionManual(form, idemKey),
    onSuccess: (t) =>
      alCrear(
        `Transacción manual creada (${t.id_banco}) por ${formatCOP(t.valor)}.`,
      ),
    onError: (e) => setError(e instanceof Error ? e.message : "Error creando"),
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!/^\d+(\.\d{1,2})?$/.test(form.valor)) {
      setError("El valor debe ser un monto positivo (ej: 50000 o 50000.50).");
      return;
    }
    crear.mutate();
  }

  return (
    <div className="fixed inset-0 z-10 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-lg">
        <h3 className="mb-4 text-lg font-semibold">Transacción manual</h3>
        <form onSubmit={onSubmit} className="flex flex-col gap-3 text-sm">
          <label className="font-medium" htmlFor="m-fecha">
            Fecha
          </label>
          <input
            id="m-fecha"
            type="date"
            required
            className="rounded-md border border-slate-300 px-3 py-2"
            value={form.fecha}
            onChange={(e) => setForm({ ...form, fecha: e.target.value })}
          />
          <label className="font-medium" htmlFor="m-desc">
            Descripción
          </label>
          <input
            id="m-desc"
            required
            maxLength={300}
            className="rounded-md border border-slate-300 px-3 py-2"
            value={form.descripcion}
            onChange={(e) => setForm({ ...form, descripcion: e.target.value })}
          />
          <label className="font-medium" htmlFor="m-valor">
            Valor (COP)
          </label>
          <input
            id="m-valor"
            required
            inputMode="decimal"
            placeholder="50000"
            className="rounded-md border border-slate-300 px-3 py-2"
            value={form.valor}
            onChange={(e) => setForm({ ...form, valor: e.target.value })}
          />
          <label className="font-medium" htmlFor="m-tipo">
            Tipo
          </label>
          <select
            id="m-tipo"
            className="rounded-md border border-slate-300 px-3 py-2"
            value={form.tipo_flujo}
            onChange={(e) =>
              setForm({
                ...form,
                tipo_flujo: e.target.value as "egreso" | "ingreso",
              })
            }
          >
            <option value="egreso">Egreso (sale plata)</option>
            <option value="ingreso">Ingreso (entra plata)</option>
          </select>
          {error && <p className="text-red-600">{error}</p>}
          <div className="mt-2 flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={alCerrar}>
              Cancelar
            </Button>
            <Button type="submit" disabled={crear.isPending}>
              {crear.isPending ? "Creando…" : "Crear"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
