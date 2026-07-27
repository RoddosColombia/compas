// FiltroBarra — F1 §5.4, formalizado en F1.1 §9 con sus consumidores reales
// (Proyecciones, Control, Flujo diario). Vive SIEMPRE en `acciones` del
// PageHeader: estado visible, y "Limpiar" cuando algún filtro difiere de su
// default. Opciones de horizonte consistentes en todo el producto.

import { Button } from "@/components/ui/button";

export interface OpcionFiltro {
  valor: string;
  label: string;
}

export interface FiltroSelect {
  id: string;
  label: string;
  opciones: OpcionFiltro[];
  valor: string;
  porDefecto: string;
  onChange: (valor: string) => void;
}

/** Opciones de horizonte del producto (§9): 18 m default · 3 años · 5 años · todo. */
export const OPCIONES_HORIZONTE: OpcionFiltro[] = [
  { valor: "18", label: "18 meses" },
  { valor: "36", label: "3 años" },
  { valor: "60", label: "5 años" },
  { valor: "180", label: "todo (15 años)" },
];

export const HORIZONTE_DEFAULT = "18";

export function FiltroBarra({ filtros }: { filtros: FiltroSelect[] }) {
  const sucio = filtros.some((f) => f.valor !== f.porDefecto);
  return (
    <div className="flex flex-wrap items-center gap-3">
      {filtros.map((f) => (
        <label
          key={f.id}
          className="flex items-center gap-2 font-sans text-cuerpo"
        >
          <span className="text-ink-soft">{f.label}</span>
          <select
            className="rounded-md border border-hairline bg-surface px-3 py-1.5 text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan"
            value={f.valor}
            onChange={(e) => f.onChange(e.target.value)}
          >
            {f.opciones.map((o) => (
              <option key={o.valor} value={o.valor}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
      ))}
      {sucio && (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => {
            for (const f of filtros) {
              if (f.valor !== f.porDefecto) f.onChange(f.porDefecto);
            }
          }}
        >
          Limpiar
        </Button>
      )}
    </div>
  );
}
