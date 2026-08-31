// KpiTileV2 — baldosa de KPI del cockpit (Blueprint §3; v1 murió en F1.1 §1).
// KpiTileV2 (sistema de diseño F1): cifra → juicio → acción. La comparación es
// OBLIGATORIA salvo que haya contexto (un número desnudo no compila: el tipo
// exige `comparacion` o `contexto`). Cifra compacta con el valor EXACTO en
// title= (hover = auditabilidad). Tono semántico = color + SÍMBOLO (nunca
// color solo). `to` opcional lleva al detalle.

import type Decimal from "decimal.js-light";
import { Link } from "react-router-dom";

import {
  type Delta,
  formatCOP,
  formatCOPCompact,
  parseMonto,
} from "@/lib/money";
import { cn } from "@/lib/utils";

export type TonoKpi = "neutro" | "positivo" | "atencion" | "critico";

// Segundo canal del tono (el color nunca va solo — regla §0.2 del sistema).
const TONO_SIMBOLO: Record<Exclude<TonoKpi, "neutro">, string> = {
  positivo: "✓",
  atencion: "●",
  critico: "✗",
};

const TONO_TEXTO: Record<Exclude<TonoKpi, "neutro">, string> = {
  positivo: "text-positivo",
  atencion: "text-atencion",
  critico: "text-critico",
};

interface KpiTileV2Base {
  label: string;
  /** Monto COP como string de la API (o Decimal ya derivado en presentación). */
  valor: string | Decimal;
  /** Texto ya formateado (ej. "1 de 18") — si se pasa, `valor` no se abrevia. */
  valorTexto?: string;
  /** Comparación: delta pre-calculado (formatDelta) + contra qué se compara. */
  comparacion?: { delta: Delta; contra: string };
  /** Línea de contexto en lenguaje llano (obligatoria si no hay comparación). */
  contexto?: string;
  tono?: TonoKpi;
  /** Ruta al detalle (la baldosa entera se vuelve clicable). */
  to?: string;
  className?: string;
  /** RV-V3 r2: serie de números crudos (últimos N puntos). Si trae ≥2 valores
   * el KpiTile dibuja un sparkline SVG debajo con el token --color-chart-real.
   * <2 valores → no se dibuja (sin tendencia posible). */
  sparkline?: number[];
}

// Cifra → juicio: sin "contra qué" no hay KPI. El tipo exige al menos uno.
export type KpiTileV2Props = KpiTileV2Base &
  ({ comparacion: { delta: Delta; contra: string } } | { contexto: string });

export function KpiTileV2(props: KpiTileV2Props) {
  const { label, valor, valorTexto, comparacion, contexto, tono, to, sparkline } = props;
  const tonoActivo = tono && tono !== "neutro" ? tono : null;
  const cifra = valorTexto ?? formatCOPCompact(valor);
  const exacto =
    valorTexto ??
    formatCOP(typeof valor === "string" ? parseMonto(valor) : valor);

  const contenido = (
    <>
      <p className="flex items-center gap-1.5 font-sans text-apoyo tracking-wide text-ink-faint uppercase">
        {label}
        {tonoActivo && (
          <span aria-hidden="true" className={TONO_TEXTO[tonoActivo]}>
            {TONO_SIMBOLO[tonoActivo]}
          </span>
        )}
      </p>
      <p
        title={exacto}
        className={cn(
          "tabular mt-1.5 font-display text-cifra",
          tonoActivo ? TONO_TEXTO[tonoActivo] : "text-ink",
        )}
      >
        {cifra}
      </p>
      {comparacion && (
        <p className="tabular mt-1 font-sans text-apoyo text-ink-soft">
          <span
            className={cn(
              "font-semibold",
              comparacion.delta.tono === "positivo" && "text-positivo",
              comparacion.delta.tono === "critico" && "text-critico",
            )}
          >
            {comparacion.delta.texto}
          </span>{" "}
          {comparacion.contra}
        </p>
      )}
      {contexto && (
        <p className="mt-1 font-sans text-apoyo text-ink-soft">{contexto}</p>
      )}
      {sparkline && sparkline.length >= 2 && <Sparkline values={sparkline} />}
    </>
  );

  const base = "block rounded-xl border border-hairline bg-surface p-5";
  if (to) {
    return (
      <Link
        to={to}
        className={cn(
          base,
          "transition-colors hover:bg-surface-muted",
          props.className,
        )}
      >
        {contenido}
      </Link>
    );
  }
  return <div className={cn(base, props.className)}>{contenido}</div>;
}

// ── RV-V3 rebanada 2: sparkline SVG inline ──────────────────────────────────
// Mini-gráfica de tendencia. Cero librerías, cero hex hardcodeado: el trazo lo
// pone --color-chart-real (el token de "estado real" de RV-V1). Se estira al
// ancho del contenedor con preserveAspectRatio="none"; el stroke queda fijo
// gracias a vector-effect="non-scaling-stroke". Un punto en el extremo derecho
// marca el valor "actual" (patrón Tufte). El aria-label describe la tendencia
// del primer al último valor — el lector de pantalla oye "sube" sin ver la línea.
function Sparkline({ values }: { values: number[] }) {
  const W = 80;
  const H = 20;
  const pad = 1.5;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const points = values.map((v, i) => {
    const x = (i / (values.length - 1)) * (W - 2 * pad) + pad;
    const y = H - pad - ((v - min) / range) * (H - 2 * pad);
    return { x, y };
  });
  const last = points[points.length - 1];
  const primero = values[0];
  const ultimo = values[values.length - 1];
  const trend =
    ultimo > primero ? "sube" : ultimo < primero ? "baja" : "estable";
  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="mt-2 h-5 w-full text-ink"
      preserveAspectRatio="none"
      role="img"
      aria-label={`Tendencia ${trend}: ${values.length} puntos`}
    >
      <polyline
        points={points.map((p) => `${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(" ")}
        fill="none"
        stroke="var(--color-chart-real)"
        strokeWidth="1.25"
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
      <circle
        cx={last.x.toFixed(2)}
        cy={last.y.toFixed(2)}
        r="1.5"
        fill="var(--color-chart-real)"
      />
    </svg>
  );
}
