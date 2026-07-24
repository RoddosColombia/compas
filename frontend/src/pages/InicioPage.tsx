// frontend/src/pages/InicioPage.tsx
//
// Inicio — el pulso ejecutivo del cockpit (Blueprint): la primera pantalla al
// entrar. Resume el estado de la caja según el escenario base del motor (C7):
// KPIs de cabecera, aviso de perforación y una trayectoria compacta con acceso a
// la proyección completa. El backend calcula todo; el front solo presenta.

import { useQuery } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";

import { CashCurve } from "@/components/charts/CashCurve";
import { PageHeader } from "@/components/layout/PageHeader";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Card, CardTitle } from "@/components/ui/card";
import { KpiTile } from "@/components/ui/kpi-tile";
import { formatCOP, parseMonto } from "@/lib/money";
import { type Proyeccion, obtenerProyeccion } from "@/lib/proyeccion";

const HORIZONTE_PULSO = 60; // mismo horizonte por defecto que Proyecciones

export default function InicioPage() {
  const q = useQuery({
    queryKey: ["proyeccion", "base", HORIZONTE_PULSO],
    queryFn: () =>
      obtenerProyeccion({ escenario: "base", horizonteMeses: HORIZONTE_PULSO }),
  });

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        titulo="Inicio"
        descripcion="El pulso de la caja de RODDOS: dónde estamos y hacia dónde vamos."
      />

      {q.isLoading && (
        <p className="font-sans text-sm text-ink-soft">Leyendo el pulso…</p>
      )}
      {q.isError && (
        <AlertBanner variant="danger">
          No se pudo leer el pulso. Verifica que haya modelos de moto y
          parámetros configurados en{" "}
          <span className="font-semibold">Datos</span>.
        </AlertBanner>
      )}

      {q.data && <Pulso data={q.data} />}
    </div>
  );
}

function Pulso({ data }: { data: Proyeccion }) {
  const perforada = data.meses_bajo_minimo > 0;
  const requiereCapital = !parseMonto(data.capital_requerido).isZero();

  return (
    <>
      {perforada ? (
        <AlertBanner variant="danger">
          Atención: la caja perfora el mínimo en {data.meses_bajo_minimo}{" "}
          {data.meses_bajo_minimo === 1 ? "mes" : "meses"}. El punto más
          ajustado es {data.mes_mas_ajustado} ({formatCOP(data.piso_caja)}).
        </AlertBanner>
      ) : (
        <AlertBanner variant="ok">
          La caja se mantiene por encima del mínimo en todo el horizonte.
        </AlertBanner>
      )}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <KpiTile
          label="Piso de caja"
          value={formatCOP(data.piso_caja)}
          sub={`en ${data.mes_mas_ajustado}`}
          tono={perforada ? "peligro" : "neutro"}
        />
        <KpiTile
          label="Meses bajo el mínimo"
          value={String(data.meses_bajo_minimo)}
          tono={perforada ? "peligro" : "neutro"}
        />
        <KpiTile
          label="Capital requerido"
          value={formatCOP(data.capital_requerido)}
          sub="para sostener el umbral"
          tono={requiereCapital ? "peligro" : "neutro"}
        />
        <KpiTile
          label="Runway"
          value={data.runway_meses === null ? "—" : `${data.runway_meses} m`}
          sub={
            data.runway_meses === null ? "caja no decrece" : "al ritmo actual"
          }
        />
      </div>

      <Card>
        <div className="mb-3 flex items-center justify-between gap-3">
          <div>
            <CardTitle>Trayectoria de caja</CardTitle>
            <p className="mt-0.5 font-sans text-xs text-ink-faint">
              escenario base · umbral {formatCOP(data.caja_minima)}
            </p>
          </div>
          <Link
            to="/proyeccion"
            className="inline-flex items-center gap-1 font-sans text-sm font-semibold text-cyan transition-colors hover:text-cyan/80"
          >
            Ver proyección completa
            <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
        <CashCurve
          meses={data.meses}
          umbral={data.caja_minima}
          className="h-40"
        />
      </Card>
    </>
  );
}
