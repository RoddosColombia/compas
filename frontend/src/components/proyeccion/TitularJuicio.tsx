// TitularJuicio — el patrón F1 §7 de Inicio, extraído en F1.1 §7 para
// compartirlo con Reportes (misma frase reconciliadora, mismos datos):
// "La caja crece, pero perfora el mínimo en X (…). Capital para cubrirlo: …".
// El juicio debe calcularse sobre el horizonte LARGO (responsabilidad del caller).

import { Link } from "react-router-dom";

import {
  formatCOP,
  formatCOPCompact,
  formatMesCorto,
  parseMonto,
} from "@/lib/money";
import type { Proyeccion } from "@/lib/proyeccion";

export function TitularJuicio({ data }: { data: Proyeccion }) {
  const perforada = data.meses_bajo_minimo > 0;
  const crece = parseMonto(data.caja_final).greaterThan(
    parseMonto(data.meses[0].caja),
  );

  if (!perforada) {
    return (
      <div className="rounded-xl border border-positivo/30 bg-positivo/5 px-5 py-4">
        <p className="font-sans text-cuerpo font-semibold text-positivo">
          ✓ La caja se mantiene sobre el mínimo de{" "}
          <span className="tabular">{formatCOPCompact(data.caja_minima)}</span>{" "}
          en los {data.meses.length} meses del horizonte.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-atencion/40 bg-atencion/5 px-5 py-4">
      <p className="font-sans text-cuerpo font-semibold text-atencion">
        ● La caja {crece ? "crece, pero" : "cae y"} perfora el mínimo en{" "}
        {formatMesCorto(data.mes_mas_ajustado)} (
        <span className="tabular" title={formatCOP(data.piso_caja)}>
          {formatCOPCompact(data.piso_caja)}
        </span>
        ). Capital para cubrirlo:{" "}
        <span className="tabular" title={formatCOP(data.capital_requerido)}>
          {formatCOPCompact(data.capital_requerido)}
        </span>
        .{" "}
        <Link
          to="/proyeccion"
          className="font-semibold text-cyan hover:underline"
        >
          Ver el mes crítico →
        </Link>
      </p>
    </div>
  );
}
