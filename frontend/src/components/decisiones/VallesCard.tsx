// VallesCard — D1 §3: los valles (hitos) de caja con sus causas en lenguaje llano.
// Compartida por la pestaña Decisiones (serie ajustada) y Proyecciones (serie vigente).
// Montos como string (regla 1); Number solo para el % de un desvío ya calculado.

import { Card, CardTitle } from "@/components/ui/card";
import { Cargando } from "@/components/ui/cargando";
import type { Valle } from "@/lib/decisiones";
import { formatCOP, formatCOPCompact, formatMesCorto } from "@/lib/money";

export function VallesCard({
  valles,
  cargando,
  titulo = "Meses de caja más baja",
}: {
  valles: Valle[];
  cargando: boolean;
  titulo?: string;
}) {
  return (
    <Card className="flex flex-col gap-3 p-5">
      <CardTitle>{titulo}</CardTitle>
      {cargando && valles.length === 0 && <Cargando variante="tabla" />}
      {!cargando && valles.length === 0 && (
        <p className="font-sans text-cuerpo text-positivo">
          Ningún mes de caja baja relevante en el horizonte: la caja queda
          holgada.
        </p>
      )}
      <ul className="flex flex-col gap-3">
        {valles.map((v) => (
          <ValleFila key={v.mes} valle={v} />
        ))}
      </ul>
    </Card>
  );
}

function ValleFila({ valle }: { valle: Valle }) {
  const perfora = valle.distancia_al_umbral.startsWith("-");
  const meses = valle.meses_para_prepararse;
  // RF-F3 · P2 — hay caracterización del segmento cuando el CEO tiene configurado
  // el umbral de atención. Sin umbral, entrada/salida/duracion vienen en null y solo
  // se muestra el fondo puntual (como antes).
  const tieneSegmento =
    valle.entrada != null && valle.duracion != null && valle.duracion > 0;
  // El color de la barrita a la izquierda: rojo si perfora el mínimo, ámbar si es un
  // valle bajo el umbral de atención (P3a), gris si no aplica.
  const barra = perfora
    ? "border-critico"
    : tieneSegmento
      ? "border-atencion"
      : "border-hairline";
  return (
    <li className={`flex flex-col gap-1 border-l-2 pl-3 ${barra}`}>
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-sans font-semibold text-ink">
          {formatMesCorto(valle.mes)}
        </span>
        <span
          className={`tabular font-sans text-cuerpo ${perfora ? "text-critico" : "text-ink-soft"}`}
          title={formatCOP(valle.caja)}
        >
          {formatCOPCompact(valle.caja)}
        </span>
      </div>
      <span className="font-sans text-apoyo text-ink-faint">
        {meses <= 0
          ? "es este mes"
          : `faltan ${meses} ${meses === 1 ? "mes" : "meses"}`}
        {perfora ? " · baja del mínimo de caja" : ""}
      </span>
      {tieneSegmento && (
        <span className="font-sans text-apoyo text-atencion">
          Bajo atención de {formatMesCorto(valle.entrada as string)}
          {valle.salida
            ? ` a ${formatMesCorto(valle.salida)}`
            : " · aún no sale"}
          {" · "}
          {valle.duracion} {valle.duracion === 1 ? "mes" : "meses"}
        </span>
      )}
      {valle.causas.length > 0 && (
        <span className="font-sans text-apoyo text-ink-soft">
          Lo explica:{" "}
          {valle.causas
            .map(
              (c) =>
                `${c.etiqueta}${
                  c.vs_promedio
                    ? ` (+${Math.round(Number(c.vs_promedio) * 100)}% sobre lo normal)`
                    : ""
                }`,
            )
            .join(" · ")}
        </span>
      )}
    </li>
  );
}
