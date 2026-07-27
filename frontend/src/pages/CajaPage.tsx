// frontend/src/pages/CajaPage.tsx
//
// C4 ajuste diario de caja (CR-S6): reportar el saldo disponible por banco sobre el
// mes EN EJECUCIÓN y ver al instante si la información cuadra (conciliación D4). Es la
// segunda entrada diaria del norte (la otra es la carga de movimientos). El bloque de
// reporte vive en ReporteCajaCard (extraído en C2 para reusarlo en la Cabina).

import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { Link } from "react-router-dom";

import { ReporteCajaCard } from "@/components/caja/ReporteCajaCard";
import { PageHeader } from "@/components/layout/PageHeader";
import { listarMeses } from "@/lib/meses";

export default function CajaPage() {
  const meses = useQuery({ queryKey: ["meses"], queryFn: listarMeses });

  // El reporte diario es del mes OPERANDO (D3). Debe haber uno solo en ejecución.
  const mesActivo = useMemo(
    () => (meses.data?.items ?? []).find((m) => m.estado === "en_ejecucion"),
    [meses.data],
  );
  const mesCorto = mesActivo?.mes.slice(0, 7) ?? null;

  // Mes más reciente pendiente de aprobar (para el vacío accionable, C1).
  const mesPendiente = useMemo(() => {
    const items = meses.data?.items ?? [];
    return (
      items
        .filter((m) => m.estado === "sugerido" || m.estado === "propuesto")
        .map((m) => m.mes.slice(0, 7))
        .sort()
        .reverse()[0] ?? null
    );
  }, [meses.data]);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        titulo="Caja"
        descripcion={`Reporta el saldo de cada banco para que la información siempre cuadre${
          mesCorto ? ` · mes ${mesCorto}` : ""
        }`}
      />

      {meses.isLoading && (
        <p className="font-sans text-sm text-ink-soft">Cargando…</p>
      )}
      {meses.data && !mesActivo && (
        <p className="font-sans text-sm text-ink-soft">
          No hay ningún mes en ejecución.{" "}
          {mesPendiente ? (
            <Link
              to={`/meses/${mesPendiente}/presupuesto`}
              className="font-medium text-cyan hover:underline"
            >
              Aprueba el presupuesto de {mesPendiente} →
            </Link>
          ) : (
            <Link to="/meses" className="font-medium text-cyan hover:underline">
              Abre un mes para empezar el ciclo →
            </Link>
          )}
        </p>
      )}

      {mesActivo && <ReporteCajaCard mes={mesActivo} />}
    </div>
  );
}
