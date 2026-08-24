// components/proyeccion/ComposicionResultado.tsx
//
// SUP-5 (CEO 2026-08-23) — "quisiera que existieran ciertas referencias de las
// variables que componen este resultado de proyección: cuánta mora se está teniendo,
// cuánto default, cuántas motos vendidas mes a mes… que permita nutrir la gráfica
// para entender qué variables componen este resultado".
//
// La pantalla ya mostraba el RESULTADO (caja, piso, ingreso, egresos). Esta tarjeta
// muestra el POR QUÉ, en dos niveles:
//   ① los SUPUESTOS de la curva que se está viendo. Importa de verdad desde SUP-2:
//      cada escenario tiene su propia mora, así que aquí van los EFECTIVOS del
//      escenario en pantalla, no los del set base.
//   ② los TOTALES de cartera de la ventana: cuántas motos se colocan, cuánto ingreso
//      bruto generan y cuánto de ese bruto se queda en el camino (mora sin recuperar
//      + incumplimiento) antes de llegar a la caja.
//
// El detalle MES A MES no se duplica aquí: vive en la tabla (columna «Motos» y el
// desglose «Cartera» de la fila expandible). Una sola tabla en la página — el tope
// anti-congelamiento de §10.3 se mide sobre `tbody tr`.

import Decimal from "decimal.js-light";

import { Card, CardTitle } from "@/components/ui/card";
import { formatCOPEntero } from "@/lib/money";
import type { MesProyeccion, SupuestosProyeccion } from "@/lib/proyeccion";

function pct(v: string | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `${new Decimal(v).times(100).toDecimalPlaces(2).toString()} %`;
}

function suma(meses: MesProyeccion[], campo: keyof MesProyeccion): Decimal {
  return meses.reduce(
    (acc, m) => acc.plus(new Decimal(String(m[campo] ?? "0"))),
    new Decimal(0),
  );
}

/** Una variable: qué vale y qué significa (nunca una cifra desnuda — F1). */
function Variable({
  label,
  valor,
  nota,
  tono = "neutro",
}: {
  label: string;
  valor: string;
  nota: string;
  tono?: "neutro" | "positivo" | "atencion" | "critico";
}) {
  const color = {
    neutro: "text-ink",
    positivo: "text-positivo",
    atencion: "text-atencion",
    critico: "text-critico",
  }[tono];
  return (
    <div className="flex flex-col gap-0.5 rounded-lg bg-surface-muted px-3 py-2">
      <span className="font-sans text-apoyo font-medium tracking-wide text-ink-faint uppercase">
        {label}
      </span>
      <span className={`tabular font-sans text-cuerpo font-semibold ${color}`}>
        {valor}
      </span>
      <span className="font-sans text-apoyo text-ink-faint">{nota}</span>
    </div>
  );
}

export function ComposicionResultado({
  supuestos,
  meses,
}: {
  supuestos: SupuestosProyeccion | undefined;
  /** La misma ventana que pinta la gráfica de arriba. */
  meses: MesProyeccion[];
}) {
  const motos = meses.reduce((a, m) => a + m.motos, 0);
  const carteraFinal = meses.length > 0 ? meses[meses.length - 1].cartera : 0;
  const mora = suma(meses, "mora");
  const recup = suma(meses, "recuperacion");
  const def = suma(meses, "default");
  const bruto = suma(meses, "ingreso_bruto");
  const neto = suma(meses, "neto");
  // lo que la cartera se queda en el camino: mora + recuperación + default, que es
  // exactamente `neto − bruto` (el «Ajuste mora/default» de la tabla).
  const fuga = neto.minus(bruto);

  return (
    <Card>
      <CardTitle>Qué compone este resultado</CardTitle>
      <p className="mt-0.5 font-sans text-apoyo text-ink-faint">
        Los supuestos de esta curva y lo que producen en la ventana. Cambia
        cualquiera en Supuestos y la proyección se recalcula. El mes a mes está
        en la tabla de abajo (columna Motos y el desglose de cada mes).
      </p>

      {/* ① los supuestos EFECTIVOS del escenario en pantalla */}
      {supuestos && (
        <>
          <h3 className="mt-4 font-sans text-apoyo font-semibold tracking-wide text-ink-faint uppercase">
            Lo que esta curva supone
          </h3>
          <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
            <Variable
              label="Mora"
              valor={pct(supuestos.pct_mora)}
              nota="del ingreso que no llega a tiempo"
              tono="atencion"
            />
            <Variable
              label="Recuperación"
              valor={pct(supuestos.pct_recuperacion)}
              nota={
                supuestos.meses_rezago_recuperacion > 0
                  ? `de la mora, ${supuestos.meses_rezago_recuperacion} mes(es) después`
                  : "de la mora, el mismo mes"
              }
              tono="positivo"
            />
            <Variable
              label="Incumplimiento"
              valor={pct(supuestos.pct_default)}
              nota="se pierde y no vuelve"
              tono="critico"
            />
            <Variable
              label="Meta de colocación"
              valor={`${supuestos.motos_base} motos/mes`}
              nota={`crece ${pct(supuestos.crec_pct_mensual)} cada mes`}
            />
            <Variable
              label="Ritmo de largo plazo"
              valor={
                supuestos.crec_pct_mensual_2
                  ? pct(supuestos.crec_pct_mensual_2)
                  : "sin cambio"
              }
              nota={
                supuestos.crec_mes_corte
                  ? `desde el mes ${supuestos.crec_mes_corte + 1}`
                  : "un solo tramo de crecimiento"
              }
            />
            <Variable
              label="Fondo de aval"
              valor={pct(supuestos.pct_aval_recaudo)}
              nota="del recaudo, reservado fuera de caja"
            />
          </div>
        </>
      )}

      {/* ② lo que esos supuestos producen en la ventana */}
      <h3 className="mt-5 font-sans text-apoyo font-semibold tracking-wide text-ink-faint uppercase">
        Lo que produce en estos {meses.length} meses
      </h3>
      <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        <Variable
          label="Motos colocadas"
          valor={String(motos)}
          nota="suma de la ventana"
        />
        <Variable
          label="Cartera activa al final"
          valor={`${carteraFinal} créditos`}
          nota="créditos vigentes pagando"
        />
        <Variable
          label="Ingreso bruto"
          valor={formatCOPEntero(bruto)}
          nota="cuotas iniciales + recaudo"
        />
        <Variable
          label="Mora"
          valor={formatCOPEntero(mora)}
          nota="no llega en su mes"
          tono="atencion"
        />
        <Variable
          label="Recuperación"
          valor={formatCOPEntero(recup)}
          nota="mora que sí vuelve"
          tono="positivo"
        />
        <Variable
          label="Incumplimiento"
          valor={formatCOPEntero(def)}
          nota="pérdida definitiva"
          tono="critico"
        />
      </div>

      <p className="mt-3 font-sans text-apoyo text-ink-faint">
        De {formatCOPEntero(bruto)} de ingreso esperado en esta ventana, la
        cartera se queda{" "}
        <span className="font-semibold text-atencion">
          {formatCOPEntero(fuga.negated())}
        </span>{" "}
        en el camino y entran{" "}
        <span className="font-semibold text-ink">{formatCOPEntero(neto)}</span>{" "}
        a caja. La provisión de cartera se calcula aparte y no resta caja (es
        P&G, no flujo).
      </p>
    </Card>
  );
}
