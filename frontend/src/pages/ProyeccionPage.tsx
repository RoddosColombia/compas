// frontend/src/pages/ProyeccionPage.tsx
//
// Proyecciones — F1.1 §2: la vista hero al estándar del sistema. El JUICIO se
// calcula a horizonte largo (patrón F1 de Inicio: nunca un ✓ falso por ventana
// corta) y el GRÁFICO/tabla enfocan la ventana elegida (18 m default, FiltroBarra
// §9). 4 KpiTileV2 (Runway reformulado: null = "Sin límite"), ChartCard con
// conclusión dinámica, y la tabla deja de ser un volcado: ventana por defecto,
// "Ver los N meses completos" expande, sin centavos, headers/1ª columna sticky,
// fila del mes crítico resaltada y anclada. Todo lo calcula el motor (C7);
// .toNumber() SOLO geometría (regla 1).

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { ComposicionCaja } from "@/components/charts/ComposicionCaja";
import { VallesCard } from "@/components/decisiones/VallesCard";
import { PageHeader } from "@/components/layout/PageHeader";
import { TablaEgreso } from "@/components/proyeccion/TablaEgreso";
import { Button } from "@/components/ui/button";
import { Cargando } from "@/components/ui/cargando";
import { ChartCard } from "@/components/ui/chart-card";
import { ErrorEstado } from "@/components/ui/error-estado";
import {
  FiltroBarra,
  HORIZONTE_DEFAULT,
  OPCIONES_HORIZONTE,
} from "@/components/ui/filtro-barra";
import { KpiTileV2 } from "@/components/ui/kpi-tile";
import { ScenarioChip } from "@/components/ui/scenario-chip";
import { obtenerValles } from "@/lib/decisiones";
import { autecoDeMes } from "@/lib/egreso";
import {
  formatCOPCompact,
  formatDelta,
  formatMesCorto,
  parseMonto,
} from "@/lib/money";
import {
  ESCENARIO_LABEL,
  type Escenario,
  type MesProyeccion,
  type Proyeccion,
  obtenerProyeccion,
} from "@/lib/proyeccion";

const ESCENARIOS: Escenario[] = ["pesimista", "base", "optimista"];
// El juicio SIEMPRE mira al menos 60 m aunque la ventana sea corta (patrón F1).
const HORIZONTE_JUICIO = 60;

/** §4 — el Auteco que sale este mes y el próximo (lote + fondeo), real si esos
 * meses caen en la ventana reconciliada (facturas registradas), o proyectado. */
function compromisoAuteco(
  ventana: MesProyeccion[],
  ventanaRec: [string, string] | null,
) {
  const dos = ventana.slice(0, 2);
  let monto = autecoDeMes(dos[0]);
  if (dos[1]) monto = monto.plus(autecoDeMes(dos[1]));
  const meses = dos.map((m) => m.mes);
  const real =
    ventanaRec !== null &&
    dos.some((m) => m.mes >= ventanaRec[0] && m.mes <= ventanaRec[1]);
  return { monto, meses, real };
}

export default function ProyeccionPage() {
  const [escenario, setEscenario] = useState<Escenario>("base");
  const [horizonte, setHorizonte] = useState(Number(HORIZONTE_DEFAULT));

  // Se consulta el máximo entre la ventana elegida y el horizonte del juicio:
  // la ventana es un slice, así que una sola query cubre ambos.
  const fetchHorizonte = Math.max(horizonte, HORIZONTE_JUICIO);
  const q = useQuery({
    queryKey: ["proyeccion", escenario, fetchHorizonte],
    queryFn: () =>
      obtenerProyeccion({ escenario, horizonteMeses: fetchHorizonte }),
  });

  // D1 §3 — los valles (hitos) de la serie vigente, con sus causas.
  const vallesQ = useQuery({
    queryKey: ["valles", escenario, fetchHorizonte],
    queryFn: () => obtenerValles({ escenario, horizonteMeses: fetchHorizonte }),
  });

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        titulo="Proyecciones"
        descripcion="Caja proyectada mes a mes contra el umbral, por escenario."
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

      {/* Palancas: escenario */}
      <div className="flex flex-wrap items-center gap-2">
        {ESCENARIOS.map((e) => (
          <ScenarioChip
            key={e}
            label={ESCENARIO_LABEL[e]}
            active={escenario === e}
            onClick={() => setEscenario(e)}
          />
        ))}
      </div>

      {q.isLoading && (
        <>
          <Cargando variante="kpis" />
          <Cargando variante="card" className="h-80" />
        </>
      )}
      {q.isError && (
        <ErrorEstado
          mensaje="No se pudo calcular la proyección: verifica que haya modelos de moto y parámetros configurados en Supuestos."
          onReintentar={() => void q.refetch()}
        />
      )}

      {q.data && (
        <ProyeccionContenido
          data={q.data}
          ventanaMeses={horizonte}
          escenario={escenario}
          vallesMeses={(vallesQ.data?.valles ?? []).map((v) => v.mes)}
        />
      )}

      {q.data && (
        <VallesCard
          valles={vallesQ.data?.valles ?? []}
          cargando={vallesQ.isLoading}
          titulo="Valles de caja (hitos)"
        />
      )}
    </div>
  );
}

