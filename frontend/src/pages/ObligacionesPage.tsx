// frontend/src/pages/ObligacionesPage.tsx
//
// Obligaciones / Auteco (D2 §7): lista de obligaciones (Auteco primero) con su saldo
// pendiente (= cartera) y sus facturas (numero · fecha · valor · plazo · mes de pago
// derivado · estado · origen del pago). Registrar factura, registrar pago con origen
// (roddos | tercero — tercero baja la deuda sin salir de caja) y anular factura. CRUD
// gated por proyeccion:gestionar (regla 9: el backend autoriza; el front solo esconde
// controles). Montos string (regla 1). Con esta página cada factura y cada pago se
// registran aquí y la proyección sigue precisa mes a mes, sin migraciones.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, type ReactNode, useState } from "react";

import { useAuth } from "@/auth/AuthContext";
import { PageHeader } from "@/components/layout/PageHeader";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { Cargando } from "@/components/ui/cargando";
import { ErrorEstado } from "@/components/ui/error-estado";
import { formatCOP } from "@/lib/money";
import {
  type FacturaObligacion,
  type Obligacion,
  type OrigenPago,
  type SimulacionNegociacion,
  anularFactura,
  anularPago,
  listarFacturas,
  listarObligaciones,
  mesDePago,
  registrarFactura,
  registrarPago,
  simularNegociacion,
} from "@/lib/obligaciones";

const RE_MONTO = /^\d+(\.\d{1,2})?$/;
const RE_FECHA = /^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$/;

export default function ObligacionesPage() {
  const { puede } = useAuth();
  const gestiona = puede("proyeccion:gestionar");

  const obligaciones = useQuery({
    queryKey: ["obligaciones"],
    queryFn: listarObligaciones,
  });

  if (obligaciones.isLoading) return <Cargando variante="card" />;
  if (obligaciones.isError) {
    return (
      <ErrorEstado
        mensaje="No se pudieron cargar las obligaciones."
        onReintentar={() => void obligaciones.refetch()}
      />
    );
  }

  // Auteco / facturación primero (es donde vive la cartera con pagos); luego el resto.
  const items = [...(obligaciones.data?.items ?? [])].sort((a, b) => {
    if (a.naturaleza !== b.naturaleza)
      return a.naturaleza === "facturacion" ? -1 : 1;
    return a.nombre.localeCompare(b.nombre);
  });

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        titulo="Obligaciones"
        descripcion="Deudas y cuentas por pagar. En facturación (Auteco) se registra cada factura y cada pago; la proyección de caja se actualiza sola."
      />
      {items.length === 0 ? (
        <Card>
          <p className="font-sans text-cuerpo text-ink-soft">
            No hay obligaciones activas.
          </p>
        </Card>
      ) : (
        items.map((o) => (
          <ObligacionCard key={o.id} obligacion={o} gestiona={gestiona} />
        ))
      )}
    </div>
  );
}

