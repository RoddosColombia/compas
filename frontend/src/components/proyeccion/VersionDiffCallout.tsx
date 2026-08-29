// frontend/src/components/proyeccion/VersionDiffCallout.tsx
//
// RF-F2 — Compara la proyección actual contra la última versión APROBADA. Congelada al
// aprobar el presupuesto (§3: la proyección se vuelve versionada). Aquí solo se rinde
// el resumen: piso vs. anterior, mes del piso, y cambios en valles (nuevos/desaparecidos).
// Alertas de valle nuevo/más profundo son RF-F3 (no acá).

import { Card } from "@/components/ui/card";
import { formatCOPCompact, formatDelta } from "@/lib/money";
import type { VersionDiff } from "@/lib/proyeccion";

function mesLabel(yyyymm: string): string {
  // acepta 'YYYY-MM' o 'YYYY-MM-01'; devuelve 'AAAA-MM'
  return yyyymm.slice(0, 7);
}

export function VersionDiffCallout({ diff }: { diff: VersionDiff }) {
  if (!diff.hay_anterior) return null;
  const piso = diff.piso;
  const valles = diff.valles;
  const mma = diff.mes_mas_ajustado;
  const delta = piso ? formatDelta(piso.delta, "sube") : null;
  const cambioMes = mma && mma.anterior !== mma.actual;

  return (
    <Card className="flex flex-col gap-2 border-l-4 border-l-cyan bg-surface-muted/60 p-3">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-sm">
        <span className="font-display text-sm font-semibold text-ink">
          vs. última aprobación
        </span>
        <span className="text-apoyo text-ink-faint">
          v{diff.version_anterior} ·{" "}
          {diff.mes_aprobado_anterior
            ? `aprobada para ${mesLabel(diff.mes_aprobado_anterior)}`
            : ""}
        </span>
      </div>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        {piso && (
          <div>
            <div className="text-apoyo uppercase tracking-wide text-ink-faint">
              Piso de caja
            </div>
            <div className="tabular font-display text-lg font-semibold text-ink">
              {formatCOPCompact(piso.actual)}
            </div>
            {delta && (
              <div
                className={
                  delta.tono === "positivo"
                    ? "tabular text-sm text-positivo"
                    : delta.tono === "critico"
                      ? "tabular text-sm text-critico"
                      : "tabular text-sm text-ink-soft"
                }
              >
                {delta.texto} vs. {formatCOPCompact(piso.anterior)}
              </div>
            )}
          </div>
        )}

        {mma && (
          <div>
            <div className="text-apoyo uppercase tracking-wide text-ink-faint">
              Mes del piso
            </div>
            <div className="tabular font-display text-lg font-semibold text-ink">
              {mesLabel(mma.actual)}
            </div>
            {cambioMes && (
              <div className="text-sm text-ink-soft">
                antes: {mesLabel(mma.anterior)}
              </div>
            )}
          </div>
        )}

        {valles && (
          <div>
            <div className="text-apoyo uppercase tracking-wide text-ink-faint">
              Valles
            </div>
            <div className="tabular font-display text-lg font-semibold text-ink">
              {valles.actual}{" "}
              <span className="text-sm font-normal text-ink-soft">
                (antes {valles.anterior})
              </span>
            </div>
            {valles.nuevos.length > 0 && (
              <div className="text-sm text-atencion">
                nuevos: {valles.nuevos.map(mesLabel).join(", ")}
              </div>
            )}
            {valles.desaparecidos.length > 0 && (
              <div className="text-sm text-positivo">
                se cerraron: {valles.desaparecidos.map(mesLabel).join(", ")}
              </div>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}
