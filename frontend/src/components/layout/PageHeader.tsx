// PageHeader — encabezado estándar de cada vista del cockpit (Blueprint §3):
// título en Montserrat + contexto opcional + zona de acciones a la derecha.

import type { ReactNode } from "react";

interface PageHeaderProps {
  titulo: string;
  descripcion?: string;
  acciones?: ReactNode;
}

export function PageHeader({ titulo, descripcion, acciones }: PageHeaderProps) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="font-display text-2xl font-bold tracking-tight text-ink">
          {titulo}
        </h1>
        {descripcion && (
          <p className="mt-1 font-sans text-sm text-ink-soft">{descripcion}</p>
        )}
      </div>
      {acciones && <div className="flex items-center gap-2">{acciones}</div>}
    </div>
  );
}
