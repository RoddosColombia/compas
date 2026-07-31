// frontend/src/components/iva/FacturasTabla.tsx
//
// Tabla de facturas (spec de diseño §4). Filtros en CLIENTE (§4: GET /facturas solo
// filtra por activo; el volumen anual es trivial). Selección múltiple + acción en
// lote de deducibilidad (§2/§3④): el corazón de la pantalla — si hay que decidir
// factura por factura nadie lo hace. Cero aritmética de dinero (regla 1): los montos
// llegan como string del backend; el front solo formatea.
//
// Dos exigencias del CEO cableadas aquí:
//  1. Tras marcar deducibilidad se refresca la LIQUIDACIÓN COMPLETA (no solo la
//     tabla) → `onCambio` = refrescarTodo de IvaPage.
//  2. El lote responde 200 aunque TODOS los ids fallen: el resumen se arma desde
//     `resultados`/`resumen`, con el motivo de cada fallo. Si errores > 0 NO se
//     presenta como éxito.
//
// La confirmación NO calcula el nuevo descontable (sería aritmética de dinero en el
// front, prohibida por la regla 1 y el §5): dice cuántas y la DIRECCIÓN del efecto;
// la cifra exacta la recalcula el backend y aparece en la liquidación al confirmar.

import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { FiltroBarra, type FiltroSelect } from "@/components/ui/filtro-barra";
import {
  type FacturaRow,
  type LoteRespuesta,
  marcarDeducibilidadLote,
} from "@/lib/facturas";
import { formatCOP, formatFecha } from "@/lib/money";
import { cn } from "@/lib/utils";

const ORIGEN_LABEL: Record<string, string> = {
  auteco: "Auteco",
  otra_compra: "Otra compra",
  moto: "Moto",
  repuesto: "Repuesto",
  servicio: "Servicio",
  otro: "Otro",
  sin_clasificar: "sin clasificar",
};

type Filtros = {
  periodo: string;
  tipo: string;
  deducibilidad: string;
  origen: string;
  estado: string;
};

const DEFAULTS: Filtros = {
  periodo: "todos",
  tipo: "todos",
  deducibilidad: "todos",
  origen: "todos",
  estado: "activas",
};

/** Estado de deducibilidad de una compra para el filtro/columna (3 valores). */
function estadoDeducible(f: FacturaRow): "si" | "no" | "sin_decidir" {
  if (!f.deducible_decidido) return "sin_decidir";
  return f.deducible ? "si" : "no";
}

function plural(n: number, uno: string, varios: string): string {
  return `${n} ${n === 1 ? uno : varios}`;
}

function TipoBadge({ tipo }: { tipo: "compra" | "venta" }) {
  // Un solo estilo de badge para tipo y estado (§4/§7).
  return (
    <span className="inline-flex rounded-full border border-hairline bg-surface-muted px-2 py-0.5 font-sans text-apoyo text-ink-soft">
      {tipo === "compra" ? "Recibida" : "Emitida"}
    </span>
  );
}

function DeducibleCelda({ f }: { f: FacturaRow }) {
  // deducible solo aplica a compras (§4): en ventas, celda vacía
  if (f.tipo !== "compra") return null;
  const est = estadoDeducible(f);
  if (est === "si") return <span className="text-ink">Sí</span>;
  if (est === "no") return <span className="text-ink">No</span>;
  // "Sin decidir" cambia la cifra de IVA → token atencion (§4)
  return <span className="font-medium text-atencion">Sin decidir</span>;
}

