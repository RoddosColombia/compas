// MesStatusBar — barra de estado del mes, visible en TODAS las rutas del cockpit
// (C2 pieza 1): nadie tiene que preguntarse qué mes está corriendo ni cómo va.
// Toda la barra enlaza a la Cabina (/mes). El % consumido sale de vistaControl
// (ejecutado/definido con decimal.js — regla 1: nunca Number sobre montos);
// "caja reportada hoy" de saldos_banco[].fecha_reporte. Queries con staleTime
// de 60 s sobre las MISMAS keys que ya invalidan las mutaciones de caja/acotar/
// aprobar (["meses"] y ["mes", m, "control"]) — sin llamadas duplicadas.

import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { vistaControl } from "@/lib/control";
import { listarMeses, mesEnEjecucion, mesPendiente } from "@/lib/meses";
import { parseMonto } from "@/lib/money";

const STALE_MS = 60_000;

const MES_LARGO = [
  "Enero",
  "Febrero",
  "Marzo",
  "Abril",
  "Mayo",
  "Junio",
  "Julio",
  "Agosto",
  "Septiembre",
  "Octubre",
  "Noviembre",
  "Diciembre",
];

/** "2026-08" → { larga: "Agosto 2026", corta: "Ago 2026" }. */
function etiquetaMes(mes7: string): { larga: string; corta: string } {
  const [y, m] = mes7.split("-");
  const nombre = MES_LARGO[Number(m) - 1] ?? mes7;
  return { larga: `${nombre} ${y}`, corta: `${nombre.slice(0, 3)} ${y}` };
}

function hoyLocal(): string {
  const d = new Date();
  const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}

export function MesStatusBar() {
  const meses = useQuery({
    queryKey: ["meses"],
    queryFn: listarMeses,
    staleTime: STALE_MS,
  });
  const items = meses.data?.items ?? [];
  const activo = mesEnEjecucion(items);
  const mes7 = activo?.mes.slice(0, 7) ?? null;

  const control = useQuery({
    queryKey: ["mes", mes7, "control"],
    queryFn: () => vistaControl(mes7 as string),
    enabled: mes7 !== null,
    staleTime: STALE_MS,
  });

  if (meses.isLoading || meses.isError) return null;

  // ── Sin mes en ejecución: el paso pendiente, con enlace al paso ──
  if (!activo) {
    const pendiente = mesPendiente(items);
    return (
      <div className="flex h-9 items-center gap-2 border-b border-hairline bg-surface px-4 font-sans text-apoyo md:px-6">
        <Link to="/mes" className="font-medium text-ink-soft hover:text-ink">
          Sin mes en ejecución
        </Link>
        <span className="text-ink-faint">·</span>
        {pendiente ? (
          <Link
            to={`/meses/${pendiente}/presupuesto`}
            className="font-medium text-cyan hover:underline"
          >
            Aprueba el presupuesto de {pendiente} →
          </Link>
        ) : (
          <Link to="/meses" className="font-medium text-cyan hover:underline">
            Abre un mes para empezar el ciclo →
          </Link>
        )}
      </div>
    );
  }

  // ── Mes en ejecución ──
  const { larga, corta } = etiquetaMes(mes7 as string);
  let pct: string | null = null;
  if (control.data) {
    const definido = parseMonto(control.data.total.definido);
    if (definido.greaterThan(0)) {
      pct = parseMonto(control.data.total.ejecutado)
        .div(definido)
        .times(100)
        .toDecimalPlaces(0)
        .toString();
    }
  }
  // ✓ solo si TODOS los bancos que alguna vez reportaron tienen fecha de HOY;
  // con reportes mixtos se muestra "parcial (n/m)" — un solo banco al día no
  // debe dar la caja del día por hecha (hallazgo QA C2).
  const hoy = hoyLocal();
  const reportados = activo.saldos_banco.length;
  const alDia = activo.saldos_banco.filter(
    (s) => s.fecha_reporte === hoy,
  ).length;

  return (
    <Link
      to="/mes"
      className="flex h-9 items-center gap-2 border-b border-hairline bg-surface px-4 font-sans text-apoyo text-ink-soft transition-colors hover:bg-surface-muted md:px-6"
    >
      <span className="font-semibold text-ink">
        <span className="sm:hidden">{corta}</span>
        <span className="hidden sm:inline">{larga}</span>
      </span>
      <span className="text-ink-faint">·</span>
      <span className="font-medium text-positivo">En ejecución</span>
      {pct !== null && (
        <>
          <span className="text-ink-faint">·</span>
          <span className="tabular">
            {pct} %
            <span className="hidden sm:inline"> del presupuesto consumido</span>
          </span>
        </>
      )}
      <span className="hidden text-ink-faint sm:inline">·</span>
      {reportados > 0 && alDia === reportados ? (
        <span className="hidden font-medium text-positivo sm:inline">
          caja reportada hoy ✓
        </span>
      ) : alDia > 0 ? (
        <span className="hidden font-medium text-atencion sm:inline">
          caja parcial hoy ({alDia}/{reportados})
        </span>
      ) : (
        <span className="hidden font-medium text-atencion sm:inline">
          caja sin reportar hoy
        </span>
      )}
    </Link>
  );
}
