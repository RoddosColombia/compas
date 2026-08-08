// Pieza 1 (ENTREGA 3) — Techo de gasto en Proyecciones. Responde de frente la pregunta
// con la que el CEO arma el presupuesto del mes: "¿cuánto puedo gastar al mes sin
// perforar el umbral?". Cifra grande (text-cifra-lg) + una frase de lectura. Usa el
// solver que ya existe (compute-only, motor intocable): el front solo presenta.
//
// Honestidad (R5): si el solver dice que NO hay margen, se dice así ("Sin margen"),
// nunca se muestra $0 — un cero se leería como "puedo gastar cero", no como "no cabe".

import { Card, CardTitle } from "@/components/ui/card";
import { Cargando } from "@/components/ui/cargando";
import type { TechoResultado } from "@/lib/decisiones";
import { formatCOP, formatMesCorto } from "@/lib/money";

export function TechoGastoCard({
  techo,
  cargando,
  horizonteJuicio,
}: {
  techo: TechoResultado | undefined;
  cargando: boolean;
  horizonteJuicio: number;
}) {
  if (cargando && !techo) return <Cargando variante="card" />;
  if (!techo) return null;

  return (
    <Card className="flex flex-col gap-2">
      <CardTitle>
        ¿Cuánto puedo gastar al mes sin bajar del mínimo de caja?
      </CardTitle>
      {techo.hay_holgura ? (
        <>
          <p className="font-display text-cifra-lg font-bold text-ink">
            {formatCOP(techo.techo_mensual)}
            <span className="ml-1 font-sans text-cuerpo font-normal text-ink-soft">
              / mes
            </span>
          </p>
          <p className="font-sans text-cuerpo text-ink-soft">
            Con gastos de hasta esa cifra CADA mes, la caja se sostiene sobre el
            mínimo de caja los {horizonteJuicio} meses. Lo limita{" "}
            {formatMesCorto(techo.valle_limitante_mes)} — es el mes que primero
            toca el mínimo si gastas más.
          </p>
        </>
      ) : (
        <>
          <p className="font-display text-cifra-sm font-semibold text-atencion">
            Sin margen para más gasto
          </p>
          <p className="font-sans text-cuerpo text-ink-soft">
            El mes de caja más baja ({formatMesCorto(techo.valle_limitante_mes)}
            ) ya está en el límite: no cabe gasto permanente extra sin bajar del
            mínimo de caja. Para abrir espacio hay que subir el ingreso o
            recortar un gasto existente.
          </p>
        </>
      )}
    </Card>
  );
}