export function FacturasTabla({
  facturas,
  onCambio,
}: {
  facturas: FacturaRow[];
  /** Refresca la liquidación COMPLETA y la tabla (§2). = refrescarTodo de IvaPage. */
  onCambio: () => void;
}) {
  const [filtros, setFiltros] = useState<Filtros>(DEFAULTS);
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [confirmar, setConfirmar] = useState<boolean | null>(null); // deducible objetivo
  const [aplicando, setAplicando] = useState(false);
  const [resultado, setResultado] = useState<LoteRespuesta | null>(null);

  const set = (parche: Partial<Filtros>) =>
    setFiltros((prev) => ({ ...prev, ...parche }));

  const opcionesPeriodo = useMemo(() => {
    const vistos = Array.from(new Set(facturas.map((f) => f.periodo))).sort();
    return [
      { valor: "todos", label: "Todos" },
      ...vistos.map((p) => ({ valor: p, label: p })),
    ];
  }, [facturas]);

  const opcionesOrigen = useMemo(() => {
    const vistos = Array.from(new Set(facturas.map((f) => f.origen)));
    return [
      { valor: "todos", label: "Todos" },
      ...vistos.map((o) => ({ valor: o, label: ORIGEN_LABEL[o] ?? o })),
    ];
  }, [facturas]);

  const visibles = useMemo(
    () =>
      facturas.filter((f) => {
        if (filtros.periodo !== "todos" && f.periodo !== filtros.periodo)
          return false;
        if (filtros.tipo !== "todos" && f.tipo !== filtros.tipo) return false;
        if (filtros.origen !== "todos" && f.origen !== filtros.origen)
          return false;
        if (filtros.estado === "activas" && !f.activo) return false;
        if (filtros.estado === "anuladas" && f.activo) return false;
        if (filtros.deducibilidad !== "todos") {
          if (f.tipo !== "compra") return false;
          if (estadoDeducible(f) !== filtros.deducibilidad) return false;
        }
        return true;
      }),
    [facturas, filtros],
  );

  // solo las compras activas visibles se pueden marcar (deducible no aplica a ventas)
  const seleccionables = useMemo(
    () => visibles.filter((f) => f.tipo === "compra" && f.activo),
    [visibles],
  );

  const barra: FiltroSelect[] = [
    {
      id: "periodo",
      label: "Período",
      opciones: opcionesPeriodo,
      valor: filtros.periodo,
      porDefecto: DEFAULTS.periodo,
      onChange: (v) => set({ periodo: v }),
    },
    {
      id: "tipo",
      label: "Tipo",
      opciones: [
        { valor: "todos", label: "Todos" },
        { valor: "compra", label: "Recibida" },
        { valor: "venta", label: "Emitida" },
      ],
      valor: filtros.tipo,
      porDefecto: DEFAULTS.tipo,
      onChange: (v) => set({ tipo: v }),
    },
    {
      id: "deducibilidad",
      label: "Deducibilidad",
      opciones: [
        { valor: "todos", label: "Todas" },
        { valor: "si", label: "Sí" },
        { valor: "no", label: "No" },
        { valor: "sin_decidir", label: "Sin decidir" },
      ],
      valor: filtros.deducibilidad,
      porDefecto: DEFAULTS.deducibilidad,
      onChange: (v) => set({ deducibilidad: v }),
    },
    {
      id: "origen",
      label: "Origen",
      opciones: opcionesOrigen,
      valor: filtros.origen,
      porDefecto: DEFAULTS.origen,
      onChange: (v) => set({ origen: v }),
    },
    {
      id: "estado",
      label: "Estado",
      opciones: [
        { valor: "activas", label: "Activas" },
        { valor: "anuladas", label: "Anuladas" },
        { valor: "todos", label: "Todas" },
      ],
      valor: filtros.estado,
      porDefecto: DEFAULTS.estado,
      onChange: (v) => set({ estado: v }),
    },
  ];

  const alternar = (id: string) =>
    setSel((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });

  const todasSel =
    seleccionables.length > 0 && seleccionables.every((f) => sel.has(f.id));
  const alternarTodas = () =>
    setSel(todasSel ? new Set() : new Set(seleccionables.map((f) => f.id)));

  async function aplicarLote(deducible: boolean) {
    setAplicando(true);
    try {
      const resp = await marcarDeducibilidadLote([...sel], deducible);
      setResultado(resp);
      setSel(new Set());
      onCambio(); // §2: recalcula titular + desglose + "qué exige atención" + tabla
    } finally {
      setAplicando(false);
      setConfirmar(null);
    }
  }

  const nSel = sel.size;

  return (
    <Card className="flex flex-col gap-4">
      <FiltroBarra filtros={barra} />

      {/* Resumen del último lote — honesto: nunca "éxito" si hubo errores (§2). */}
      {resultado && (
        <ResumenLote
          resultado={resultado}
          onCerrar={() => setResultado(null)}
        />
      )}

      {/* Barra de acción en lote — aparece con selección */}
      {nSel > 0 && (
        <div className="flex flex-wrap items-center gap-3 rounded-lg bg-surface-muted px-3 py-2">
          <span className="font-sans text-cuerpo text-ink-soft">
            {plural(nSel, "seleccionada", "seleccionadas")}
          </span>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setConfirmar(true)}
            >
              Marcar como deducibles
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setConfirmar(false)}
            >
              Marcar como no deducibles
            </Button>
          </div>
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full border-collapse font-sans text-cuerpo">
          <thead>
            <tr className="border-hairline border-b text-ink-soft">
              <th className="w-8 px-2 py-2">
                <input
                  type="checkbox"
                  aria-label="Seleccionar todas"
                  checked={todasSel}
                  onChange={alternarTodas}
                  disabled={seleccionables.length === 0}
                />
              </th>
              <th className="px-2 py-2 text-left font-medium">Fecha</th>
              <th className="px-2 py-2 text-left font-medium">Tipo</th>
              <th className="px-2 py-2 text-left font-medium">Contraparte</th>
              <th className="px-2 py-2 text-left font-medium">Número</th>
              <th className="px-2 py-2 text-left font-medium">Origen</th>
              <th className="px-2 py-2 text-right font-medium">Total bruto</th>
              <th className="px-2 py-2 text-right font-medium">IVA</th>
              <th className="px-2 py-2 text-left font-medium">Deducible</th>
              <th className="px-2 py-2 text-left font-medium">Estado</th>
            </tr>
          </thead>
          <tbody>
            {visibles.map((f) => {
              const puede = f.tipo === "compra" && f.activo;
              return (
                <tr
                  key={f.id}
                  className={cn(
                    "border-hairline/60 border-b",
                    !f.activo && "text-ink-faint line-through",
                  )}
                >
                  <td className="px-2 py-2 align-middle">
                    {puede && (
                      <input
                        type="checkbox"
                        aria-label={`Seleccionar ${f.numero}`}
                        checked={sel.has(f.id)}
                        onChange={() => alternar(f.id)}
                      />
                    )}
                  </td>
                  <td className="whitespace-nowrap px-2 py-2 text-ink-soft">
                    {formatFecha(f.fecha)}
                  </td>
                  <td className="px-2 py-2">
                    <TipoBadge tipo={f.tipo} />
                  </td>
                  <td className="px-2 py-2">
                    {f.tercero_nombre ?? (
                      <span
                        className="text-ink-faint italic"
                        title="Dato personal restringido a los roles autorizados."
                      >
                        Reservado
                      </span>
                    )}
                  </td>
                  <td className="px-2 py-2 font-mono text-apoyo text-ink-soft">
                    {f.numero}
                  </td>
                  <td className="px-2 py-2">
                    {f.origen === "sin_clasificar" ? (
                      <span className="text-atencion">sin clasificar</span>
                    ) : (
                      (ORIGEN_LABEL[f.origen] ?? f.origen)
                    )}
                  </td>
                  <td className="px-2 py-2 text-right tabular-nums">
                    {f.total_bruto === null ? (
                      <span
                        className="text-ink-faint"
                        title="La representación gráfica de la DIAN no trae la base gravada; trae el total bruto."
                      >
                        —
                      </span>
                    ) : (
                      formatCOP(f.total_bruto)
                    )}
                  </td>
                  <td className="px-2 py-2 text-right text-cifra-sm tabular-nums">
                    {formatCOP(f.iva_valor)}
                  </td>
                  <td className="px-2 py-2">
                    <DeducibleCelda f={f} />
                  </td>
                  <td className="px-2 py-2 text-ink-faint">
                    {f.activo ? "" : "Anulada"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {visibles.length === 0 && (
          <p className="px-2 py-6 text-center font-sans text-cuerpo text-ink-soft">
            Ninguna factura coincide con los filtros.
          </p>
        )}
      </div>

      {confirmar !== null && (
        <ConfirmarLote
          deducible={confirmar}
          n={nSel}
          aplicando={aplicando}
          onConfirmar={() => void aplicarLote(confirmar)}
          onCancelar={() => setConfirmar(null)}
        />
      )}
    </Card>
  );
}

function ResumenLote({
  resultado,
  onCerrar,
}: {
  resultado: LoteRespuesta;
  onCerrar: () => void;
}) {
  const { actualizadas, sin_cambio, errores } = resultado.resumen;
  const hayError = errores > 0;
  const fallidas = resultado.resultados.filter((r) => r.estado === "error");
  const partes = [plural(actualizadas, "marcada", "marcadas")];
  if (sin_cambio > 0) partes.push(`${sin_cambio} sin cambio`);
  if (hayError) partes.push(`${errores} con error`);

  return (
    <div
      className={cn(
        "flex flex-col gap-1 rounded-lg px-3 py-2",
        hayError ? "bg-atencion-tint" : "bg-positivo-tint",
      )}
    >
      <div className="flex items-center justify-between">
        <span
          className={cn(
            "font-sans text-cuerpo font-medium",
            hayError ? "text-atencion" : "text-positivo",
          )}
        >
          {partes.join(" · ")}
        </span>
        <button
          type="button"
          onClick={onCerrar}
          className="font-sans text-apoyo text-ink-faint hover:text-ink"
        >
          Cerrar
        </button>
      </div>
      {fallidas.length > 0 && (
        <ul className="list-disc pl-5 font-sans text-apoyo text-ink-soft">
          {fallidas.map((r) => (
            <li key={r.id}>{r.motivo ?? "error"}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ConfirmarLote({
  deducible,
  n,
  aplicando,
  onConfirmar,
  onCancelar,
}: {
  deducible: boolean;
  n: number;
  aplicando: boolean;
  onConfirmar: () => void;
  onCancelar: () => void;
}) {
  return (
    <dialog
      open
      aria-modal="true"
      className="fixed inset-0 z-50 m-0 flex h-full max-h-none w-full max-w-none items-center justify-center bg-ink/30 p-4"
    >
      <Card className="flex max-w-md flex-col gap-4">
        <p className="font-display text-cifra-sm font-semibold text-ink">
          {deducible
            ? `Marcar ${plural(n, "factura", "facturas")} como deducibles`
            : `Marcar ${plural(n, "factura", "facturas")} como no deducibles`}
        </p>
        <p className="font-sans text-cuerpo text-ink-soft">
          {deducible
            ? "El IVA descontable del período subirá y el neto a pagar bajará. "
            : "El IVA descontable del período bajará y el neto a pagar subirá. "}
          La cifra exacta se recalcula al confirmar.
        </p>
        <div className="flex justify-end gap-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onCancelar}
            disabled={aplicando}
          >
            Cancelar
          </Button>
          <Button
            type="button"
            variant="cyan"
            size="sm"
            onClick={onConfirmar}
            disabled={aplicando}
          >
            {aplicando ? "Aplicando…" : "Confirmar"}
          </Button>
        </div>
      </Card>
    </dialog>
  );
}
