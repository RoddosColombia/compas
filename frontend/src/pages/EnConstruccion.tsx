// EnConstruccion — placeholder honesto para las vistas del Blueprint aún no
// construidas. Nombra la vista y marca que llega en la Fase B del cockpit.
// Para "Datos", recibe enlaces a las herramientas de captura que YA existen,
// para no perder acceso mientras se rediseñan.

import { Link } from "react-router-dom";

import { PageHeader } from "@/components/layout/PageHeader";
import { Card } from "@/components/ui/card";

export interface EnlaceRapido {
  label: string;
  path: string;
}

interface EnConstruccionProps {
  vista: string;
  descripcion?: string;
  enlaces?: EnlaceRapido[];
}

export default function EnConstruccion({
  vista,
  descripcion,
  enlaces,
}: EnConstruccionProps) {
  return (
    <>
      <PageHeader titulo={vista} descripcion={descripcion} />
      <Card className="border-dashed">
        <p className="font-sans text-sm text-ink-soft">
          Esta vista llega en la{" "}
          <span className="font-semibold text-ink">Fase B</span> del cockpit. El
          diseño y los datos ya están definidos; falta armarla.
        </p>
        {enlaces && enlaces.length > 0 && (
          <div className="mt-5">
            <p className="mb-2 font-sans text-xs font-semibold tracking-wide text-ink-faint uppercase">
              Disponible ahora
            </p>
            <div className="flex flex-wrap gap-2">
              {enlaces.map((e) => (
                <Link
                  key={e.path}
                  to={e.path}
                  className="rounded-lg border border-hairline bg-surface px-3 py-2 font-sans text-sm font-medium text-ink transition-colors hover:border-cyan hover:text-cyan"
                >
                  {e.label}
                </Link>
              ))}
            </div>
          </div>
        )}
      </Card>
    </>
  );
}
