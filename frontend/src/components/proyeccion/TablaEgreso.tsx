// components/proyeccion/TablaEgreso.tsx
//
// V1 §3 — la tabla de Proyecciones deja de mostrar solo el ingreso: cada mes se
// resume en TRES totales (Ingreso · Costo · Gasto) que reconcilian con el flujo
// (candado en lib/egreso). Fila expandible por mes con el desglose completo, fila
// de totales al pie, sin centavos (F1 §3), flujo negativo en `critico`. El lote
// Auteco se marca real/proyectado según la ventana reconciliada (D2 §4).

import { Fragment, type ReactNode, useState } from "react";

import { Card } from "@/components/ui/card";
import { bucketsMes, totales } from "@/lib/egreso";
import { formatCOPEntero, formatMesCorto } from "@/lib/money";
import {
  ESTADO_LABEL,
  type EstadoMes,
  type MesProyeccion,
} from "@/lib/proyeccion";
import { cn } from "@/lib/utils";
import type Decimal from "decimal.js-light";

const ESTADO_ESTILO: Record<EstadoMes, string> = {
  ok: "bg-positivo/10 text-positivo",
  critico: "bg-atencion/10 text-atencion",
  negativo: "bg-critico/10 text-critico",
};
const ESTADO_SIMBOLO: Record<EstadoMes, string> = {
  ok: "✓",
  critico: "●",
  negativo: "✗",
};

interface TablaEgresoProps {
  filas: MesProyeccion[];
  mesCritico: string;
  perforada: boolean;
  ventanaReconciliada: [string, string] | null;
}

function esReconciliado(
  mes: string,
  ventana: [string, string] | null,
): boolean {
  return ventana !== null && mes >= ventana[0] && mes <= ventana[1];
}

/** Celda de monto sin centavos, alineada a la derecha, con el exacto en title. */
function Monto({
  valor,
  className,
}: {
  valor: string | Decimal;
  className?: string;
}) {
  return (
    <td className={cn("tabular px-4 py-2 text-right", className)}>
      {formatCOPEntero(valor)}
    </td>
  );
}

