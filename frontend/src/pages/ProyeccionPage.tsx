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

import { CashCurve } from "@/components/charts/CashCurve";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
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
import {
  formatCOPCompact,
  formatCOPEntero,
  formatDelta,
  formatMesCorto,
  parseMonto,
} from "@/lib/money";
import {
  ESCENARIO_LABEL,
  ESTADO_LABEL,
  type Escenario,
  type EstadoMes,
  type Proyeccion,
  obtenerProyeccion,
} from "@/lib/proyeccion";
import { cn } from "@/lib/utils";

const ESCENARIOS: Escenario[] = ["pesimista", "base", "optimista"];
// El juicio SIEMPRE mira al menos 60 m aunque la ventana sea corta (patrón F1).
const HORIZONTE_JUICIO = 60;

const ESTADO_ESTILO: Record<EstadoMes, string> = {
  ok: "bg-positivo/10 text-positivo",
  critico: "bg-atencion/10 text-atencion",
  negativo: "bg-critico/10 text-critico",
};

// Segundo canal del estado (el color nunca va solo — F1 §0.2).
const ESTADO_SIMBOLO: Record<EstadoMes, string> = {
  ok: "✓",
  critico: "●",
  negativo: "✗",
};

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
        />
      )}
    </div>
  );
}

function ProyeccionContenido({
  data,
  ventanaMeses,
  escenario,
}: {
  data: Proyeccion;
  ventanaMeses: number;
  escenario: Escenario;
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
            <a
              href="#mes-critico"
              onClick={() => {
                if (criticoFuera || !expandida) setExpandida(true);
              }}
              className="font-sans text-cuerpo font-semibold text-cyan hover:underline"
            >
              Ver el mes crítico ↓
            </a>
          ) : undefined
        }
      >
        <CashCurve meses={ventana} umbral={data.caja_minima} anotada />
      </ChartCard>

      {/* Tabla: ventana por defecto, expandible — nunca un volcado */}
      <Card className="overflow-hidden p-0">
        <div
          className={cn(
            "overflow-x-auto",
            expandida && "max-h-[34rem] overflow-y-auto",
          )}
        >
          <table className="w-full font-sans text-cuerpo">
            <thead className="sticky top-0 z-10 bg-surface">
              <tr className="border-b border-hairline text-left text-ink-faint">
                <th className="sticky left-0 z-10 bg-surface px-4 py-2.5 font-semibold">
                  Mes
                </th>
                <th className="px-4 py-2.5 text-right font-semibold">Motos</th>
                <th className="px-4 py-2.5 text-right font-semibold">
                  Recaudo crédito
                </th>
                <th className="px-4 py-2.5 text-right font-semibold">
                  Cuota inicial
                </th>
                <th className="px-4 py-2.5 text-right font-semibold">
                  Ingreso bruto
                </th>
                <th className="px-4 py-2.5 text-right font-semibold">Flujo</th>
                <th className="px-4 py-2.5 text-right font-semibold">Caja</th>
                <th className="px-4 py-2.5 font-semibold">Estado</th>
              </tr>
            </thead>
            <tbody>
              {filas.map((m) => {
                const esCritico = perforada && m.mes === data.mes_mas_ajustado;
                return (
                  <tr
                    key={m.mes}
                    id={esCritico ? "mes-critico" : undefined}
                    className={cn(
                      "border-b border-hairline/60 last:border-0 hover:bg-surface-muted",
                      esCritico && "scroll-mt-16 bg-atencion/10",
                    )}
                  >
                    <td className="sticky left-0 bg-surface px-4 py-2 font-medium text-ink">
                      {formatMesCorto(m.mes)}
                    </td>
                    <td className="tabular px-4 py-2 text-right text-ink-soft">
                      {m.motos}
                    </td>
                    <td className="tabular px-4 py-2 text-right text-ink-soft">
                      {formatCOPEntero(m.recaudo_credito)}
                    </td>
                    <td className="tabular px-4 py-2 text-right text-ink-soft">
                      {formatCOPEntero(m.cuotas_iniciales)}
                    </td>
                    <td className="tabular px-4 py-2 text-right font-medium text-ink">
                      {formatCOPEntero(m.ingreso_bruto)}
                    </td>
                    <td className="tabular px-4 py-2 text-right text-ink-soft">
                      {formatCOPEntero(m.flujo)}
                    </td>
                    <td className="tabular px-4 py-2 text-right font-medium text-ink">
                      {formatCOPEntero(m.caja)}
                    </td>
                    <td className="px-4 py-2">
                      <span
                        className={`rounded-full px-2 py-0.5 font-sans text-apoyo font-medium whitespace-nowrap ${ESTADO_ESTILO[m.estado]}`}
                      >
                        {ESTADO_SIMBOLO[m.estado]} {ESTADO_LABEL[m.estado]}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {data.meses.length > ventana.length && (
          <div className="border-t border-hairline px-4 py-2.5">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => setExpandida((v) => !v)}
            >
              {expandida
                ? `Ver solo la ventana de ${ventana.length} meses`
                : `Ver los ${data.meses.length} meses completos`}
            </Button>
          </div>
        )}
      </Card>
    </>
  );
}
