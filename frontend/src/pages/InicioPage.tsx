// frontend/src/pages/InicioPage.tsx
//
// Inicio — PILOTO del sistema de diseño F1 (§7): cifra → juicio → acción.
// Titular de juicio (una frase que reconcilia crecimiento y perforación),
// 4 KpiTiles v2 (cada cifra con comparación o contexto — nunca desnuda),
// gráfico protagonista con ejes/umbral etiquetado/mínimo anotado, y
// Realidad vs. proyección como soporte. El backend calcula todo; el front
// presenta. Horizonte por defecto: 18 meses (decisión F1, pendiente de
// confirmación del CEO en el piloto) — el mes crítico siempre queda dentro.

import { useQuery } from "@tanstack/react-query";
import Decimal from "decimal.js-light";
import { ArrowRight } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { CashCurve } from "@/components/charts/CashCurve";
import { PageHeader } from "@/components/layout/PageHeader";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Card, CardTitle } from "@/components/ui/card";
import { Cargando } from "@/components/ui/cargando";
import { ChartCard } from "@/components/ui/chart-card";
import { ErrorEstado } from "@/components/ui/error-estado";
import { EstadoVacio } from "@/components/ui/estado-vacio";
import { KpiTileV2 } from "@/components/ui/kpi-tile";
import { type Mes, listarMeses, mesEnEjecucion } from "@/lib/meses";
import {
  formatCOP,
  formatCOPCompact,
  formatDelta,
  formatMesCorto,
  parseMonto,
} from "@/lib/money";
import {
  type AnclaModo,
  type Comparacion,
  type Proyeccion,
  obtenerComparacion,
  obtenerProyeccion,
} from "@/lib/proyeccion";

// F1 + hallazgo QA del CEO: el JUICIO mira lejos, el GRÁFICO enfoca.
// El titular y los KPIs se calculan sobre el horizonte largo (60 m, como el
// Inicio previo) — si la perforación se corre más allá de la ventana corta,
// Inicio NO puede decir "✓ todo bien" (norte: no ser sorprendidos). El gráfico
// protagonista muestra la ventana de 18 m (una sola query: la ventana es el
// slice de la larga), con nota cuando el mes crítico queda fuera de la vista.
const HORIZONTE_JUICIO = 60;
const VENTANA_GRAFICO = 18;

export default function InicioPage() {
  const q = useQuery({
    queryKey: ["proyeccion", "base", HORIZONTE_JUICIO],
    queryFn: () =>
      obtenerProyeccion({
        escenario: "base",
        horizonteMeses: HORIZONTE_JUICIO,
      }),
  });
  const meses = useQuery({ queryKey: ["meses"], queryFn: listarMeses });

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        titulo="Inicio"
        descripcion="El pulso de la caja de RODDOS: dónde estamos y hacia dónde vamos."
      />

      {q.isLoading && (
        <>
          <Cargando variante="kpis" />
          <Cargando variante="card" className="h-80" />
        </>
      )}
      {q.isError && (
        <ErrorEstado
          mensaje="No se pudo leer el pulso de la caja: verifica que haya modelos de moto y parámetros configurados en Datos."
          onReintentar={() => void q.refetch()}
        />
      )}

      {q.data && (
        <Pulso
          data={q.data}
          mesActivo={mesEnEjecucion(meses.data?.items ?? [])}
        />
      )}
      <RealidadVsProyeccion />
    </div>
  );
}

// ── Titular de juicio (§7): una frase que reconcilia el mensaje ─────────────

