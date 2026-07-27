// frontend/src/pages/IvaPage.tsx
//
// IVA (C11) — la vista del cockpit: liquidación por período (generado − descontable con
// arrastre de saldo a favor), el PRÓXIMO pago a la DIAN, el saldo a favor vigente, y el
// FONDO DE PROVISIÓN (reserva mensual de tesorería para que el pago no sea un golpe seco
// a la caja). El período es configurable (cuatrimestral por defecto; bimestral cuando la
// DIAN lo exija). Todo lo calcula el backend (regla 1: montos como string → formatCOP;
// parseMonto solo para comparar, nunca Number sobre un monto).

import { useQuery } from "@tanstack/react-query";

import { PageHeader } from "@/components/layout/PageHeader";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Card, CardTitle } from "@/components/ui/card";
import { EstadoVacio } from "@/components/ui/estado-vacio";
import { KpiTileV2 } from "@/components/ui/kpi-tile";
import {
  type LiquidacionIva,
  PERIODICIDAD_LABEL,
  type PeriodoIva,
  obtenerLiquidacionIva,
} from "@/lib/iva";
import { formatCOP, parseMonto } from "@/lib/money";
import { type FondoMes, obtenerProyeccion } from "@/lib/proyeccion";

const esPositivo = (monto: string) => parseMonto(monto).greaterThan(0);

export default function IvaPage() {
  const liq = useQuery({
    queryKey: ["iva", "liquidacion"],
    queryFn: obtenerLiquidacionIva,
  });
  // El fondo de provisión viaja en la proyección (usa la línea de tiempo del motor).
  const proy = useQuery({
    queryKey: ["proyeccion", "base", 24],
    queryFn: () => obtenerProyeccion({ escenario: "base", horizonteMeses: 24 }),
  });

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        titulo="IVA"
        descripcion="Generado, descontable y liquidación por período; próximo pago a la DIAN y fondo de provisión."
        acciones={liq.data && <PeriodicidadBadge liq={liq.data} />}
      />

      {liq.isLoading && (
        <p className="font-sans text-sm text-ink-soft">Liquidando IVA…</p>
      )}
      {liq.isError && (
        <AlertBanner variant="danger">
          No se pudo cargar la liquidación de IVA.
        </AlertBanner>
      )}

      {liq.data && liq.data.periodos.length === 0 && (
        <Card>
          <EstadoVacio
            mensaje="Aún no hay facturas cargadas: con ellas verás la liquidación por período, el próximo pago a la DIAN y el fondo de provisión."
            quien="financiero o admin — hoy entran por la API de facturas; la pantalla de captura aún no existe"
          />
        </Card>
      )}

      {liq.data && liq.data.periodos.length > 0 && (
        <>
          <ResumenIva periodos={liq.data.periodos} />
          <LiquidacionTabla periodos={liq.data.periodos} />
          {proy.data && proy.data.fondo_provision.length > 0 && (
            <FondoProvision fondo={proy.data.fondo_provision} />
          )}
        </>
      )}
    </div>
  );
}

function PeriodicidadBadge({ liq }: { liq: LiquidacionIva }) {
  return (
    <span className="rounded-full bg-cyan-tint px-3 py-1 font-sans text-apoyo font-semibold text-ink">
      Período {PERIODICIDAD_LABEL[liq.periodicidad].toLowerCase()}
    </span>
  );
}

function ResumenIva({ periodos }: { periodos: PeriodoIva[] }) {
  // Próximo pago = primer período (cronológico) con neto a pagar > 0.
  const proximo = periodos.find((p) => esPositivo(p.neto_a_pagar));
  // Saldo a favor vigente = arrastre del último período liquidado.
  const saldoFavor = periodos[periodos.length - 1].saldo_favor_nuevo;

  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
      <KpiTileV2
        label="Próximo pago a la DIAN"
        valor={proximo ? proximo.neto_a_pagar : "0"}
        valorTexto={proximo ? undefined : "—"}
        contexto={proximo ? proximo.etiqueta : "sin pago pendiente"}
        tono={proximo ? "atencion" : "positivo"}
      />
      <KpiTileV2
        label="Saldo a favor"
        valor={saldoFavor}
        contexto="arrastre al próximo período"
      />
      <KpiTileV2
        label="Períodos liquidados"
        valor="0"
        valorTexto={String(periodos.length)}
        contexto="con facturas cargadas"
      />
    </div>
  );
}