function ProyeccionContenido({
  data,
  ventanaMeses,
  escenario,
  vallesMeses,
}: {
  data: Proyeccion;
  ventanaMeses: number;
  escenario: Escenario;
  vallesMeses: string[];
}) {
  const [expandida, setExpandida] = useState(false);

  const perforada = data.meses_bajo_minimo > 0;
  const requiereCapital = !parseMonto(data.capital_requerido).isZero();
  const piso = parseMonto(data.piso_caja);
  const vsUmbral = piso.minus(parseMonto(data.caja_minima));

  const ventana = data.meses.slice(0, ventanaMeses);
  const criticoFuera =
    perforada && data.mes_mas_ajustado > ventana[ventana.length - 1].mes;
  const filas = expandida ? data.meses : ventana;

  // KPI "Compromiso Auteco" (§4): lote + fondeo que sale este mes y el próximo.
  const auteco = compromisoAuteco(ventana, data.ventana_reconciliada);
  const autecoEnValle = auteco.meses.some((m) => vallesMeses.includes(m));

  return (
    <>
      {/* 4 KPIs con juicio (calculados sobre el horizonte largo) */}
      <div className="grid grid-cols-2 gap-5 lg:grid-cols-4">
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
        {data.runway_meses === null ? (
          <KpiTileV2
            label="Runway"
            valor="0"
            valorTexto="Sin límite"
            contexto="la caja crece al ritmo actual"
            tono="positivo"
          />
        ) : (
          <KpiTileV2
            label="Runway"
            valor="0"
            valorTexto={`${data.runway_meses} meses`}
            contexto="al ritmo promedio de quema"
            tono="atencion"
          />
        )}
      </div>

      {/* §4 — Compromiso Auteco: lo que sale este mes y el próximo por lote + fondeo */}
      <KpiTileV2
        label="Compromiso Auteco"
        valor={auteco.monto}
        contexto={`Lote + fondeo de ${auteco.meses
          .map(formatMesCorto)
          .join(" y ")} · ${
          auteco.real ? "facturas registradas" : "proyección"
        }`}
        tono={autecoEnValle ? "atencion" : "neutro"}
        className="max-w-md"
      />

      {/* Protagonista: la curva anotada en la ventana */}
      <ChartCard
        conclusion={
          criticoFuera
            ? `El punto más ajustado (${formatMesCorto(data.mes_mas_ajustado)}) está más allá de esta vista`
            : perforada
              ? `La caja toca su punto más bajo en ${formatMesCorto(data.mes_mas_ajustado)}`
              : "La caja se sostiene sobre el umbral en todo el horizonte"
        }
        subtitulo={`caja proyectada · escenario ${ESCENARIO_LABEL[escenario].toLowerCase()} · ${ventana.length} de ${data.meses.length} meses`}
        pie={`Caja final a ${data.meses.length} meses: ${formatCOPCompact(data.caja_final)} (exacta en la tabla) · Fuente: motor de proyección`}
        protagonista
        acciones={
          perforada ? (
            <button
              type="button"
              onClick={() => {
                if (criticoFuera || !expandida) setExpandida(true);
                // desplazar a la fila del mes crítico una vez visible
                requestAnimationFrame(() =>
                  document.getElementById("mes-critico")?.scrollIntoView({
                    behavior: "smooth",
                    block: "center",
                  }),
                );
              }}
              className="font-sans text-cuerpo font-semibold text-cyan hover:underline"
            >
              Ver el mes crítico ↓
            </button>
          ) : undefined
        }
      >
        <ComposicionCaja
          meses={ventana}
          umbral={data.caja_minima}
          ventanaReconciliada={data.ventana_reconciliada}
        />
      </ChartCard>

      {/* Tabla V1 §3: tres totales por mes, fila expandible, fila de totales */}
      <div className="flex flex-col gap-2">
        <TablaEgreso
          filas={filas}
          mesCritico={data.mes_mas_ajustado}
          perforada={perforada}
          ventanaReconciliada={data.ventana_reconciliada}
        />
        {data.meses.length > ventana.length && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="self-start"
            onClick={() => setExpandida((v) => !v)}
          >
            {expandida
              ? `Ver solo la ventana de ${ventana.length} meses`
              : `Ver los ${data.meses.length} meses completos`}
          </Button>
        )}
      </div>
    </>
  );
}
