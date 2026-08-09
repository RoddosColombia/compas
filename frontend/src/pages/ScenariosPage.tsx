// frontend/src/pages/ScenariosPage.tsx
//
// Escenarios — F1.1 §3: los tres futuros con los MISMOS datos pero comunicando.
// Banda de rango (pesimista↔optimista) + línea base, zoom a la ventana donde
// los escenarios divergen (18 m default, juicio a horizonte largo — patrón F1),
// conclusión escrita desde los datos, y una KpiTileV2 por escenario con tono
// según el piso vs. el umbral. Todo lo calcula el motor; el front presenta.

import { useQueries } from "@tanstack/react-query";
import { useState } from "react";

import {
  ScenariosChart,
  type TonoSerie,
} from "@/components/charts/ScenariosChart";
import { PageHeader } from "@/components/layout/PageHeader";
import { Cargando } from "@/components/ui/cargando";
import { ChartCard } from "@/components/ui/chart-card";
import { ErrorEstado } from "@/components/ui/error-estado";
import {
  FiltroBarra,
  HORIZONTE_DEFAULT,
  OPCIONES_HORIZONTE,
} from "@/components/ui/filtro-barra";
import { KpiTileV2, type TonoKpi } from "@/components/ui/kpi-tile";
import {
  formatCOPCompact,
  formatDelta,
  formatMesCorto,
  parseMonto,
} from "@/lib/money";
import {
  type Escenario,
  type Proyeccion,
  obtenerProyeccion,
} from "@/lib/proyeccion";

const HORIZONTE_JUICIO = 60;

const ESCENARIOS: { esc: Escenario; label: string; tono: TonoSerie }[] = [
  { esc: "pesimista", label: "Pesimista", tono: "atencion" },
  { esc: "base", label: "Base", tono: "cyan" },
  { esc: "optimista", label: "Optimista", tono: "positivo" },
];

/** Tono del escenario según su piso: negativo → crítico; perfora el umbral sin
 * ser negativo → atención; sano → positivo. (Regla por umbrales — el ejemplo
 * del spec no sale de ninguna regla monótona; documentado en el PR.) */
function tonoPiso(data: Proyeccion): TonoKpi {
  const piso = parseMonto(data.piso_caja);
  if (piso.isNegative()) return "critico";
  if (piso.lessThan(parseMonto(data.caja_minima))) return "atencion";
  return "positivo";
}

/** La conclusión de la pantalla, escrita desde los datos (§3). */
function conclusionEscenarios(pes: Proyeccion, opt: Proyeccion): string {
  const faltaPeor = parseMonto(pes.capital_requerido);
  const faltaMejor = parseMonto(opt.capital_requerido);
  if (faltaPeor.isZero()) {
    return "La caja aguanta incluso el escenario pesimista";
  }
  if (faltaMejor.isZero()) {
    return `En el peor caso faltan ${formatCOPCompact(faltaPeor)}; en el mejor, sobra margen`;
  }
  return `Incluso en el mejor caso faltan ${formatCOPCompact(faltaMejor)}; en el peor, ${formatCOPCompact(faltaPeor)}`;
}

export default function ScenariosPage() {
  const [horizonte, setHorizonte] = useState(Number(HORIZONTE_DEFAULT));
  const fetchHorizonte = Math.max(horizonte, HORIZONTE_JUICIO);

  const resultados = useQueries({
    queries: ESCENARIOS.map((s) => ({
      queryKey: ["proyeccion", s.esc, fetchHorizonte],
      queryFn: () =>
        obtenerProyeccion({ escenario: s.esc, horizonteMeses: fetchHorizonte }),
    })),
  });

  // Robustez de estado: error si ALGUNO falla; skeleton mientras alguno carga.
  const error = resultados.some((r) => r.isError);
  const cargando = resultados.some((r) => r.isPending);
  const datos = resultados.map((r) => r.data);
  const listos = datos.every((d): d is Proyeccion => d !== undefined);

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        titulo="Escenarios"
        descripcion="Los tres futuros de la caja, uno al lado del otro, para decidir con margen."
        acciones={
          <FiltroBarra
            filtros={[
              {
                id: "horizonte",
                label: "Horizonte",
                opciones: OPCIONES_HORIZONTE,
                valor: String(horizonte),
                porDefecto: HORIZONTE_DEFAULT,
                onChange: (v) => setHorizonte(Number(v)),
              },
            ]}
          />
        }
      />

      {error && (
        <ErrorEstado
          mensaje="No se pudieron calcular los escenarios: verifica que haya modelos de moto y parámetros configurados en Supuestos."
          onReintentar={() => {
            for (const r of resultados) void r.refetch();
          }}
        />
      )}
      {!error && cargando && (
        <>
          <Cargando variante="card" className="h-80" />
          <Cargando variante="kpis" />
        </>
      )}

      {listos && !error && (
        <Contenido
          pesimista={datos[0]}
          base={datos[1]}
          optimista={datos[2]}
          ventanaMeses={horizonte}
        />
      )}
    </div>
  );
}

function Contenido({
  pesimista,
  base,
  optimista,
  ventanaMeses,
}: {
  pesimista: Proyeccion;
  base: Proyeccion;
  optimista: Proyeccion;
  ventanaMeses: number;
}) {
  const ventana = (p: Proyeccion) => p.meses.slice(0, ventanaMeses);

  return (
    <>
      <ChartCard
        conclusion={conclusionEscenarios(pesimista, optimista)}
        subtitulo={`banda pesimista ↔ optimista · línea = base · ${Math.min(ventanaMeses, base.meses.length)} de ${base.meses.length} meses`}
        pie="El piso de cada escenario (etiquetas del trazo) se calcula sobre el horizonte completo. Fuente: motor de proyección."
        protagonista
      >
        <ScenariosChart
          umbral={base.caja_minima}
          pesimista={{
            label: "Pesimista",
            tono: "atencion",
            meses: ventana(pesimista),
            piso: pesimista.piso_caja,
          }}
          base={{
            label: "Base",
            tono: "cyan",
            meses: ventana(base),
            piso: base.piso_caja,
          }}
          optimista={{
            label: "Optimista",
            tono: "positivo",
            meses: ventana(optimista),
            piso: optimista.piso_caja,
          }}
        />
      </ChartCard>

      {/* Una tarjeta-juicio por escenario */}
      <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
        {(
          [
            ["Pesimista", pesimista],
            ["Base", base],
            ["Optimista", optimista],
          ] as const
        ).map(([label, data]) => (
          <KpiTileV2
            key={label}
            label={`${label} · piso de caja`}
            valor={data.piso_caja}
            comparacion={{
              delta: formatDelta(
                parseMonto(data.piso_caja).minus(parseMonto(data.caja_minima)),
              ),
              contra: "vs. el mínimo de caja",
            }}
            contexto={`capital requerido: ${formatCOPCompact(data.capital_requerido)} · piso en ${formatMesCorto(data.mes_mas_ajustado)}`}
            tono={tonoPiso(data)}
          />
        ))}
      </div>
    </>
  );
}