function ObligacionCard({
  obligacion,
  gestiona,
}: {
  obligacion: Obligacion;
  gestiona: boolean;
}) {
  const qc = useQueryClient();
  const esFacturacion = obligacion.naturaleza === "facturacion";
  const facturas = useQuery({
    queryKey: ["obligacion-facturas", obligacion.id],
    queryFn: () => listarFacturas(obligacion.id),
    enabled: esFacturacion,
  });

  const [nuevaFactura, setNuevaFactura] = useState(false);
  const [pagoDe, setPagoDe] = useState<FacturaObligacion | null>(null);
  const [anular, setAnular] = useState<FacturaObligacion | null>(null);
  // RF-F8 · «negocia esta deuda» (compute-only, sin persistir).
  const [negociar, setNegociar] = useState<FacturaObligacion | null>(null);

  const invalidar = () => {
    void qc.invalidateQueries({
      queryKey: ["obligacion-facturas", obligacion.id],
    });
    void qc.invalidateQueries({ queryKey: ["obligaciones"] });
    // la proyección depende de las facturas activas / pagos → refrescarla también
    void qc.invalidateQueries({ queryKey: ["proyeccion"] });
  };

  const anularPagoMut = useMutation({
    mutationFn: (f: FacturaObligacion) => anularPago(obligacion.id, f.id),
    onSuccess: invalidar,
  });
  const anularFacturaMut = useMutation({
    mutationFn: (f: FacturaObligacion) => anularFactura(f.id),
    onSuccess: () => {
      setAnular(null);
      invalidar();
    },
  });

  const lista = facturas.data?.items ?? [];

  return (
    <Card
      className="flex flex-col gap-3 p-0"
      data-testid={`obligacion-${obligacion.id}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3 px-5 pt-5">
        <div className="flex flex-col gap-0.5">
          <CardTitle>{obligacion.nombre}</CardTitle>
          <span className="font-sans text-apoyo text-ink-faint">
            {obligacion.acreedor}
            {obligacion.es_sistema && " · sistema"}
          </span>
        </div>
        <div className="flex items-center gap-4">
          {esFacturacion && (
            <div className="flex flex-col items-end gap-0.5">
              <span className="font-sans text-apoyo text-ink-faint">
                Saldo pendiente
              </span>
              <span className="tabular font-display text-xl font-semibold text-ink">
                {obligacion.saldo_pendiente !== null
                  ? formatCOP(obligacion.saldo_pendiente)
                  : "—"}
              </span>
            </div>
          )}
          {esFacturacion && gestiona && (
            <Button
              variant="cyan"
              size="sm"
              onClick={() => setNuevaFactura(true)}
            >
              Registrar factura
            </Button>
          )}
        </div>
      </div>

      {!esFacturacion ? (
        <p className="px-5 pb-5 font-sans text-sm text-ink-soft">
          Obligación por cuotas (calendario fijo). Las facturas y pagos se
          registran solo en obligaciones de facturación.
        </p>
      ) : facturas.isLoading ? (
        <div className="px-5 pb-5">
          <Cargando variante="tabla" />
        </div>
      ) : lista.length === 0 ? (
        <p className="px-5 pb-5 font-sans text-sm text-ink-soft">
          Sin facturas registradas.
        </p>
      ) : (
        <TablaFacturas
          facturas={lista}
          gestiona={gestiona}
          onPagar={setPagoDe}
          onAnularPago={(f) => anularPagoMut.mutate(f)}
          onAnular={setAnular}
          onNegociar={setNegociar}
          obligacion={obligacion}
        />
      )}

      {nuevaFactura && (
        <FacturaDialog
          onGuardar={async (input) => {
            await registrarFactura(obligacion.id, input);
            setNuevaFactura(false);
            invalidar();
          }}
          onCerrar={() => setNuevaFactura(false)}
        />
      )}

      {pagoDe && (
        <PagoDialog
          factura={pagoDe}
          onGuardar={async (input) => {
            await registrarPago(obligacion.id, pagoDe.id, input);
            setPagoDe(null);
            invalidar();
          }}
          onCerrar={() => setPagoDe(null)}
        />
      )}

      {negociar && (
        <NegociarDialog
          factura={negociar}
          obligacion={obligacion}
          onCerrar={() => setNegociar(null)}
        />
      )}

      {anular && (
        <ConfirmarAnular
          factura={anular}
          pendiente={anularFacturaMut.isPending}
          error={
            anularFacturaMut.isError
              ? (anularFacturaMut.error as Error).message
              : null
          }
          onConfirmar={() => anularFacturaMut.mutate(anular)}
          onCerrar={() => setAnular(null)}
        />
      )}
    </Card>
  );
}

function TablaFacturas({
  facturas,
  gestiona,
  onPagar,
  onAnularPago,
  onAnular,
  onNegociar,
  obligacion,
}: {
  facturas: FacturaObligacion[];
  gestiona: boolean;
  onPagar: (f: FacturaObligacion) => void;
  onAnularPago: (f: FacturaObligacion) => void;
  onAnular: (f: FacturaObligacion) => void;
  // RF-F8 · «simular negociación» (compute-only). Solo se ofrece cuando la
  // obligación tiene rango de plazo real (plazo_max > plazo_base): sin rango,
  // no hay nada para negociar.
  onNegociar: (f: FacturaObligacion) => void;
  obligacion: Obligacion;
}) {
  const puedeNegociar =
    typeof obligacion.plazo_max_dias === "number" &&
    typeof obligacion.plazo_base_dias === "number" &&
    obligacion.plazo_max_dias > obligacion.plazo_base_dias;
  return (
    <div className="overflow-x-auto">
      <table className="w-full font-sans text-sm">
        <thead>
          <tr className="border-b border-hairline text-left text-ink-faint">
            <th className="px-5 py-2.5 font-semibold">Número</th>
            <th className="px-5 py-2.5 font-semibold">Fecha</th>
            <th className="px-5 py-2.5 text-right font-semibold">Valor</th>
            <th className="px-5 py-2.5 text-right font-semibold">Plazo</th>
            <th className="px-5 py-2.5 font-semibold">Mes de pago</th>
            <th className="px-5 py-2.5 font-semibold">Estado</th>
            {gestiona && (
              <th className="px-5 py-2.5 text-right font-semibold">
                <span className="sr-only">Acciones</span>
              </th>
            )}
          </tr>
        </thead>
        <tbody>
          {facturas.map((f) => (
            <tr
              key={f.id}
              className="border-b border-hairline/60 last:border-0"
              data-testid={`factura-${f.id}`}
            >
              <td className="px-5 py-2 font-medium text-ink">
                {f.numero ?? "—"}
              </td>
              <td className="px-5 py-2 text-ink-soft">{f.fecha_factura}</td>
              <td className="tabular px-5 py-2 text-right text-ink-soft">
                {formatCOP(f.valor)}
              </td>
              <td className="tabular px-5 py-2 text-right text-ink-soft">
                {f.plazo_elegido_dias}d
              </td>
              <td className="px-5 py-2 text-ink-soft">
                {mesDePago(f.fecha_factura, f.plazo_elegido_dias)}
              </td>
              <td className="px-5 py-2">
                <EstadoBadge factura={f} />
              </td>
              {gestiona && (
                <td className="px-5 py-2 text-right whitespace-nowrap">
                  {f.estado === "pendiente" ? (
                    <>
                      <button
                        type="button"
                        className="font-medium text-cyan hover:underline"
                        onClick={() => onPagar(f)}
                      >
                        Registrar pago
                      </button>
                      {puedeNegociar && (
                        <button
                          type="button"
                          className="ml-3 font-medium text-ink-soft hover:underline"
                          onClick={() => onNegociar(f)}
                          title="Simula el impacto de cambiar plazo o fecha (no persiste)"
                        >
                          Simular negociación
                        </button>
                      )}
                      <button
                        type="button"
                        className="ml-3 font-medium text-critico hover:underline"
                        onClick={() => onAnular(f)}
                      >
                        Anular
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      className="font-medium text-ink-soft hover:underline"
                      onClick={() => onAnularPago(f)}
                    >
                      Anular pago
                    </button>
                  )}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function EstadoBadge({ factura }: { factura: FacturaObligacion }) {
  if (factura.estado === "pendiente") {
    return (
      <span className="rounded-full bg-surface-muted px-2 py-0.5 text-apoyo font-medium text-ink-soft">
        Pendiente
      </span>
    );
  }
  const tercero = factura.pagada_desde === "tercero";
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-apoyo font-medium ${
        tercero ? "bg-cyan/15 text-cyan" : "bg-positivo/15 text-positivo"
      }`}
    >
      Pagada · {tercero ? "tercero" : "RODDOS"}
    </span>
  );
}

