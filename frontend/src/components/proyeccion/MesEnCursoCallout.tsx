// components/proyeccion/MesEnCursoCallout.tsx
//
// E1·P6 — el mes en curso: comparación (presupuesto del mes · ejecutado al día N · lo
// que resta del presupuesto) + completitud (B13, "cargado hasta el día N") con la
// fórmula en lenguaje de negocio (honestidad R5: se ve cómo se armó, no solo el
// resultado) + copy de efecto-arrastre. Nunca inventa cifras (montos del backend).
//
// Nota de honestidad: la 3ª cifra es lo que RESTA del presupuesto (proyectado −
// ejecutado) — lo que la Regla A añade para completar el mes —, NO una "desviación"
// entre el ejecutado parcial y el presupuesto completo, que a mitad de mes engañaría.

import { Card } from "@/components/ui/card";
import { formatCOPCompact, parseMonto } from "@/lib/money";
import type { MesEnCurso } from "@/lib/proyeccion";

const FORMULA_NEGOCIO = "ejecutado + lo que resta del presupuesto";

const MESES_LARGO = [
  "enero",
  "febrero",
  "marzo",
  "abril",
  "mayo",
  "junio",
  "julio",
  "agosto",
  "septiembre",
  "octubre",
  "noviembre",
  "diciembre",
];

/** 'YYYY-MM' → 'agosto' (nombre largo para copy legible; el CEO lo lee). */
function mesLargo(mes: string): string {
  return MESES_LARGO[Number(mes.split("-")[1]) - 1] ?? mes;
}

function Cifra({ k, valor }: { k: string; valor: string }) {
  return (
    <div className="rounded-lg border border-hairline bg-surface px-3 py-2">
      <div className="text-apoyo font-semibold uppercase tracking-wide text-ink-faint">
        {k}
      </div>
      <div className="tabular mt-0.5 font-display text-cuerpo font-bold text-ink">
        {valor}
      </div>
    </div>
  );
}

export function MesEnCursoCallout({ mesEnCurso }: { mesEnCurso: MesEnCurso }) {
  const mes = mesLargo(mesEnCurso.mes);
  const anio = mesEnCurso.mes.slice(0, 4);
  const resta = parseMonto(mesEnCurso.proyectado).minus(
    parseMonto(mesEnCurso.ejecutado),
  );
  const ejecutadoLbl =
    mesEnCurso.dia === null
      ? "Ejecutado (sin cargas)"
      : `Ejecutado (al día ${mesEnCurso.dia})`;
  return (
    <Card className="border-cyan/30 p-0">
      <div className="grid gap-0 sm:grid-cols-[1.4fr_1fr]">
        <div className="p-5">
          <span className="inline-flex items-center gap-2 text-apoyo font-semibold uppercase tracking-wide text-cyan">
            <span className="inline-block h-2.5 w-2.5 rounded-full bg-cyan ring-2 ring-cyan/40" />
            Mes en curso · {mes} {anio}
          </span>
          <div className="mt-3 grid grid-cols-3 gap-2">
            <Cifra
              k="Presupuesto del mes"
              valor={formatCOPCompact(mesEnCurso.proyectado)}
            />
            <Cifra
              k={ejecutadoLbl}
              valor={formatCOPCompact(mesEnCurso.ejecutado)}
            />
            <Cifra k="Resta del presupuesto" valor={formatCOPCompact(resta)} />
          </div>
          <p className="mt-3 border-l-[3px] border-cyan pl-3 text-cuerpo text-ink-soft">
            Cuando cierres {mes}, su ejecución real reemplaza esta estimación y
            arrastra el resto del año.
          </p>
        </div>
        <div className="border-t border-hairline bg-surface-muted p-5 sm:border-t-0 sm:border-l">
          <span className="text-apoyo font-semibold uppercase tracking-wide text-ink-soft">
            Completitud del mes
          </span>
          <p className="mt-1 font-display text-cuerpo font-semibold text-ink">
            {mesEnCurso.dia === null
              ? `${mes}: aún sin movimientos cargados`
              : `Cargado hasta el ${mesEnCurso.dia} de ${mes}`}
          </p>
          <p className="mt-2 text-apoyo text-ink-soft">
            Los días que faltan se estiman así:{" "}
            <span className="rounded-md border border-hairline bg-surface px-1.5 py-0.5 text-ink">
              {FORMULA_NEGOCIO}
            </span>
          </p>
        </div>
      </div>
    </Card>
  );
}
