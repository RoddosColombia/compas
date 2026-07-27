// frontend/src/pages/CargasPage.tsx
//
// Pantalla de cargas (PRD M7 / Spec §1.6): subir extracto (F-22), historial con
// conteos, detalle de errores por fila (regla 7: el texto crudo se muestra al
// Financiero) y registro de transacción manual (US-10) con Idempotency-Key.
// Los montos son strings; formato SOLO con formatCOP (regla 1).

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useRef, useState } from "react";

import { useAuth } from "@/auth/AuthContext";
import { PageHeader } from "@/components/layout/PageHeader";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
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
  completada: "bg-positivo/10 text-positivo",
  procesando: "bg-atencion/10 text-atencion",
  fallida: "bg-critico/10 text-critico",
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

  const acciones = gestor ? (
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
        variant="cyan"
        onClick={() => inputArchivo.current?.click()}
        disabled={subir.isPending}
      >
        {subir.isPending ? "Procesando…" : "Subir extracto"}
      </Button>
      <Button variant="outline" onClick={() => setManualAbierto(true)}>
        Transacción manual
      </Button>
    </div>
  ) : undefined;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        titulo="Cargas"
        descripcion="Sube extractos bancarios y registra transacciones manuales."
        acciones={acciones}
      />

      {mensaje && (
        <output className="block rounded-md border border-hairline bg-surface-muted px-3 py-2 font-sans text-sm text-ink">
          {mensaje}
        </output>
      )}

      {cargas.isLoading && (
        <p className="font-sans text-sm text-ink-soft">Cargando…</p>
      )}
      {cargas.isError && (
        <AlertBanner variant="danger">
          No se pudo listar las cargas.
        </AlertBanner>
      )}

      {cargas.data && cargas.data.items.length === 0 && (
        <p className="font-sans text-sm text-ink-soft">
          Sin cargas todavía. Sube el primer extracto (.xlsx de Bancolombia,
          BBVA o Global66).
        </p>
      )}

      {cargas.data && cargas.data.items.length > 0 && (
        <Card className="overflow-hidden p-0">
          <div className="overflow-x-auto">
            <table className="w-full font-sans text-sm">
              <thead>
                <tr className="border-b border-hairline text-left text-ink-faint">
                  <th className="px-4 py-2.5 font-semibold">Fecha</th>
                  <th className="px-4 py-2.5 font-semibold">Banco</th>
                  <th className="px-4 py-2.5 font-semibold">Archivo</th>
                  <th className="px-4 py-2.5 font-semibold">Estado</th>
                  <th className="px-4 py-2.5 text-right font-semibold">
                    Nuevas
                  </th>
                  <th className="px-4 py-2.5 text-right font-semibold">
                    Duplicadas
                  </th>
                  <th className="px-4 py-2.5 text-right font-semibold">
                    Errores
                  </th>
                  <th className="px-4 py-2.5" />
                </tr>
              </thead>
              <tbody>
                {cargas.data.items.map((c) => (
                  <tr
                    key={c.id}
                    className="border-b border-hairline/60 last:border-0"
                  >
                    <td className="px-4 py-2 whitespace-nowrap text-ink-soft">
                      {formatFecha(c.created_at.slice(0, 10))}
                    </td>
                    <td className="px-4 py-2 text-ink capitalize">{c.banco}</td>
                    <td className="px-4 py-2 text-ink">{c.archivo_nombre}</td>
                    <td className="px-4 py-2">
                      <span
                        className={`rounded-full px-2 py-0.5 font-sans text-apoyo font-medium ${ESTADO_ESTILO[c.estado]}`}
                      >
                        {c.estado}
                      </span>
                    </td>
                    <td className="tabular px-4 py-2 text-right text-ink-soft">
                      {c.nuevas}
                    </td>
                    <td className="tabular px-4 py-2 text-right text-ink-soft">
                      {c.duplicadas}
                    </td>
                    <td className="tabular px-4 py-2 text-right text-ink-soft">
                      {c.errores}
                    </td>
                    <td className="px-4 py-2 text-right">
                      <button
                        type="button"
                        className="font-sans text-apoyo text-cyan underline"
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
        </Card>
      )}

      {detalleId && detalle.data && (
        <Card>
          <h3 className="mb-2 font-display text-sm font-semibold text-ink">
            Errores de {detalle.data.archivo_nombre}
          </h3>
          {detalle.data.motivo_fallo && (
            <div className="mb-2">
              <AlertBanner variant="danger">
                {detalle.data.motivo_fallo}
              </AlertBanner>
            </div>
          )}
          {(detalle.data.errores_detalle ?? []).length === 0 ? (
            <p className="font-sans text-sm text-ink-soft">
              Sin errores de fila.
            </p>
          ) : (
            <ul className="flex flex-col gap-1 font-sans text-sm text-ink">
              {(detalle.data.errores_detalle ?? []).map((e) => (
                <li key={`${e.fila}-${e.motivo}`}>
                  <span className="tabular text-ink-faint">
                    {e.fila >= 0 ? `fila ${e.fila}` : "archivo"}
                  </span>{" "}
                  — {e.motivo}
                  {e.valor_crudo && (
                    <span className="tabular text-ink-faint">
                      {" "}
                      · «{e.valor_crudo}»
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>
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
      <Card className="w-full max-w-md shadow-lg">
        <h3 className="mb-4 font-display text-lg font-semibold text-ink">
          Transacción manual
        </h3>
        <form
          onSubmit={onSubmit}
          className="flex flex-col gap-3 font-sans text-sm"
        >
          <label className="font-medium text-ink" htmlFor="m-fecha">
            Fecha
          </label>
          <input
            id="m-fecha"
            type="date"
            required
            className="rounded-md border border-hairline bg-surface px-3 py-1.5 text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan"
            value={form.fecha}
            onChange={(e) => setForm({ ...form, fecha: e.target.value })}
          />
          <label className="font-medium text-ink" htmlFor="m-desc">
            Descripción
          </label>
          <input
            id="m-desc"
            required
            maxLength={300}
            className="rounded-md border border-hairline bg-surface px-3 py-1.5 text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan"
            value={form.descripcion}
            onChange={(e) => setForm({ ...form, descripcion: e.target.value })}
          />
          <label className="font-medium text-ink" htmlFor="m-valor">
            Valor (COP)
          </label>
          <input
            id="m-valor"
            required
            inputMode="decimal"
            placeholder="50000"
            className="tabular rounded-md border border-hairline bg-surface px-3 py-1.5 text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan"
            value={form.valor}
            onChange={(e) => setForm({ ...form, valor: e.target.value })}
          />
          <label className="font-medium text-ink" htmlFor="m-tipo">
            Tipo
          </label>
          <select
            id="m-tipo"
            className="rounded-md border border-hairline bg-surface px-3 py-1.5 text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan"
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
          {error && <AlertBanner variant="danger">{error}</AlertBanner>}
          <div className="mt-2 flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={alCerrar}>
              Cancelar
            </Button>
            <Button type="submit" variant="cyan" disabled={crear.isPending}>
              {crear.isPending ? "Creando…" : "Crear"}
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}