function LiquidacionTabla({ periodos }: { periodos: PeriodoIva[] }) {
  return (
    <Card className="overflow-hidden p-0">
      <div className="border-b border-hairline px-4 py-3">
        <CardTitle>Liquidación por período</CardTitle>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full font-sans text-sm">
          <thead>
            <tr className="border-b border-hairline text-left text-ink-faint">
              <th className="px-4 py-2.5 font-semibold">Período</th>
              <th className="px-4 py-2.5 text-right font-semibold">Generado</th>
              <th className="px-4 py-2.5 text-right font-semibold">
                Descontable
              </th>
              <th className="px-4 py-2.5 text-right font-semibold">
                Saldo a favor previo
              </th>
              <th className="px-4 py-2.5 text-right font-semibold">
                Neto a pagar
              </th>
              <th className="px-4 py-2.5 text-right font-semibold">
                Saldo a favor
              </th>
            </tr>
          </thead>
          <tbody>
            {periodos.map((p) => {
              const paga = esPositivo(p.neto_a_pagar);
              return (
                <tr
                  key={p.etiqueta}
                  className="border-b border-hairline/60 last:border-0 hover:bg-surface-muted"
                >
                  <td className="px-4 py-2 font-medium text-ink">
                    {p.etiqueta}
                  </td>
                  <td className="tabular px-4 py-2 text-right text-ink-soft">
                    {formatCOP(p.generado)}
                  </td>
                  <td className="tabular px-4 py-2 text-right text-ink-soft">
                    {formatCOP(p.descontable)}
                  </td>
                  <td className="tabular px-4 py-2 text-right text-ink-soft">
                    {formatCOP(p.saldo_favor_previo)}
                  </td>
                  <td
                    className={`tabular px-4 py-2 text-right font-semibold ${
                      paga ? "text-critico" : "text-ink"
                    }`}
                  >
                    {formatCOP(p.neto_a_pagar)}
                  </td>
                  <td className="tabular px-4 py-2 text-right text-positivo">
                    {formatCOP(p.saldo_favor_nuevo)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function FondoProvision({ fondo }: { fondo: FondoMes[] }) {
  // Solo los meses con movimiento del fondo (reserva o pago) para no saturar.
  const activos = fondo.filter(
    (f) => esPositivo(f.reserva) || esPositivo(f.pago),
  );
  if (activos.length === 0) return null;

  return (
    <Card className="overflow-hidden p-0">
      <div className="border-b border-hairline px-4 py-3">
        <CardTitle>Fondo de provisión</CardTitle>
        <p className="mt-0.5 font-sans text-apoyo text-ink-faint">
          Reserva mensual para que el pago del período no sea un golpe seco a la
          caja: al llegar la fecha DIAN el fondo ya tiene el monto y el pago lo
          vacía.
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full font-sans text-sm">
          <thead>
            <tr className="border-b border-hairline text-left text-ink-faint">
              <th className="px-4 py-2.5 font-semibold">Mes</th>
              <th className="px-4 py-2.5 text-right font-semibold">Reserva</th>
              <th className="px-4 py-2.5 text-right font-semibold">
                Pago DIAN
              </th>
              <th className="px-4 py-2.5 text-right font-semibold">
                Saldo del fondo
              </th>
            </tr>
          </thead>
          <tbody>
            {activos.map((f) => (
              <tr
                key={f.mes}
                className="border-b border-hairline/60 last:border-0 hover:bg-surface-muted"
              >
                <td className="px-4 py-2 font-medium text-ink">{f.mes}</td>
                <td className="tabular px-4 py-2 text-right text-ink-soft">
                  {formatCOP(f.reserva)}
                </td>
                <td
                  className={`tabular px-4 py-2 text-right ${
                    esPositivo(f.pago) ? "text-critico" : "text-ink-soft"
                  }`}
                >
                  {formatCOP(f.pago)}
                </td>
                <td className="tabular px-4 py-2 text-right font-medium text-ink">
                  {formatCOP(f.saldo)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
