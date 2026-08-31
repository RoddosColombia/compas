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
import { ComposicionFlujoRV2 } from "@/components/charts/ComposicionFlujoRV2";
import { CurvaCajaRV2 } from "@/components/charts/CurvaCajaRV2";
import { VallesCard } from "@/components/decisiones/VallesCard";
import { PageHeader } from "@/components/layout/PageHeader";
import { ComposicionResultado } from "@/components/proyeccion/ComposicionResultado";
import { LeyendaOrigen } from "@/components/proyeccion/MarcaOrigen";
import { MesEnCursoCallout } from "@/components/proyeccion/MesEnCursoCallout";
import { TablaEgreso } from "@/components/proyeccion/TablaEgreso";
import { TechoGastoCard } from "@/components/proyeccion/TechoGastoCard";
import { TechoVentanaCard } from "@/components/proyeccion/TechoVentanaCard";
import { VersionDiffCallout } from "@/components/proyeccion/VersionDiffCallout";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
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
  type ArranqueCaja,
  ESCENARIO_LABEL,
  type Escenario,
  type GranularidadAgregada,
  type PeriodoAgregado,
  type Proyeccion,
  obtenerProyeccion,
  obtenerProyeccionAgregada,
  obtenerVersionDiff,
} from "@/lib/proyeccion";

const ESCENARIOS: Escenario[] = ["pesimista", "base", "optimista"];
// El juicio SIEMPRE mira al menos 60 m aunque la ventana sea corta (patrón F1).
const HORIZONTE_JUICIO = 60;

/**
 * P2 del ciclo mensual — de dónde salió la plata con la que arranca la curva. El CEO
 * tiene que poder ver si la proyección parte del efectivo REAL del último cierre o de
 * un número configurado a mano (que era el caso: la semilla decía $704.722.003 mientras
 * el cierre de julio dejó $665.715.578).
 */
