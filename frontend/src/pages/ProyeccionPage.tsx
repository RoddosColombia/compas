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

import { useAuth } from "@/auth/AuthContext";
import { ComposicionCaja } from "@/components/charts/ComposicionCaja";
import { VallesCard } from "@/components/decisiones/VallesCard";
import { PageHeader } from "@/components/layout/PageHeader";
import { ComposicionResultado } from "@/components/proyeccion/ComposicionResultado";
import { LeyendaOrigen } from "@/components/proyeccion/MarcaOrigen";
import { MesEnCursoCallout } from "@/components/proyeccion/MesEnCursoCallout";
import { TablaEgreso } from "@/components/proyeccion/TablaEgreso";
import { TechoGastoCard } from "@/components/proyeccion/TechoGastoCard";
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
import { obtenerValles, resolver } from "@/lib/decisiones";
import { proximoCompromisoAuteco } from "@/lib/egreso";
import {
  formatCOPCompact,
  formatDelta,
  formatMesCorto,
  parseMonto,
} from "@/lib/money";
import {
  ESCENARIO_LABEL,
  type Escenario,
  type Proyeccion,
  obtenerProyeccion,
} from "@/lib/proyeccion";

const ESCENARIOS: Escenario[] = ["pesimista", "base", "optimista"];
// El juicio SIEMPRE mira al menos 60 m aunque la ventana sea corta (patrón F1).
const HORIZONTE_JUICIO = 60;

/** V1.1 ítem 6 — distancia en meses del próximo compromiso, en lenguaje natural. */
function distanciaTexto(meses: number): string {
  if (meses <= 0) return "este mes";
  if (meses === 1) return "el próximo mes";
  return `en ${meses} meses`;
}

export default function ProyeccionPage() {
  const { puede } = useAuth();
  const puedeGestionar = puede("proyeccion:gestionar");
  const [escenario, setEscenario] = useState<Escenario>("base");
  const [horizonte, setHorizonte] = useState(Number(HORIZONTE_DEFAULT));

  // Pieza 1 (ENTREGA 3) — techo de gasto del escenario en pantalla, a horizonte de
  // juicio (60 m: nunca un techo falsamente alto por ventana corta). Compute-only,
  // mismo permiso que el editor de Decisiones (matemática que propone, no persiste).
  const techoQ = useQuery({
    queryKey: ["resolver", "techo-proy", escenario],
    queryFn: () =>
      resolver(
        { objetivo: "techo_gasto" },
        { escenario, horizonteMeses: HORIZONTE_JUICIO },
      ),
    enabled: puedeGestionar,
  });

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
        descripcion="Caja proyectada mes a mes contra el mínimo de caja, por escenario."
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

      {/* Pieza 1: el techo de gasto — con qué el CEO arma el presupuesto del mes */}
      {puedeGestionar && (
        <TechoGastoCard
          techo={
            techoQ.data?.objetivo === "techo_gasto" ? techoQ.data : undefined
          }
          cargando={techoQ.isFetching}
          horizonteJuicio={HORIZONTE_JUICIO}
        />
      )}

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
          titulo="Meses de caja más baja"
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

  // KPI "Compromiso Auteco" (V1.1 ítem 6): el PRÓXIMO compromiso (mes, monto,
  // distancia) en TODO el horizonte — no la suma de dos meses que daba "$0" cuando
  // ambos eran paramétricos. Busca en data.meses (completo), no solo en la ventana.
  const compromiso = proximoCompromisoAuteco(
    data.meses,
    data.ventana_reconciliada,
  );
  const autecoEnValle =
    compromiso !== null && vallesMeses.includes(compromiso.mes);

  return (
    <>
      {/* KPIs con juicio + Compromiso Auteco (§4) como quinta baldosa */}
      <div className="grid grid-cols-2 gap-5 lg:grid-cols-3 xl:grid-cols-5">
        <KpiTileV2
          label="Piso de caja"
          valor={data.piso_caja}
          comparacion={{
            delta: formatDelta(vsUmbral),
            contra: "vs. el mínimo de caja",
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
          contexto={`para sostener el mínimo de caja de ${formatCOPCompact(data.caja_minima)}`}
          tono={requiereCapital ? "atencion" : "positivo"}
        />
        {data.runway_meses === null ? (
          <KpiTileV2
            label="Autonomía de caja"
            valor="0"
            valorTexto="Sin límite"
            contexto="la caja crece al ritmo actual"
            tono="positivo"
          />
        ) : (
          <KpiTileV2
            label="Autonomía de caja"
            valor="0"
            valorTexto={`${data.runway_meses} meses`}
            contexto="al ritmo de gasto actual"
            tono="atencion"
          />
        )}
        {/* V1.1 ítem 6 — Próximo compromiso Auteco: mes, monto y meses de distancia */}
        {compromiso === null ? (
          <KpiTileV2
            label="Compromiso Auteco"
            valor="0"
            valorTexto="Sin compromisos"
            contexto="ninguno en el horizonte proyectado"
            tono="positivo"
          />
        ) : (
          <KpiTileV2
            label="Próximo compromiso Auteco"
            valor={compromiso.monto}
            contexto={`${formatMesCorto(compromiso.mes)} · ${distanciaTexto(
              compromiso.mesesDistancia,
            )} · lote + costo de financiación · ${compromiso.real ? "factura registrada" : "proyección"}`}
            tono={autecoEnValle ? "atencion" : "neutro"}
          />
        )}
      </div>

      {/* E1·P6 — leyenda de origen (solo con ciclo; sin anclaje no se pinta) */}
      {Object.keys(data.meses_anclados ?? {}).length > 0 && <LeyendaOrigen />}

      {/* Protagonista: la curva anotada en la ventana */}
      <ChartCard
        conclusion={
          criticoFuera
            ? `El punto más ajustado (${formatMesCorto(data.mes_mas_ajustado)}) está más allá de esta vista`
            : perforada
              ? `La caja toca su punto más bajo en ${formatMesCorto(data.mes_mas_ajustado)}`
              : "La caja se sostiene sobre el mínimo de caja en todo el horizonte"
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
          mesesAnclados={data.meses_anclados}
        />
      </ChartCard>

      {/* SUP-5 — qué variables componen esa curva: los supuestos efectivos del
          escenario en pantalla y lo que producen en la ventana (motos, cartera,
          mora, recuperación, default). El mes a mes vive en la tabla. */}
      <ComposicionResultado supuestos={data.supuestos} meses={ventana} />

      {/* E1·P6 — el mes en curso: comparación + completitud (B13) + arrastre */}
      {data.mes_en_curso && (
        <MesEnCursoCallout mesEnCurso={data.mes_en_curso} />
      )}

      {/* Tabla V1 §3: tres totales por mes, fila expandible, fila de totales */}
      <div className="flex flex-col gap-2">
        <TablaEgreso
          filas={filas}
          mesCritico={data.mes_mas_ajustado}
          perforada={perforada}
          ventanaReconciliada={data.ventana_reconciliada}
          mesesAnclados={data.meses_anclados}
          sinMapear={data.sin_mapear}
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
