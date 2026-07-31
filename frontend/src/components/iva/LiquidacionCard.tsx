// frontend/src/components/iva/LiquidacionCard.tsx
//
// Liquidación del período (spec de diseño §3③): desglose en el ORDEN del cálculo,
// próximo pago DIAN, y selector de períodos HONESTO. Todo el cálculo lo hace el
// backend (regla 1): aquí solo se formatean strings y se COMPARAN montos
// (decimal.js-light permitido solo para comparar, §5) — cero aritmética.
//
// Honestidad (§3③/§8.5): `/liquidacion` solo devuelve períodos CON facturas. El
// cliente sintetiza los candidatos (los del año en curso + el anterior); un período
// sin facturas dice "sin facturas cargadas", NUNCA "$ 0,00 a pagar" — un cero
// calculado y un cero por falta de datos no pueden verse igual.
//
// Regla dura: NUNCA un pago negativo. "A pagar" sale del `neto_a_pagar` del backend
// (ya es max(0, …)); si hay saldo a favor, se muestra además la línea que se arrastra
// con token positivo (§8.1). `critico` no se usa: pagar IVA es normal (§7).

import { useState } from "react";

import { Card, CardTitle } from "@/components/ui/card";
import { ScenarioChip } from "@/components/ui/scenario-chip";
import type { LiquidacionIva, Periodicidad, PeriodoIva } from "@/lib/iva";
import { formatCOP, parseMonto } from "@/lib/money";

const MESES_ABBR = [
  "ene",
  "feb",
  "mar",
  "abr",
  "may",
  "jun",
  "jul",
  "ago",
  "sep",
  "oct",
  "nov",
  "dic",
];

const MESES_LARGOS = [
  "enero",
  "febrero",
  "marzo",
  "abril",
  "mayo",
  "junio",
  "julio",
  "agosto",
  "septiembre",
  "octubre",
  "noviembre",
  "diciembre",
];

function mesesPorPeriodo(p: Periodicidad): number {
  return p === "cuatrimestral" ? 4 : 2;
}

function prefijo(p: Periodicidad): string {
  return p === "cuatrimestral" ? "C" : "B";
}

function etiquetaDe(anio: number, idx: number, p: Periodicidad): string {
  return `${anio}-${prefijo(p)}${idx}`;
}

/** Rango humano del período: "may–ago". */
function rangoPeriodo(idx: number, p: Periodicidad): string {
  const meses = mesesPorPeriodo(p);
  const ini = (idx - 1) * meses;
  const fin = idx * meses - 1;
  return `${MESES_ABBR[ini]}–${MESES_ABBR[fin]}`;
}