function textoArranque(a: ArranqueCaja | null | undefined): string {
  if (!a) return "";
  const monto = formatCOPCompact(a.valor);
  if (a.origen === "ciclo") {
    const transito = !parseMonto(a.transito_heredado).isZero()
      ? ` (incluye ${formatCOPCompact(a.transito_heredado)} en tránsito)`
      : "";
    return `Arranca con la caja real de ${formatMesCorto(a.mes ?? "")}: ${monto}${transito}, del cierre del mes anterior`;
  }
  if (a.origen === "override")
    return `Arranca con una caja re-anclada: ${monto}`;
  return `Arranca con la caja configurada en Supuestos: ${monto} — el mes no está abierto en el ciclo`;
}

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

  // RF-F4 — Techo en VENTANA de 9 meses contra el umbral de ATENCIÓN. Detecta el
  // valle cercano aunque el horizonte largo cierre bien. Se pinta al lado del techo
  // clásico; con la bandera roja pintada cuando la ventana perfora la atención.
  const techoVentanaQ = useQuery({
    queryKey: ["resolver", "techo-ventana", escenario],
    queryFn: () =>
      resolver(
        { objetivo: "techo_gasto_ventana", ventana_meses: 9 },
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

  // RF-F2 — diff contra la última versión aprobada (piso, mes del piso, valles).
  const diffQ = useQuery({
    queryKey: ["proyeccion", "version", "diff", escenario, fetchHorizonte],
    queryFn: () =>
      obtenerVersionDiff({ escenario, horizonteMeses: fetchHorizonte }),
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

      {/* Pieza 1: el techo de gasto — con qué el CEO arma el presupuesto del mes.
          RF-F4 · a su lado el techo de VENTANA (9m contra atención): atrapa el valle
          cercano aunque el horizonte largo cierre bien. */}
      {puedeGestionar && (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <TechoGastoCard
            techo={
              techoQ.data?.objetivo === "techo_gasto" ? techoQ.data : undefined
            }
            cargando={techoQ.isFetching}
            horizonteJuicio={HORIZONTE_JUICIO}
          />
          <TechoVentanaCard
            techo={
              techoVentanaQ.data?.objetivo === "techo_gasto_ventana"
                ? techoVentanaQ.data
                : undefined
            }
            cargando={techoVentanaQ.isFetching}
          />
        </div>
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

      {diffQ.data?.hay_anterior && <VersionDiffCallout diff={diffQ.data} />}

      {q.data && (
        <VallesCard
          valles={vallesQ.data?.valles ?? []}
          cargando={vallesQ.isLoading}
          titulo="Meses de caja más baja"
          // RF-F3 · P3b — marca cada valle según su cambio vs. última aprobación.
          mesesNuevos={new Set(diffQ.data?.valles?.nuevos ?? [])}
          mesesMasProfundos={
            new Set((diffQ.data?.valles?.mas_profundos ?? []).map((v) => v.mes))
          }
        />
      )}

      {/* RF-F10 · Fundacional §2 — Horizonte largo con agregación. Mostrar 120+
          puntos mensuales es ruido; con la vista por trimestre/año la caja de
          largo plazo se lee. Solo se ofrece cuando la ventana ≥ 60 meses. */}
      {horizonte >= 60 && (
        <HorizonteLargoCard escenario={escenario} horizonte={horizonte} />
      )}
    </div>
  );
}

function HorizonteLargoCard({
  escenario,
  horizonte,
}: {
  escenario: Escenario;
  horizonte: number;
}) {
  const [granularidad, setGranularidad] =
    useState<GranularidadAgregada>("anual");
  const q = useQuery({
    queryKey: ["proyeccion", "agregada", escenario, horizonte, granularidad],
    queryFn: () =>
      obtenerProyeccionAgregada(granularidad, {
        escenario,
        horizonteMeses: horizonte,
      }),
  });
  return (
    <Card className="flex flex-col gap-3 p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <CardTitle>Horizonte largo — vista agregada</CardTitle>
        <div className="flex items-center gap-1">
          <GranularidadChip
            label="Trimestre"
            active={granularidad === "trimestre"}
            onClick={() => setGranularidad("trimestre")}
          />
          <GranularidadChip
            label="Año"
            active={granularidad === "anual"}
            onClick={() => setGranularidad("anual")}
          />
        </div>
      </div>
      {q.isLoading && <Cargando variante="tabla" />}
      {q.isError && (
        <ErrorEstado
          mensaje="No se pudo cargar la vista agregada."
          onReintentar={() => void q.refetch()}
        />
      )}
      {q.data && <TablaAgregada periodos={q.data.periodos} />}
    </Card>
  );
}

function GranularidadChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={
        active
          ? "rounded-full bg-cyan/15 px-3 py-1 font-sans text-apoyo font-semibold text-cyan"
          : "rounded-full bg-surface-muted px-3 py-1 font-sans text-apoyo text-ink-soft hover:bg-hairline"
      }
    >
      {label}
    </button>
  );
}

function TablaAgregada({ periodos }: { periodos: PeriodoAgregado[] }) {
  if (periodos.length === 0) {
    return (
      <p className="font-sans text-cuerpo text-ink-soft">
        Sin datos para agregar en el horizonte pedido.
      </p>
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full font-sans text-sm">
        <thead>
          <tr className="border-b border-hairline text-left text-ink-faint">
            <th className="px-3 py-2 font-semibold">Periodo</th>
            <th className="px-3 py-2 text-right font-semibold">Caja al cierre</th>
            <th className="px-3 py-2 text-right font-semibold">
              Piso del periodo
            </th>
            <th className="px-3 py-2 text-right font-semibold">Flujo neto</th>
            <th className="px-3 py-2 text-right font-semibold">Ingreso bruto</th>
            <th className="px-3 py-2 text-right font-semibold">Egresos</th>
            <th className="px-3 py-2 text-right font-semibold">Motos</th>
          </tr>
        </thead>
        <tbody>
          {periodos.map((p) => (
            <tr
              key={p.etiqueta}
              className="border-b border-hairline/60 last:border-0"
              data-testid={`periodo-${p.etiqueta}`}
            >
              <td className="px-3 py-2 font-medium text-ink">
                {p.etiqueta}
                {p.meses_en_periodo < 12 && (
                  <span
                    className="ml-1.5 font-sans text-apoyo text-ink-faint"
                    title={`Periodo parcial (${p.meses_en_periodo} meses)`}
                  >
                    · parcial
                  </span>
                )}
              </td>
              <td className="tabular px-3 py-2 text-right text-ink-soft">
                {formatCOPCompact(p.caja_final)}
              </td>
              <td className="tabular px-3 py-2 text-right text-ink-soft">
                {formatCOPCompact(p.piso)}
              </td>
              <td className="tabular px-3 py-2 text-right text-ink-soft">
                {formatCOPCompact(p.flujo)}
              </td>
              <td className="tabular px-3 py-2 text-right text-ink-soft">
                {formatCOPCompact(p.ingreso_bruto)}
              </td>
              <td className="tabular px-3 py-2 text-right text-ink-soft">
                {formatCOPCompact(p.egresos)}
              </td>
              <td className="tabular px-3 py-2 text-right text-ink-soft">
                {p.motos}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
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
        pie={`${textoArranque(data.arranque)} · Caja final a ${data.meses.length} meses: ${formatCOPCompact(data.caja_final)} (exacta en la tabla) · Fuente: motor de proyección`}
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
        {/* RV-V2 rebanada 1 (2026-08-30): CurvaCajaRV2 reemplaza a ComposicionCaja
            en la vista principal. */}
        <CurvaCajaRV2 data={data} ventanaMeses={ventanaMeses} />
      </ChartCard>

      {/* RV-V2 rebanada 2 (2026-08-30) · AC #8 · Composición del flujo en GRÁFICA
          PROPIA (no franja, regla 7 del DESIGN.md): ingreso arriba, egresos por
          concepto abajo apilados, línea de flujo neto. Usa los 4 tokens categóricos
          de RV-V1 (`--color-chart-ingreso/gasto-fijo/auteco/otros`), disjuntos
          del semáforo (regla 9). */}
      <ChartCard
        conclusion="De qué está hecho el flujo cada mes"
        subtitulo={`composición del flujo · ${ventana.length} de ${data.meses.length} meses · ingreso arriba, egresos por concepto abajo`}
        pie="Las 4 categorías (ingreso · gastos fijos · Auteco · otros) no comparten familia de color con los umbrales — el semáforo queda reservado a estado (regla 9 del DESIGN.md)."
      >
        <ComposicionFlujoRV2 meses={ventana} />
      </ChartCard>

      {/* SUP-5 — qué variables componen esa curva: los supuestos efectivos del
          escenario en pantalla y lo que producen en la ventana (motos, cartera,
          mora, recuperación, default). El mes a mes vive en la tabla. */}
      <ComposicionResultado supuestos={data.supuestos} meses={ventana} />

      {/* E1·P6 — el mes en curso: comparación + completitud (B13) + arrastre */}
      {data.mes_en_curso && (
        <MesEnCursoCallout
          mesEnCurso={data.mes_en_curso}
          arranque={data.arranque}
          cajaCierre={
            data.meses.find((m) => m.mes === data.mes_en_curso?.mes)?.caja
          }
        />
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
