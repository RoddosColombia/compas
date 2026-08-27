// SaldoDisponibleBar — el saldo disponible EN VIVO, fijo y visible en TODAS las rutas
// (CEO 2026-08-24: "conocer cada vez que se actualice movimientos de banco el saldo
// disponible de dinero").
//
// Un solo número grande = el total disponible (saldo en banco + Wava en tránsito), la
// MISMA definición que la conciliación del cierre y que el arranque del ciclo. Al lado:
// el desglose por banco y la FRESCURA (qué tan viejo es el último movimiento) — si va
// atrasado, se pinta en ámbar para que el número no se lea como si estuviera al día.
//
// Componente HERMANO de MesStatusBar (no la toca — está QA'd por Kimi). Enlaza a
// /flujo-diario para el detalle. Query con staleTime 60 s; se invalida sola cuando la
// carga de movimientos invalida ["meses"] (misma key que ya mueve el saldo).

import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { obtenerSaldoDisponible } from "@/lib/caja";
import { formatCOP, formatCOPCompact } from "@/lib/money";

const STALE_MS = 60_000;

const BANCO_LABEL: Record<string, string> = {
  bancolombia: "Bancolombia",
  bbva: "BBVA",
  global66: "Global66",
};

function bancoLabel(b: string): string {
  return BANCO_LABEL[b] ?? b;
}

/** Texto de frescura + tono. `al_dia` verde, `atrasado` ámbar, resto neutro. */
function frescuraTexto(
  estado: string | undefined,
  dias: number | null | undefined,
): { texto: string; clase: string } {
  if (estado === "al_dia") {
    return { texto: "al día", clase: "text-positivo" };
  }
  if (estado === "atrasado") {
    const d = dias ?? 0;
    return {
      texto: `sin registrar hace ${d} día${d === 1 ? "" : "s"}`,
      clase: "text-atencion",
    };
  }
  return { texto: "sin movimientos aún", clase: "text-ink-faint" };
}

export function SaldoDisponibleBar() {
  const q = useQuery({
    queryKey: ["caja", "disponible"],
    queryFn: obtenerSaldoDisponible,
    staleTime: STALE_MS,
  });

  if (q.isLoading || q.isError || !q.data) return null;
  const d = q.data;

  // Sin mes en ejecución: la barra no aparece (MesStatusBar ya guía al paso pendiente).
  if (!d.disponible || d.total === undefined) return null;

  const fr = frescuraTexto(d.frescura?.estado, d.frescura?.dias);
  const bancos = d.por_banco ?? [];
  const transito = d.transito_wava ?? "0";
  const hayTransito = transito !== "0.00" && transito !== "0";

  return (
    <Link
      to="/flujo-diario"
      className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-hairline bg-surface px-4 py-2 font-sans transition-colors hover:bg-surface-muted md:px-6"
    >
      <span className="text-apoyo font-semibold tracking-wide text-ink-faint uppercase">
        Disponible
      </span>
      <span className="tabular font-display text-lg font-bold text-ink">
        {formatCOP(d.total)}
      </span>

      {/* desglose por banco (sm+): cada banco con su saldo */}
      {bancos.length > 0 && (
        <span className="hidden items-center gap-2 text-apoyo text-ink-soft sm:flex">
          <span className="text-ink-faint">·</span>
          {bancos.map((b, i) => (
            <span key={b.banco} className="tabular">
              {i > 0 && <span className="mr-2 text-ink-faint">+</span>}
              {bancoLabel(b.banco)} {formatCOPCompact(b.saldo)}
            </span>
          ))}
          {hayTransito && (
            <span className="tabular">
              <span className="mr-2 text-ink-faint">+</span>
              Wava {formatCOPCompact(transito)}
            </span>
          )}
        </span>
      )}

      {/* frescura: siempre visible, es lo que dice si el número es de fiar */}
      <span className="text-ink-faint">·</span>
      <span className={`text-apoyo font-medium ${fr.clase}`}>{fr.texto}</span>

      {/* bancos con movimientos pero sin saldo reportado (regla 7) */}
      {d.sin_dato && d.sin_dato.length > 0 && (
        <>
          <span className="hidden text-ink-faint sm:inline">·</span>
          <span className="hidden text-apoyo font-medium text-atencion sm:inline">
            falta reportar {d.sin_dato.map(bancoLabel).join(", ")}
          </span>
        </>
      )}
    </Link>
  );
}