function FacturaDialog({
  onGuardar,
  onCerrar,
}: {
  onGuardar: (input: {
    numero?: string;
    fecha_factura: string;
    valor: string;
    plazo_elegido_dias: number;
    nota?: string;
  }) => Promise<void>;
  onCerrar: () => void;
}) {
  const [numero, setNumero] = useState("");
  const [fecha, setFecha] = useState("");
  const [valor, setValor] = useState("");
  const [plazo, setPlazo] = useState("150");
  const [nota, setNota] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pendiente, setPendiente] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!RE_FECHA.test(fecha)) {
      setError("La fecha de la factura usa año-mes-día (ej: 2026-08-15).");
      return;
    }
    if (!RE_MONTO.test(valor.trim())) {
      setError("El valor debe ser un número positivo (COP).");
      return;
    }
    const plazoN = Number.parseInt(plazo, 10);
    if (!Number.isFinite(plazoN) || plazoN < 0) {
      setError("El plazo (días) debe ser un entero ≥ 0.");
      return;
    }
    setPendiente(true);
    try {
      await onGuardar({
        numero: numero.trim() || undefined,
        fecha_factura: fecha,
        valor: valor.trim(),
        plazo_elegido_dias: plazoN,
        nota: nota.trim() || undefined,
      });
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "No se pudo registrar la factura",
      );
      setPendiente(false);
    }
  }

  return (
    <DialogShell
      titulo="Registrar factura"
      onSubmit={onSubmit}
      onCerrar={onCerrar}
      pendiente={pendiente}
    >
      <Campo etiqueta="Número (opcional)">
        <input
          className={inputCls}
          placeholder="E670165520"
          value={numero}
          onChange={(e) => setNumero(e.target.value)}
        />
      </Campo>
      <Campo etiqueta="Fecha de la factura">
        <input
          type="date"
          required
          className={inputCls}
          value={fecha}
          onChange={(e) => setFecha(e.target.value)}
        />
      </Campo>
      <Campo etiqueta="Valor (COP)">
        <input
          inputMode="decimal"
          placeholder="149030808"
          className={`${inputCls} tabular text-right`}
          value={valor}
          onChange={(e) => setValor(e.target.value)}
        />
      </Campo>
      <Campo etiqueta="Plazo (días)">
        <input
          inputMode="numeric"
          className={`${inputCls} tabular text-right`}
          value={plazo}
          onChange={(e) => setPlazo(e.target.value)}
        />
      </Campo>
      <Campo etiqueta="Nota (opcional)">
        <input
          className={inputCls}
          placeholder="22 Raider"
          value={nota}
          onChange={(e) => setNota(e.target.value)}
        />
      </Campo>
      {error && <AlertBanner variant="danger">{error}</AlertBanner>}
    </DialogShell>
  );
}

