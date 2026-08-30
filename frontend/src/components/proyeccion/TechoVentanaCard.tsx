// RF-F4 — Techo de gasto en VENTANA (Fundacional §2). Diferencia clave con el
// TechoGastoCard clásico: mira solo los primeros `ventana` meses (default 9) contra
// el umbral de ATENCIÓN (D-1), no contra el crítico. Levanta bandera roja cuando el
// valle DE LA VENTANA perfora la atención — aunque el horizonte completo cierre bien.

import { Card, CardTitle } from "@/components/ui/card";
import { Cargando } from "@/components/ui/cargando";
import type { TechoVentanaResultado } from "@/lib/decisiones";
import { formatCOP, formatMesCorto } from "@/lib/money";

export function TechoVentanaCard({
  techo,
  cargando,
}: {
  techo: TechoVentanaResultado | undefined;
  cargando: boolean;
}) {
  if (cargando && !techo) return <Cargando variante="card" />;
  if (!techo) return null;

  const perfora = techo.perfora_atencion;
  return (
    <Card
      className={`flex flex-col gap-2 ${
        perfora ? "border-critico/40 bg-critico/5" : ""
      }`}
    >
      <CardTitle>
        Techo de gasto en los próximos {techo.ventana} meses
      </CardTitle>

      {perfora && (
        <p className="font-sans text-cuerpo font-semibold text-critico">
          ⚠ La ventana de {techo.ventana} meses ya perfora el umbral de atención
          ({formatCOP(techo.referencia)}) sin gastar de más — el valle está en{" "}
          {formatMesCorto(techo.valle_limitante_mes)}. Aunque el horizonte
          completo cierre bien, el corto plazo pide acción.
        </p>
      )}

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
            umbral de atención ({formatCOP(techo.referencia)}) durante los{" "}
            {techo.ventana} meses de la ventana. Lo limita{" "}
            {formatMesCorto(techo.valle_limitante_mes)}.
          </p>
        </>
      ) : (
        !perfora && (
          <>
            <p className="font-display text-cifra-sm font-semibold text-atencion">
              Sin margen para más gasto
            </p>
            <p className="font-sans text-cuerpo text-ink-soft">
              El valle de la ventana (
              {formatMesCorto(techo.valle_limitante_mes)}) ya está en el límite:
              no cabe gasto permanente extra sin perforar la atención.
            </p>
          </>
        )
      )}
    </Card>
  );
}