function fechaLarga(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${Number(d)} de ${MESES_LARGOS[Number(m) - 1]} de ${y}`;
}

interface Candidato {
  anio: number;
  idx: number;
  etiqueta: string;
  titulo: string; // "may–ago 2026"
}

/** Períodos que ofrece el selector: los del AÑO en curso + el inmediato anterior
 * (§3③). El backend solo devuelve los que tienen facturas; el resto se muestra como
 * "sin facturas cargadas". */
function candidatos(hoy: Date, p: Periodicidad): Candidato[] {
  const meses = mesesPorPeriodo(p);
  const n = 12 / meses; // 3 cuatrimestral | 6 bimestral
  const anio = hoy.getFullYear();
  const lista: Candidato[] = [];
  // el inmediato anterior al primer período del año = último período del año pasado
  lista.push({
    anio: anio - 1,
    idx: n,
    etiqueta: etiquetaDe(anio - 1, n, p),
    titulo: `${rangoPeriodo(n, p)} ${anio - 1}`,
  });
  for (let idx = 1; idx <= n; idx++) {
    lista.push({
      anio,
      idx,
      etiqueta: etiquetaDe(anio, idx, p),
      titulo: `${rangoPeriodo(idx, p)} ${anio}`,
    });
  }
  return lista;
}

function periodoDeHoy(hoy: Date, p: Periodicidad): string {
  const meses = mesesPorPeriodo(p);
  const idx = Math.floor(hoy.getMonth() / meses) + 1;
  return etiquetaDe(hoy.getFullYear(), idx, p);
}

function Fila({
  label,
  monto,
  signo,
  fuerte,
  tono,
  testId,
}: {
  label: string;
  monto: string;
  signo?: "menos";
  fuerte?: boolean;
  tono?: "positivo";
  testId?: string;
}) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1">
      <span
        className={`font-sans ${fuerte ? "text-cuerpo font-semibold text-ink" : "text-cuerpo text-ink-soft"} ${
          tono === "positivo" ? "text-positivo" : ""
        }`}
      >
        {label}
      </span>
      <span
        data-testid={testId}
        className={`tabular-nums ${fuerte ? "text-cifra-sm font-semibold" : "text-cuerpo"} ${
          tono === "positivo" ? "text-positivo" : "text-ink"
        }`}
      >
        {signo === "menos" ? "− " : ""}
        {formatCOP(monto)}
      </span>
    </div>
  );
}

function Desglose({ p }: { p: PeriodoIva }) {
  const hayFavorNuevo = parseMonto(p.saldo_favor_nuevo).gt(0);
  return (
    <div className="flex flex-col">
      <Fila label="IVA generado (facturas emitidas)" monto={p.generado} />
      <Fila
        label="IVA descontable (recibidas deducibles)"
        monto={p.descontable}
        signo="menos"
      />
      <div className="my-1 border-hairline border-t" />
      <Fila label="Subtotal del período" monto={p.saldo} />
      <Fila
        label="Saldo a favor del período anterior"
        monto={p.saldo_favor_previo}
        signo="menos"
      />
      <div className="my-1 border-ink/20 border-t" />
      {/* "A pagar" nunca negativo: es el neto_a_pagar del backend (max(0, …)) */}
      <Fila label="A pagar" monto={p.neto_a_pagar} fuerte testId="a-pagar" />
      {hayFavorNuevo && (
        <Fila
          label="Saldo a favor que se arrastra"
          monto={p.saldo_favor_nuevo}
          tono="positivo"
        />
      )}
      {p.proximo_pago && (
        <p className="mt-3 font-sans text-apoyo text-ink-soft">
          Próximo pago: {fechaLarga(p.proximo_pago.fecha)}{" "}
          {p.proximo_pago.dias >= 0
            ? `(en ${p.proximo_pago.dias} día${p.proximo_pago.dias === 1 ? "" : "s"})`
            : `(hace ${-p.proximo_pago.dias} día${p.proximo_pago.dias === -1 ? "" : "s"})`}
        </p>
      )}
    </div>
  );
}

export function LiquidacionCard({
  liquidacion,
  hoy = new Date(),
}: {
  liquidacion: LiquidacionIva;
  /** Inyectable para pruebas deterministas; por defecto, ahora. */
  hoy?: Date;
}) {
  const p = liquidacion.periodicidad;
  const porEtiqueta = new Map(liquidacion.periodos.map((x) => [x.etiqueta, x]));
  const lista = candidatos(hoy, p);
  const actual = periodoDeHoy(hoy, p);
  const [sel, setSel] = useState(actual);

  const seleccionado = porEtiqueta.get(sel) ?? null;
  const tituloSel = lista.find((c) => c.etiqueta === sel)?.titulo ?? sel;

  return (
    <Card className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <CardTitle>Liquidación · {tituloSel}</CardTitle>
        <div className="flex flex-wrap gap-2">
          {lista.map((c) => (
            <ScenarioChip
              key={c.etiqueta}
              label={c.titulo}
              active={c.etiqueta === sel}
              onClick={() => setSel(c.etiqueta)}
            />
          ))}
        </div>
      </div>

      {seleccionado ? (
        <Desglose p={seleccionado} />
      ) : (
        <p className="py-6 text-center font-sans text-cuerpo text-ink-soft">
          Sin facturas cargadas en este período.
        </p>
      )}
    </Card>
  );
}