function PagoDialog({
  factura,
  onGuardar,
  onCerrar,
}: {
  factura: FacturaObligacion;
  onGuardar: (input: {
    fecha: string;
    valor: string;
    pagada_desde: OrigenPago;
    nota?: string;
  }) => Promise<void>;
  onCerrar: () => void;
}) {
  const [fecha, setFecha] = useState("");
  const [valor, setValor] = useState(factura.valor);
  const [origen, setOrigen] = useState<OrigenPago>("roddos");
  const [nota, setNota] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pendiente, setPendiente] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!RE_FECHA.test(fecha)) {
      setError("La fecha del pago usa año-mes-día (ej: 2026-08-15).");
      return;
    }
    if (!RE_MONTO.test(valor.trim())) {
      setError("El valor del pago debe ser un número positivo (COP).");
      return;
    }
    setPendiente(true);
    try {
      await onGuardar({
        fecha,
        valor: valor.trim(),
        pagada_desde: origen,
        nota: nota.trim() || undefined,
      });
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "No se pudo registrar el pago",
      );
      setPendiente(false);
    }
  }

  return (
    <DialogShell
      titulo={`Registrar pago · ${factura.numero ?? factura.fecha_factura}`}
      onSubmit={onSubmit}
      onCerrar={onCerrar}
      pendiente={pendiente}
    >
      <Campo etiqueta="Fecha del pago">
        <input
          type="date"
          required
          className={inputCls}
          value={fecha}
          onChange={(e) => setFecha(e.target.value)}
        />
      </Campo>
      <Campo etiqueta="Valor pagado (COP)">
        <input
          inputMode="decimal"
          className={`${inputCls} tabular text-right`}
          value={valor}
          onChange={(e) => setValor(e.target.value)}
        />
      </Campo>
      <fieldset className="flex flex-col gap-1.5">
        <legend className="font-medium text-ink">Origen del pago</legend>
        <label className="flex items-start gap-2">
          <input
            type="radio"
            name="origen"
            checked={origen === "roddos"}
            onChange={() => setOrigen("roddos")}
          />
          <span className="text-ink-soft">
            <span className="font-medium text-ink">RODDOS</span> — sale de la
            caja de RODDOS.
          </span>
        </label>
        <label className="flex items-start gap-2">
          <input
            type="radio"
            name="origen"
            checked={origen === "tercero"}
            onChange={() => setOrigen("tercero")}
          />
          <span className="text-ink-soft">
            <span className="font-medium text-ink">Tercero</span> — baja la
            deuda sin salir de la caja de RODDOS.
          </span>
        </label>
      </fieldset>
      <Campo etiqueta="Nota (opcional)">
        <input
          className={inputCls}
          placeholder="pago de Fabián"
          value={nota}
          onChange={(e) => setNota(e.target.value)}
        />
      </Campo>
      {error && <AlertBanner variant="danger">{error}</AlertBanner>}
    </DialogShell>
  );
}