function TitularJuicio({ data }: { data: Proyeccion }) {
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

// ── Caja hoy (conecta con la barra de C2): suma de saldos del mes operando ──

function cajaHoy(mesActivo: Mes | undefined): {
  valor: Decimal;
  contexto: string;
  tono: "positivo" | "atencion" | "neutro";
} | null {
  if (!mesActivo || mesActivo.saldos_banco.length === 0) return null;
  let total = new Decimal(0);
  for (const s of mesActivo.saldos_banco) {
    total = total.plus(parseMonto(s.saldo));
  }
  const d = new Date();
  const hoy = new Date(d.getTime() - d.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 10);
  const alDia = mesActivo.saldos_banco.filter(
    (s) => s.fecha_reporte === hoy,
  ).length;
  const n = mesActivo.saldos_banco.length;
  if (alDia === n)
    return { valor: total, contexto: "conciliada hoy ✓", tono: "positivo" };
  if (alDia > 0)
    return {
      valor: total,
      contexto: `reporte parcial hoy (${alDia}/${n})`,
      tono: "atencion",
    };
  const ultima = mesActivo.saldos_banco
    .map((s) => s.fecha_reporte)
    .sort()
    .reverse()[0];
  return {
    valor: total,
    contexto: `último reporte: ${ultima}`,
    tono: "atencion",
  };
}

function Pulso({
  data,
  mesActivo,
}: {
  data: Proyeccion;
  mesActivo: Mes | undefined;
}) {
  const perforada = data.meses_bajo_minimo > 0;
  const requiereCapital = !parseMonto(data.capital_requerido).isZero();
  const piso = parseMonto(data.piso_caja);
  const vsUmbral = piso.minus(parseMonto(data.caja_minima));
  const caja = cajaHoy(mesActivo);

  // Ventana del gráfico (18 m); el juicio de arriba ya miró los 60.
  const ventana = data.meses.slice(0, VENTANA_GRAFICO);
  const criticoFuera =
    perforada && data.mes_mas_ajustado > ventana[ventana.length - 1].mes;

  return (
    <>
      <TitularJuicio data={data} />

      <div className="grid grid-cols-2 gap-5 md:grid-cols-4">
        <KpiTileV2
          label="Piso de caja"
          valor={data.piso_caja}
          comparacion={{
            delta: formatDelta(vsUmbral),
            contra: "vs. el umbral",
          }}
          contexto={`en ${formatMesCorto(data.mes_mas_ajustado)}`}
          tono={perforada ? "critico" : "positivo"}
        />
        <KpiTileV2
          label="Meses bajo el mínimo"
          valor="0"
          valorTexto={`${data.meses_bajo_minimo} de ${data.meses.length}`}
          contexto={
            data.meses_bajo_minimo === 0
              ? "ninguno en el horizonte"
              : data.meses_bajo_minimo === 1
                ? `único: ${formatMesCorto(data.mes_mas_ajustado)}`
                : `el más ajustado: ${formatMesCorto(data.mes_mas_ajustado)}`
          }
          tono={perforada ? "critico" : "positivo"}
        />
        <KpiTileV2
          label="Capital requerido"
          valor={data.capital_requerido}
          contexto={`para sostener el umbral de ${formatCOPCompact(data.caja_minima)}`}
          tono={requiereCapital ? "atencion" : "positivo"}
        />
        {caja ? (
          <KpiTileV2
            label="Caja hoy"
            valor={caja.valor}
            contexto={caja.contexto}
            tono={caja.tono}
            to="/mes"
          />
        ) : (
          <KpiTileV2
            label="Caja hoy"
            valor="0"
            valorTexto="—"
            contexto="sin mes en ejecución"
            to="/mes"
          />
        )}
      </div>

      <ChartCard
        conclusion={
          criticoFuera
            ? `El punto más ajustado (${formatMesCorto(data.mes_mas_ajustado)}) está más allá de esta vista`
            : perforada
              ? `La caja toca su punto más bajo en ${formatMesCorto(data.mes_mas_ajustado)}`
              : "La caja se sostiene sobre el umbral en todo el horizonte"
        }
        subtitulo={`caja proyectada · escenario base · ${ventana.length} de ${data.meses.length} meses`}
        pie={
          criticoFuera
            ? `El mes crítico (${formatMesCorto(data.mes_mas_ajustado)}) queda fuera de la ventana de ${ventana.length} meses — ábrelo en la proyección completa. Fuente: motor de proyección (escenario base).`
            : "Fuente: motor de proyección (escenario base) · se recalcula al abrir"
        }
        protagonista
        acciones={
          <Link
            to="/proyeccion"
            className="inline-flex items-center gap-1 font-sans text-cuerpo font-semibold text-cyan transition-colors hover:text-cyan/80"
          >
            Ver proyección completa
            <ArrowRight className="h-4 w-4" />
          </Link>
        }
      >
        <CashCurve meses={ventana} umbral={data.caja_minima} anotada />
      </ChartCard>
    </>
  );
}

// COCK-09 — actuals (caja real de bancos) vs proyección re-anclada (rolling forecast).
function RealidadVsProyeccion() {
  const [ancla, setAncla] = useState<AnclaModo>("cerrado");
  const q = useQuery({
    queryKey: ["comparar", "base", ancla, HORIZONTE_JUICIO],
    queryFn: () =>
      obtenerComparacion({
        escenario: "base",
        ancla,
        horizonteMeses: HORIZONTE_JUICIO,
      }),
  });

  const selector = (
    <label className="flex items-center gap-2 font-sans text-cuerpo">
      <span className="text-ink-soft">Anclar a</span>
      <select
        className="rounded-md border border-hairline bg-surface px-3 py-1.5 text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan"
        value={ancla}
        onChange={(e) => setAncla(e.target.value as AnclaModo)}
      >
        <option value="cerrado">último mes cerrado</option>
        <option value="movimientos">último con movimientos</option>
      </select>
    </label>
  );

  return (
    <Card className="p-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <CardTitle>Realidad vs. proyección</CardTitle>
          <p className="mt-0.5 font-sans text-apoyo text-ink-faint">
            la proyección se re-ancla a la caja real (rolling forecast)
          </p>
        </div>
        {selector}
      </div>
      {q.isError ? (
        <AlertBanner variant="warn">
          No se pudo comparar realidad vs. proyección: falta configurar el motor
          (modelos de moto y parámetros en Datos) o cerrar un mes.
        </AlertBanner>
      ) : q.isPending ? (
        <Cargando variante="tabla" />
      ) : (
        q.data && <ComparacionContenido data={q.data} />
      )}
    </Card>
  );
}

function ComparacionContenido({ data }: { data: Comparacion }) {
  if (data.ancla === null) {
    return (
      <EstadoVacio
        mensaje={`Aún no hay un mes ${
          data.ancla_modo === "cerrado" ? "cerrado" : "con movimientos"
        }: la proyección arranca de los supuestos. Cuando el ciclo mensual corra, la caja real anclará el forecast.`}
        accion={{ to: "/mes", label: "Ir al ciclo del mes" }}
        quien="cualquier rol con el ciclo al día"
      />
    );
  }
  // tramo real (últimos meses) + cabeza del forecast re-anclado (primeros meses)
  const reales = data.actuals.slice(-4);
  const futuros = data.forecast.slice(1, 5); // [0] = el propio mes ancla (ya es real)
  return (
    <div className="flex flex-col gap-3">
      <KpiTileV2
        label={`Último real · ${data.ancla.mes}`}
        valor={data.ancla.caja_real}
        contexto="ancla del forecast"
      />
      <div className="overflow-x-auto">
        <table className="w-full font-sans text-cuerpo">
          <tbody>
            {reales.map((a) => (
              <FilaCaja key={a.mes} mes={a.mes} caja={a.caja_real} real />
            ))}
            {futuros.map((f) => (
              <FilaCaja key={f.mes} mes={f.mes} caja={f.caja} real={false} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function FilaCaja({
  mes,
  caja,
  real,
}: {
  mes: string;
  caja: string;
  real: boolean;
}) {
  return (
    <tr className="border-b border-hairline/60 last:border-0">
      <td className="py-1.5">
        <span
          className={`mr-2 inline-block h-2 w-2 rounded-full ${
            real ? "bg-positivo" : "bg-cyan"
          }`}
        />
        <span className="text-ink">{mes}</span>
      </td>
      <td className="py-1.5 font-sans text-apoyo text-ink-faint">
        {real ? "real" : "proyectado"}
      </td>
      <td className="tabular py-1.5 text-right font-medium text-ink">
        {formatCOP(caja)}
      </td>
    </tr>
  );
}
