// components/proyeccion/MarcaOrigen.tsx
//
// E1·P6 — marca de ORIGEN de la cifra (Real · En curso · Presupuesto · Proyección ·
// Revisar carga). Dimensión distinta de la salud de caja (EstadoMes). Presentación
// pura: una verdad para la tabla y la leyenda del gráfico. Un mes sin marca del backend
// es "Proyección".

import type { MarcaOrigen as Marca } from "@/lib/proyeccion";
import { cn } from "@/lib/utils";

type Clave = Marca | "proyeccion";

export const MARCA_LABEL: Record<Clave, string> = {
  cerrado: "Real",
  en_ejecucion: "En curso",
  presupuesto: "Presupuesto",
  cerrado_sospechoso: "Revisar carga",
  proyeccion: "Proyección",
};

const PUNTO: Record<Clave, string> = {
  cerrado: "bg-ink",
  en_ejecucion: "bg-cyan ring-2 ring-cyan/40",
  presupuesto: "border-2 border-ink-decor bg-transparent",
  cerrado_sospechoso: "bg-atencion",
  proyeccion: "border-2 border-dashed border-ink-decor bg-transparent",
};

function clave(marca: Marca | undefined): Clave {
  return marca ?? "proyeccion";
}

/** Punto + etiqueta de la marca de origen de un mes. */
export function MarcaOrigen({ marca }: { marca?: Marca }) {
  const k = clave(marca);
  return (
    <span className="inline-flex items-center gap-1.5 text-apoyo text-ink-faint">
      <span
        className={cn(
          "inline-block h-2.5 w-2.5 flex-none rounded-full",
          PUNTO[k],
        )}
      />
      {k === "cerrado_sospechoso" && (
        <span aria-hidden className="text-atencion">
          ⚠
        </span>
      )}
      {MARCA_LABEL[k]}
    </span>
  );
}

/** Leyenda de las cinco marcas de origen, para encima de la tabla/gráfico. */
export function LeyendaOrigen() {
  const orden: Clave[] = [
    "cerrado",
    "en_ejecucion",
    "presupuesto",
    "proyeccion",
    "cerrado_sospechoso",
  ];
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 rounded-xl border border-cyan/20 bg-cyan-tint px-4 py-2.5 text-apoyo">
      <span className="font-semibold text-ink">Origen de cada cifra:</span>
      {orden.map((k) => (
        <span
          key={k}
          className="inline-flex items-center gap-1.5 text-ink-soft"
        >
          <span
            className={cn(
              "inline-block h-2.5 w-2.5 flex-none rounded-full",
              PUNTO[k],
            )}
          />
          {MARCA_LABEL[k]}
        </span>
      ))}
    </div>
  );
}