function ConfirmarAnular({
  factura,
  pendiente,
  error,
  onConfirmar,
  onCerrar,
}: {
  factura: FacturaObligacion;
  pendiente: boolean;
  error: string | null;
  onConfirmar: () => void;
  onCerrar: () => void;
}) {
  return (
    <div className="fixed inset-0 z-20 flex items-center justify-center bg-black/40 p-4">
      <dialog
        open
        aria-label="Anular factura"
        className="static w-full max-w-sm rounded-lg border border-hairline bg-surface p-6 text-inherit shadow-lg"
      >
        <h3 className="mb-2 font-display text-lg font-semibold text-ink">
          Anular factura {factura.numero ?? factura.fecha_factura}
        </h3>
        <p className="mb-4 font-sans text-sm text-ink-soft">
          La factura ({formatCOP(factura.valor)}) se dará de baja y saldrá de la
          proyección. Es reversible registrándola de nuevo.
        </p>
        {error && (
          <AlertBanner variant="danger">
            <span className="text-sm">{error}</span>
          </AlertBanner>
        )}
        <div className="mt-4 flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onCerrar}>
            Cancelar
          </Button>
          <Button
            type="button"
            variant="outline"
            className="border-critico/40 text-critico hover:bg-critico/10"
            disabled={pendiente}
            onClick={onConfirmar}
          >
            {pendiente ? "Anulando…" : "Anular"}
          </Button>
        </div>
      </dialog>
    </div>
  );
}

const inputCls =
  "rounded-md border border-hairline bg-surface px-3 py-1.5 text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan";

function Campo({
  etiqueta,
  children,
}: {
  etiqueta: string;
  children: ReactNode;
}) {
  return (
    // biome-ignore lint/a11y/noLabelWithoutControl: el input se pasa como children (anidado dentro del label → asociación implícita, que getByLabelText usa); biome no lo ve estáticamente.
    <label className="flex flex-col gap-1">
      <span className="font-medium text-ink">{etiqueta}</span>
      {children}
    </label>
  );
}