export function TablaEgreso({
  filas,
  mesCritico,
  perforada,
  ventanaReconciliada,
}: TablaEgresoProps) {
  const [abiertos, setAbiertos] = useState<Set<string>>(new Set());
  const t = totales(filas);

  const toggle = (mes: string) =>
    setAbiertos((prev) => {
      const next = new Set(prev);
      next.has(mes) ? next.delete(mes) : next.add(mes);
      return next;
    });

  return (
    <Card className="overflow-hidden p-0">
      <div className="overflow-x-auto">
        <table className="w-full font-sans text-cuerpo">
          <thead className="sticky top-0 z-10 bg-surface">
            <tr className="border-b border-hairline text-left text-ink-faint">
              <th className="sticky left-0 z-10 bg-surface px-4 py-2.5 font-semibold">
                Mes
              </th>
              <th className="px-4 py-2.5 text-right font-semibold">Motos</th>
              <th className="px-4 py-2.5 text-right font-semibold">Ingreso</th>
              <th className="px-4 py-2.5 text-right font-semibold">Costo</th>
              <th className="px-4 py-2.5 text-right font-semibold">Gasto</th>
              <th className="px-4 py-2.5 text-right font-semibold">Flujo</th>
              <th className="px-4 py-2.5 text-right font-semibold">Caja</th>
              <th className="px-4 py-2.5 font-semibold">Estado</th>
            </tr>
          </thead>
          <tbody>
            {filas.map((m) => {
              const b = bucketsMes(m);
              const esCritico = perforada && m.mes === mesCritico;
              const abierto = abiertos.has(m.mes);
              const flujoNeg = b.flujo.isNegative();
              return (
                <Fragment key={m.mes}>
                  <tr
                    id={esCritico ? "mes-critico" : undefined}
                    className={cn(
                      "border-b border-hairline/60 hover:bg-surface-muted",
                      esCritico && "scroll-mt-16 bg-atencion/10",
                    )}
                  >
                    <td className="sticky left-0 bg-surface p-0 font-medium text-ink">
                      <button
                        type="button"
                        onClick={() => toggle(m.mes)}
                        aria-expanded={abierto}
                        className="flex w-full items-center px-4 py-2 text-left hover:underline"
                      >
                        <span className="mr-1.5 inline-block text-ink-faint">
                          {abierto ? "▾" : "▸"}
                        </span>
                        {formatMesCorto(m.mes)}
                      </button>
                    </td>
                    <td className="tabular px-4 py-2 text-right text-ink-soft">
                      {m.motos}
                    </td>
                    <Monto valor={b.ingreso} className="font-medium text-ink" />
                    <Monto valor={b.costo} className="text-ink-soft" />
                    <Monto valor={b.gasto} className="text-ink-soft" />
                    <Monto
                      valor={b.flujo}
                      className={flujoNeg ? "text-critico" : "text-ink-soft"}
                    />
                    <Monto valor={m.caja} className="font-medium text-ink" />
                    <td className="px-4 py-2">
                      <span
                        className={cn(
                          "rounded-full px-2 py-0.5 font-sans text-apoyo font-medium whitespace-nowrap",
                          ESTADO_ESTILO[m.estado],
                        )}
                      >
                        {ESTADO_SIMBOLO[m.estado]} {ESTADO_LABEL[m.estado]}
                      </span>
                    </td>
                  </tr>
                  {abierto && (
                    <tr className="border-b border-hairline/60 bg-surface-muted/40">
                      <td colSpan={8} className="px-4 py-3">
                        <DesgloseMes
                          m={m}
                          reconciliado={esReconciliado(
                            m.mes,
                            ventanaReconciliada,
                          )}
                        />
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
          <tfoot className="border-t-2 border-hairline">
            <tr className="font-semibold text-ink">
              <td className="sticky left-0 bg-surface px-4 py-2.5">Totales</td>
              <td />
              <Monto valor={t.ingreso} />
              <Monto valor={t.costo} />
              <Monto valor={t.gasto} />
              <Monto
                valor={t.flujo}
                className={t.flujo.isNegative() ? "text-critico" : undefined}
              />
              <td className="tabular px-4 py-2.5 text-right">
                {filas.length > 0 &&
                  formatCOPEntero(filas[filas.length - 1].caja)}
              </td>
              <td />
            </tr>
          </tfoot>
        </table>
      </div>
    </Card>
  );
}

/** Fila de detalle: los componentes de cada bucket, agrupados. Reconcilia con
 * los tres totales (candado de lib/egreso). Marca el lote Auteco real/proyectado. */
function DesgloseMes({
  m,
  reconciliado,
}: {
  m: MesProyeccion;
  reconciliado: boolean;
}) {
  // los campos de egreso ya llegan negativos del motor: formatCOPEntero pinta el signo.
  const f = formatCOPEntero;
  return (
    <div className="grid grid-cols-1 gap-x-8 gap-y-1 text-apoyo sm:grid-cols-3">
      <Grupo titulo="Ingreso">
        <Linea etiqueta="Recaudo crédito" valor={f(m.recaudo_credito)} />
        <Linea etiqueta="Cuota inicial" valor={f(m.cuotas_iniciales)} />
      </Grupo>
      <Grupo titulo="Costo">
        <Linea
          etiqueta={`Lote Auteco · ${reconciliado ? "real" : "proyectado"}`}
          valor={f(m.pago_inventario)}
        />
        <Linea etiqueta="Fondeo del plazo" valor={f(m.fondeo)} />
        <Linea etiqueta="Alistamiento" valor={f(m.costo_nueva)} />
        {m.adelanto !== "0.00" && (
          <Linea etiqueta="Adelanto" valor={f(m.adelanto)} />
        )}
      </Grupo>
      <Grupo titulo="Gasto">
        <Linea etiqueta="Gastos fijos" valor={f(m.gastos_fijos)} />
        <Linea etiqueta="GPS cartera" valor={f(m.gps)} />
        <Linea etiqueta="Intereses deuda" valor={f(m.int_deuda)} />
        <Linea etiqueta="IVA" valor={f(m.iva)} />
      </Grupo>
    </div>
  );
}

function Grupo({
  titulo,
  children,
}: {
  titulo: string;
  children: ReactNode;
}) {
  return (
    <div>
      <div className="mb-1 font-semibold text-ink-faint uppercase tracking-wide">
        {titulo}
      </div>
      <dl className="flex flex-col gap-0.5">{children}</dl>
    </div>
  );
}

function Linea({ etiqueta, valor }: { etiqueta: string; valor: string }) {
  return (
    <div className="flex justify-between gap-4">
      <dt className="text-ink-soft">{etiqueta}</dt>
      <dd className="tabular text-ink">{valor}</dd>
    </div>
  );
}
