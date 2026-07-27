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
}

// Cifra → juicio: sin "contra qué" no hay KPI. El tipo exige al menos uno.
export type KpiTileV2Props = KpiTileV2Base &
  ({ comparacion: { delta: Delta; contra: string } } | { contexto: string });

export function KpiTileV2(props: KpiTileV2Props) {
  const { label, valor, valorTexto, comparacion, contexto, tono, to } = props;
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