// RF-F8 · Fundacional §2 — «negocia esta deuda» (simulación compute-only).
// Muestra el impacto que TENDRÍA la renegociación en el piso de caja y en los
// valles ANTES de decidir hacerla (persistir es CR-RF-F8-B; ese endpoint aún
// no existe: aquí solo se lee la simulación).
function NegociarDialog({
  factura,
  obligacion,
  onCerrar,
}: {
  factura: FacturaObligacion;
  obligacion: Obligacion;
  onCerrar: () => void;
}) {
  const [plazo, setPlazo] = useState<string>(String(factura.plazo_elegido_dias));
  const [fecha, setFecha] = useState<string>(factura.fecha_factura);
  const [sim, setSim] = useState<SimulacionNegociacion | null>(null);
  const [error, setError] = useState<string | null>(null);

  const plazoBase = obligacion.plazo_base_dias ?? 0;
  const plazoMax = obligacion.plazo_max_dias ?? 0;

  const mut = useMutation({
    mutationFn: async () => {
      const plazoNum = Number.parseInt(plazo, 10);
      const cambiaPlazo = plazoNum !== factura.plazo_elegido_dias;
      const cambiaFecha = fecha !== factura.fecha_factura;
      if (!cambiaPlazo && !cambiaFecha) {
        throw new Error("cambia el plazo o la fecha para simular");
      }
      return simularNegociacion(obligacion.id, factura.id, {
        plazo_elegido_dias_nuevo: cambiaPlazo ? plazoNum : undefined,
        fecha_factura_nueva: cambiaFecha ? fecha : undefined,
      });
    },
    onSuccess: (r) => {
      setSim(r);
      setError(null);
    },
    onError: (e) => {
      setError(e instanceof Error ? e.message : "no se pudo simular");
      setSim(null);
    },
  });

  const deltaPositivo = sim ? Number(sim.delta_piso) > 0 : false;
  const deltaNegativo = sim ? Number(sim.delta_piso) < 0 : false;

  return (
    <div className="fixed inset-0 z-20 flex items-center justify-center bg-black/40 p-4">
      <dialog
        open
        aria-label={`Simular negociación de factura ${factura.numero ?? factura.id}`}
        className="static w-full max-w-lg rounded-lg border border-hairline bg-surface p-6 text-inherit shadow-lg"
      >
        <h3 className="mb-1 font-display text-lg font-semibold text-ink">
          Simular negociación
        </h3>
        <p className="mb-4 font-sans text-apoyo text-ink-faint">
          El cambio NO se guarda. Solo ves qué pasaría con el piso de caja.
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            mut.mutate();
          }}
          className="flex flex-col gap-3 font-sans text-sm"
        >
          <Campo etiqueta={`Plazo nuevo (rango ${plazoBase}–${plazoMax} días)`}>
            <input
              type="number"
              min={plazoBase}
              max={plazoMax}
              value={plazo}
              onChange={(e) => setPlazo(e.target.value)}
              className={inputCls}
              required
            />
          </Campo>
          <Campo etiqueta="Fecha de factura (YYYY-MM-DD)">
            <input
              type="date"
              value={fecha}
              onChange={(e) => setFecha(e.target.value)}
              className={inputCls}
              required
            />
          </Campo>
          {error && <AlertBanner variant="danger">{error}</AlertBanner>}
          {sim && (
            <div className="rounded-md border border-hairline bg-surface-muted/50 p-3">
              <p className="mb-2 font-sans text-apoyo text-ink-faint">
                Mes de pago: {sim.mes_pago_actual} → {sim.mes_pago_negociado}
              </p>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-1 font-sans text-sm">
                <dt className="text-ink-soft">Piso actual</dt>
                <dd className="tabular text-right text-ink">
                  {formatCOP(sim.piso_actual)}
                </dd>
                <dt className="text-ink-soft">Piso negociado</dt>
                <dd className="tabular text-right text-ink">
                  {formatCOP(sim.piso_negociado)}
                </dd>
                <dt className="font-semibold text-ink">Delta piso</dt>
                <dd
                  className={`tabular text-right font-semibold ${
                    deltaPositivo
                      ? "text-positivo"
                      : deltaNegativo
                        ? "text-critico"
                        : "text-ink"
                  }`}
                >
                  {deltaPositivo ? "+" : ""}
                  {formatCOP(sim.delta_piso)}
                </dd>
              </dl>
              <p className="mt-2 font-sans text-apoyo text-ink-faint">
                {deltaPositivo
                  ? "Negociar mejora el piso de caja."
                  : deltaNegativo
                    ? "Negociar empeora el piso de caja."
                    : "No hay cambio en el piso."}
              </p>
            </div>
          )}
          <div className="mt-2 flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onCerrar}>
              Cerrar
            </Button>
            <Button type="submit" variant="cyan" disabled={mut.isPending}>
              {mut.isPending ? "Simulando…" : "Simular"}
            </Button>
          </div>
        </form>
      </dialog>
    </div>
  );
}

function DialogShell({
  titulo,
  children,
  onSubmit,
  onCerrar,
  pendiente,
}: {
  titulo: string;
  children: ReactNode;
  onSubmit: (e: FormEvent) => void;
  onCerrar: () => void;
  pendiente: boolean;
}) {
  return (
    <div className="fixed inset-0 z-20 flex items-center justify-center bg-black/40 p-4">
      <dialog
        open
        aria-label={titulo}
        className="static w-full max-w-md rounded-lg border border-hairline bg-surface p-6 text-inherit shadow-lg"
      >
        <h3 className="mb-4 font-display text-lg font-semibold text-ink">
          {titulo}
        </h3>
        <form
          onSubmit={onSubmit}
          className="flex flex-col gap-3 font-sans text-sm"
        >
          {children}
          <div className="mt-2 flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onCerrar}>
              Cancelar
            </Button>
            <Button type="submit" variant="cyan" disabled={pendiente}>
              {pendiente ? "Guardando…" : "Guardar"}
            </Button>
          </div>
        </form>
      </dialog>
    </div>
  );
}
