// components/proyeccion/MesEnCursoCallout.tsx
//
// El mes en curso — completitud (B13) + el TERMÓMETRO de desviación (P6 del ciclo
// mensual, CEO 2026-08-23):
//
//   "El mes en curso son proyecciones basadas en los objetivos planteados y lo que
//    podemos hacer es revisar la realidad para ver qué desviación o qué precisión
//    estamos logrando con los objetivos planteados."
//
// La curva de arriba muestra el OBJETIVO. Esto muestra la realidad AL LADO, en tres
// lecturas: colocaciones, ingreso y gasto. No toca la proyección — responde otra
// pregunta: ¿qué tan buenos son nuestros objetivos?
//
// Honestidad (R5): lo real es "al día N" y el objetivo es del MES completo, así que cada
// fila lo dice. Un dato sin cargar se muestra "sin cargar", nunca como cero — "no hay
// dato" y "cero" son cosas distintas. Ninguna cifra se calcula aquí: todas del backend.

import type Decimal from "decimal.js-light";

import { Card } from "@/components/ui/card";
import { formatCOPCompact, parseMonto } from "@/lib/money";
import type { ArranqueCaja, MesEnCurso } from "@/lib/proyeccion";

const MESES_LARGO = [
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

/** 'YYYY-MM' → 'agosto' (nombre largo para copy legible; el CEO lo lee). */
function mesLargo(mes: string): string {
  return MESES_LARGO[Number(mes.split("-")[1]) - 1] ?? mes;
}

function capitalizar(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function Cifra({ k, valor }: { k: string; valor: string }) {
  return (
    <div className="rounded-lg border border-hairline bg-surface px-3 py-2">
      <div className="text-apoyo font-semibold tracking-wide text-ink-faint uppercase">
        {k}
      </div>
      <div className="tabular mt-0.5 font-display text-cuerpo font-bold text-ink">
        {valor}
      </div>
    </div>
  );
}

/**
 * Una lectura del termómetro: qué se persigue, cuánto llevamos y qué falta. La barra
 * es geometría (`.toNumber()` solo para el ancho, regla 1); las cifras son del backend.
 */
function Lectura({
  concepto,
  objetivo,
  real,
  falta,
  pctAvance,
  nota,
}: {
  concepto: string;
  objetivo: string;
  real: string | null;
  falta: string | null;
  pctAvance: number | null;
  nota?: string;
}) {
  return (
    <div className="border-t border-hairline py-2.5 first:border-t-0 first:pt-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <span className="font-sans text-cuerpo font-semibold text-ink">
          {concepto}
        </span>
        <span className="tabular font-sans text-cuerpo text-ink-soft">
          {real === null ? (
            <span className="text-ink-faint">sin cargar</span>
          ) : (
            <>
              <span className="font-semibold text-ink">{real}</span> de{" "}
              {objetivo}
            </>
          )}
        </span>
      </div>
      {pctAvance !== null && (
        <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-surface-muted">
          <div
            className={
              pctAvance >= 100
                ? "h-full rounded-full bg-positivo"
                : "h-full rounded-full bg-cyan"
            }
            style={{ width: `${Math.min(100, Math.max(0, pctAvance))}%` }}
          />
        </div>
      )}
      <div className="mt-1 font-sans text-apoyo text-ink-faint">
        {real === null
          ? (nota ?? "Se llena al cargar los datos del mes.")
          : falta !== null
            ? `Falta ${falta} para el objetivo del mes.`
            : (nota ?? "")}
      </div>
    </div>
  );
}

export function MesEnCursoCallout({
  mesEnCurso,
  arranque,
  cajaCierre,
}: {
  mesEnCurso: MesEnCurso;
  /** Ítem 4 Kimi e75 — con qué plata ARRANCA el mes (P2) y con cuál CERRARÍA si se
   * cumple el objetivo (la caja de su fila). Opcionales: sin ellos la tarjeta queda
   * como antes (aditivo). */
  arranque?: ArranqueCaja | null;
  cajaCierre?: string;
}) {
  const mes = mesLargo(mesEnCurso.mes);
  const anio = mesEnCurso.mes.slice(0, 4);
  const resta = parseMonto(mesEnCurso.proyectado).minus(
    parseMonto(mesEnCurso.ejecutado),
  );
  const ejecutadoLbl =
    mesEnCurso.dia === null
      ? "Ejecutado (sin cargas)"
      : `Ejecutado (al día ${mesEnCurso.dia})`;

  // ── el termómetro: tres lecturas contra el objetivo del mes ──
  const metaMotos = mesEnCurso.colocaciones_meta ?? null;
  const motosReales = mesEnCurso.colocaciones_reales ?? null;
  const ingObjetivo = mesEnCurso.ingreso_proyectado ?? null;
  const ingReal = mesEnCurso.ingreso_real ?? null;

  const pct = (real: Decimal, objetivo: Decimal): number | null =>
    objetivo.isZero() ? null : real.div(objetivo).times(100).toNumber();

  const hayTermometro = metaMotos !== null || ingObjetivo !== null;

  return (
    <Card className="border-cyan/30 p-0">
      <div className="grid gap-0 sm:grid-cols-[1.4fr_1fr]">
        <div className="p-5">
          <span className="inline-flex items-center gap-2 text-apoyo font-semibold tracking-wide text-cyan uppercase">
            <span className="inline-block h-2.5 w-2.5 rounded-full bg-cyan ring-2 ring-cyan/40" />
            Mes en curso · {mes} {anio}
          </span>
          <div className="mt-3 grid grid-cols-3 gap-2">
            <Cifra
              k="Presupuesto del mes"
              valor={formatCOPCompact(mesEnCurso.proyectado)}
            />
            <Cifra
              k={ejecutadoLbl}
              valor={formatCOPCompact(mesEnCurso.ejecutado)}
            />
            <Cifra k="Resta del presupuesto" valor={formatCOPCompact(resta)} />
          </div>
          {/* Ítem 4 Kimi e75 — inicio y fin del mes, explícitos, para que la
              columna «Caja al cerrar» no deje ninguna ambigüedad. */}
          {arranque && cajaCierre && (
            <p className="mt-3 font-sans text-cuerpo text-ink">
              {capitalizar(mes)} <b>arranca</b> con{" "}
              <span className="tabular font-semibold">
                {formatCOPCompact(arranque.valor)}
              </span>
              {arranque.origen === "ciclo"
                ? " (el efectivo real del cierre anterior)"
                : " (la caja configurada en Supuestos)"}{" "}
              y <b>cerraría</b> en{" "}
              <span className="tabular font-semibold">
                {formatCOPCompact(cajaCierre)}
              </span>{" "}
              si se cumple el objetivo.
            </p>
          )}
          <p className="mt-3 border-l-[3px] border-cyan pl-3 text-cuerpo text-ink-soft">
            La gráfica proyecta el <b>objetivo</b> de {mes}. Cuando lo cierres,
            su ejecución real lo reemplaza y arrastra el resto del año.
          </p>
        </div>

        <div className="border-t border-hairline bg-surface-muted p-5 sm:border-t-0 sm:border-l">
          {hayTermometro ? (
            <>
              <span className="text-apoyo font-semibold tracking-wide text-ink-soft uppercase">
                Qué tan cerca vamos del objetivo
              </span>
              <p className="mt-0.5 font-sans text-apoyo text-ink-faint">
                {mesEnCurso.dia === null
                  ? `${mes}: aún sin movimientos cargados`
                  : `Real al día ${mesEnCurso.dia}${
                      mesEnCurso.dias_del_mes
                        ? ` de ${mesEnCurso.dias_del_mes}`
                        : ""
                    } · objetivo del mes completo`}
              </p>
              <div className="mt-2.5">
                {metaMotos !== null && (
                  <Lectura
                    concepto="Motos colocadas"
                    objetivo={`${metaMotos}`}
                    real={motosReales === null ? null : `${motosReales}`}
                    falta={
                      motosReales === null || motosReales >= metaMotos
                        ? null
                        : `${metaMotos - motosReales}`
                    }
                    pctAvance={
                      motosReales === null || metaMotos === 0
                        ? null
                        : (motosReales / metaMotos) * 100
                    }
                    nota={
                      motosReales !== null && motosReales >= metaMotos
                        ? "Objetivo cumplido."
                        : "Se actualiza con la carga semanal del cronograma."
                    }
                  />
                )}
                {ingObjetivo !== null && (
                  <Lectura
                    concepto="Ingreso recaudado"
                    objetivo={formatCOPCompact(ingObjetivo)}
                    real={ingReal === null ? null : formatCOPCompact(ingReal)}
                    falta={
                      ingReal === null ||
                      parseMonto(ingReal).gte(parseMonto(ingObjetivo))
                        ? null
                        : formatCOPCompact(
                            parseMonto(ingObjetivo).minus(parseMonto(ingReal)),
                          )
                    }
                    pctAvance={
                      ingReal === null
                        ? null
                        : pct(parseMonto(ingReal), parseMonto(ingObjetivo))
                    }
                    nota="Objetivo cumplido."
                  />
                )}
                <Lectura
                  concepto="Gasto ejecutado"
                  objetivo={formatCOPCompact(mesEnCurso.proyectado)}
                  real={formatCOPCompact(mesEnCurso.ejecutado)}
                  falta={
                    resta.isNegative()
                      ? null
                      : formatCOPCompact(resta) /* lo que queda por gastar */
                  }
                  pctAvance={pct(
                    parseMonto(mesEnCurso.ejecutado),
                    parseMonto(mesEnCurso.proyectado),
                  )}
                  nota={
                    resta.isNegative()
                      ? `Por encima del presupuesto en ${formatCOPCompact(resta.negated())}.`
                      : ""
                  }
                />
              </div>
            </>
          ) : (
            <>
              <span className="text-apoyo font-semibold tracking-wide text-ink-soft uppercase">
                Completitud del mes
              </span>
              <p className="mt-1 font-display text-cuerpo font-semibold text-ink">
                {mesEnCurso.dia === null
                  ? `${mes}: aún sin movimientos cargados`
                  : `Cargado hasta el ${mesEnCurso.dia} de ${mes}`}
              </p>
              <p className="mt-2 text-apoyo text-ink-soft">
                El mes se proyecta con{" "}
                <span className="rounded-md border border-hairline bg-surface px-1.5 py-0.5 text-ink">
                  {mesEnCurso.formula}
                </span>
              </p>
            </>
          )}
        </div>
      </div>
    </Card>
  );
}
