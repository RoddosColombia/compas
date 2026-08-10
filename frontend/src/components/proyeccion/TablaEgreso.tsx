// components/proyeccion/TablaEgreso.tsx
//
// V1 §3 — la tabla de Proyecciones deja de mostrar solo el ingreso: cada mes se
// resume en TRES totales (Ingreso · Costo · Gasto) que reconcilian con el flujo
// (candado en lib/egreso). Fila expandible por mes con el desglose completo, fila
// de totales al pie, sin centavos (F1 §3), flujo negativo en `critico`. El lote
// Auteco se marca real/proyectado según la ventana reconciliada (D2 §4).

import { Fragment, type ReactNode, useState } from "react";

import { MarcaOrigen } from "@/components/proyeccion/MarcaOrigen";
import { Card } from "@/components/ui/card";
import {
  ajusteRecaudoDeMes,
  autecoDeMes,
  bucketsMes,
  nuevaDeMes,
  totales,
} from "@/lib/egreso";
import { formatCOPEntero, formatMesCorto } from "@/lib/money";
import {
  ESTADO_LABEL,
  type EstadoMes,
  type MesProyeccion,
  type MarcaOrigen as TMarca,
} from "@/lib/proyeccion";
import { cn } from "@/lib/utils";
import Decimal from "decimal.js-light";

/** Σ de una columna sobre las filas (sumas de presentación de valores del backend,
 * mismo patrón que `totales`; nunca cálculo financiero nuevo). */
function sumaCol(
  filas: MesProyeccion[],
  valor: (m: MesProyeccion) => Decimal | string,
): Decimal {
  return filas.reduce<Decimal>((acc, m) => acc.plus(valor(m)), new Decimal(0));
}

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
  // E1·P6 — origen de cada mes (marca) + rubros sin clasificar. Opcionales: sin ciclo
  // no se renderiza nada nuevo (candado). La marca va en la 1ª columna (sin columna
  // nueva → sin scroll lateral).
  mesesAnclados?: Record<string, TMarca>;
  sinMapear?: string[];
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
  mesesAnclados = {},
  sinMapear = [],
}: TablaEgresoProps) {
  const [abiertos, setAbiertos] = useState<Set<string>>(new Set());
  const t = totales(filas);
  // V1.2 B — totales de las columnas discriminadas (ingreso y costo a la vista)
  const tInicial = sumaCol(filas, (m) => m.cuotas_iniciales);
  const tSemanal = sumaCol(filas, (m) => m.recaudo_credito);
  const tAjuste = sumaCol(filas, ajusteRecaudoDeMes); // PTS6-D: cierra la fila
  const tActivacion = sumaCol(filas, nuevaDeMes);
  const tAuteco = sumaCol(filas, autecoDeMes);

  // Candado: la marca de origen solo se pinta cuando hay ciclo (algún mes anclado);
  // sin anclaje la tabla queda idéntica a hoy (sin línea de marca bajo el mes).
  const hayCiclo = Object.keys(mesesAnclados).length > 0;

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
              {/* Ingreso discriminado a la VISTA (V1.2 B); Ajuste = PTS6-D:
                  Cuota inicial + Cuotas semanales + Ajuste == Ingreso (neto). */}
              <th className="px-4 py-2.5 text-right font-semibold">
                Cuota inicial
              </th>
              <th className="px-4 py-2.5 text-right font-semibold">
                Cuotas semanales
              </th>
              <th
                className="px-4 py-2.5 text-right font-semibold"
                title="Mora, recuperación y default sobre el recaudo bruto. La caja se proyecta con el ingreso neto."
              >
                Ajuste mora/default
              </th>
              <th className="px-4 py-2.5 text-right font-semibold">Ingreso</th>
              {/* Costo discriminado a la VISTA (V1.2 B). Alistamiento (antes
                  «Activación») es COSTO por moto colocada — Costo = Alistamiento
                  + Auteco. */}
              <th
                className="px-4 py-2.5 text-right font-semibold"
                title="Alistamiento por moto colocada (SOAT, matrícula, GPS…) + adelanto a Auteco. Es costo, no ingreso: Costo = Alistamiento + Auteco."
              >
                Alistamiento
              </th>
              <th className="px-4 py-2.5 text-right font-semibold">Auteco</th>
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
                        className="flex w-full flex-col items-start px-4 py-2 text-left hover:underline"
                      >
                        <span className="flex items-center">
                          <span className="mr-1.5 inline-block text-ink-faint">
                            {abierto ? "▾" : "▸"}
                          </span>
                          {formatMesCorto(m.mes)}
                        </span>
                        {hayCiclo && (
                          <MarcaOrigen marca={mesesAnclados[m.mes]} />
                        )}
                      </button>
                    </td>
                    <Monto
                      valor={m.cuotas_iniciales}
                      className="text-ink-soft"
                    />
                    <Monto
                      valor={m.recaudo_credito}
                      className="text-ink-soft"
                    />
                    <Monto
                      valor={ajusteRecaudoDeMes(m)}
                      className="text-ink-faint"
                    />
                    <Monto valor={b.ingreso} className="font-medium text-ink" />
                    <Monto valor={nuevaDeMes(m)} className="text-ink-soft" />
                    <Monto valor={autecoDeMes(m)} className="text-ink-soft" />
                    <Monto valor={b.costo} className="font-medium text-ink" />
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
                      <td colSpan={12} className="px-4 py-3">
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
              <Monto valor={tInicial} />
              <Monto valor={tSemanal} />
              <Monto valor={tAjuste} className="text-ink-faint" />
              <Monto valor={t.ingreso} />
              <Monto valor={tActivacion} />
              <Monto valor={tAuteco} />
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
      {sinMapear.length > 0 && (
        <div className="border-t border-hairline px-4 py-3 text-apoyo text-ink-soft">
          <span className="font-semibold text-ink">
            {sinMapear.length} rubro{sinMapear.length > 1 ? "s" : ""} con
            movimiento sin clasificar:
          </span>{" "}
          {sinMapear.map((r) => `«${r}»`).join(", ")}. No suman a ningún total
          del motor — revísalos.
        </div>
      )}
    </Card>
  );
}

/** Fila de detalle (V1.2 B): ingreso y costo ya están DISCRIMINADOS en columnas, así
 * que aquí solo queda lo que NO subió a columna — de qué se compone el Auteco (lote +
 * fondeo del plazo: transparencia del interés, candado anti-doble-conteo) y el
 * desglose del gasto. Marca el lote Auteco real/proyectado según la ventana. */
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
    <div className="grid grid-cols-1 gap-x-8 gap-y-1 text-apoyo sm:grid-cols-2">
      <Grupo titulo="Auteco (dentro de Costo)">
        <Linea
          etiqueta={`Lote · ${reconciliado ? "real" : "proyectado"}`}
          valor={f(m.pago_inventario)}
        />
        <Linea
          etiqueta="Costo de financiar el plazo (interés)"
          valor={f(m.fondeo)}
        />
      </Grupo>
      <Grupo titulo="Gasto">
        <Linea etiqueta="Gastos fijos" valor={f(m.gastos_fijos)} />
        <Linea etiqueta="GPS cartera" valor={f(m.gps)} />
        <Linea etiqueta="Deudas y obligaciones" valor={f(m.int_deuda)} />
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
