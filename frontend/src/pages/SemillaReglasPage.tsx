// frontend/src/pages/SemillaReglasPage.tsx
//
// RF-F1 — Semilla de reglas: aprende reglas de clasificación de la curaduría real
// (movimientos que ya se clasificaron a mano) y deja SEMBRAR las elegidas. Se crean
// APRENDIDAS e INACTIVAS: no clasifican nada hasta que se aprueben en Reglas (§1.9).
// Las de riesgo (nombre propio / patrón de 3 letras) vienen desmarcadas. La autoridad
// real la impone el backend (reglas:gestionar); aquí solo se ofrece el flujo.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "@/auth/AuthContext";
import { PageHeader } from "@/components/layout/PageHeader";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Cargando } from "@/components/ui/cargando";
import { ErrorEstado } from "@/components/ui/error-estado";
import {
  type ResultadoSembrar,
  type SemillaPropuesta,
  obtenerSemilla,
  sembrarSemilla,
} from "@/lib/reglas";

const NOMBRE_RE = /[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+ [A-ZÁÉÍÓÚÑ][a-záéíóúñ]+/;

/** Banderas de riesgo (mismas que el reporte de revisión): patrón corto o nombre propio. */
function riesgos(p: SemillaPropuesta): string[] {
  const r: string[] = [];
  if (p.patron.length <= 3) r.push("3 letras");
  const esNombre = p.ejemplos.some((ej) => {
    const m = ej.match(NOMBRE_RE);
    if (m?.[0].toLowerCase().split(" ").includes(p.patron)) return true;
    return (
      /(?:recibido de|env[ií]o a|pago) /i.test(ej) && /[A-ZÁÉÍÓÚÑ]/.test(ej)
    );
  });
  if (esNombre) r.push("nombre propio");
  return r;
}

const clave = (p: SemillaPropuesta) => `${p.patron}|${p.tipo_flujo}`;

export default function SemillaReglasPage() {
  const { puede } = useAuth();
  const gestiona = puede("reglas:gestionar");
  const qc = useQueryClient();
  const [sel, setSel] = useState<Set<string> | null>(null);
  const [hecho, setHecho] = useState<ResultadoSembrar | null>(null);

  const reporte = useQuery({
    queryKey: ["reglas", "semilla"],
    queryFn: () => obtenerSemilla(),
  });

  // seleccionables = propuestas que no chocan con una regla activa
  const nuevas = useMemo(
    () => (reporte.data?.propuestas ?? []).filter((p) => !p.colisiona),
    [reporte.data],
  );

  // estado inicial: seguras marcadas, riesgosas no
  const seleccion = useMemo(() => {
    if (sel) return sel;
    return new Set(nuevas.filter((p) => riesgos(p).length === 0).map(clave));
  }, [sel, nuevas]);

  const grupos = useMemo(() => {
    const g = new Map<string, SemillaPropuesta[]>();
    for (const p of nuevas) {
      const arr = g.get(p.rubro) ?? [];
      arr.push(p);
      g.set(p.rubro, arr);
    }
    return [...g.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [nuevas]);

  const sembrar = useMutation({
    mutationFn: () => {
      const elegidas = nuevas
        .filter((p) => seleccion.has(clave(p)))
        .map((p) => ({
          patron: p.patron,
          rubro_id: p.rubro_id,
          tipo_flujo: p.tipo_flujo,
        }));
      return sembrarSemilla(elegidas);
    },
    onSuccess: (r) => {
      setHecho(r);
      qc.invalidateQueries({ queryKey: ["reglas"] });
    },
  });

  function toggle(k: string) {
    const next = new Set(seleccion);
    if (next.has(k)) next.delete(k);
    else next.add(k);
    setSel(next);
  }
  function marcar(keys: string[], on: boolean) {
    const next = new Set(seleccion);
    for (const k of keys) {
      if (on) next.add(k);
      else next.delete(k);
    }
    setSel(next);
  }

  if (reporte.isLoading) return <Cargando />;
  if (reporte.isError)
    return (
      <ErrorEstado
        mensaje="No se pudo cargar la semilla de reglas."
        onReintentar={() => reporte.refetch()}
      />
    );

  const seguras = nuevas.filter((p) => riesgos(p).length === 0).length;
  const nSel = nuevas.filter((p) => seleccion.has(clave(p))).length;

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        titulo="Semilla de reglas"
        descripcion={`${nuevas.length} reglas aprendidas de ${reporte.data?.total_movimientos ?? 0} movimientos que ya clasificaste. Marca cuáles sembrar — las de riesgo vienen desmarcadas.`}
      />

      {!gestiona && (
        <AlertBanner variant="warn">
          Necesitas el permiso <b>reglas:gestionar</b> para sembrar.
        </AlertBanner>
      )}

      {hecho && (
        <AlertBanner variant="ok">
          Sembradas <b>{hecho.creadas}</b> reglas (inactivas) ·{" "}
          {hecho.ya_existian} ya existían · {hecho.errores} con error. Ahora
          apruébalas en{" "}
          <Link to="/reglas" className="underline">
            Reglas
          </Link>{" "}
          para que empiecen a clasificar.
        </AlertBanner>
      )}

      <div className="flex flex-wrap items-center gap-2 text-sm text-ink-soft">
        <span className="rounded-full bg-surface-muted px-2.5 py-0.5 font-semibold">
          {nuevas.length} propuestas
        </span>
        <span className="rounded-full bg-positivo/10 px-2.5 py-0.5 font-semibold text-positivo">
          {seguras} seguras
        </span>
        <span className="rounded-full bg-atencion/10 px-2.5 py-0.5 font-semibold text-atencion">
          {nuevas.length - seguras} a revisar
        </span>
      </div>

      <div className="flex flex-col gap-3">
        {grupos.map(([rubro, filas]) => {
          const keys = filas.map(clave);
          const todas = keys.every((k) => seleccion.has(k));
          return (
            <Card key={rubro} className="overflow-hidden p-0">
              <div className="flex items-center gap-2 border-b border-hairline bg-surface-muted px-3 py-2">
                <input
                  type="checkbox"
                  checked={todas}
                  onChange={(e) => marcar(keys, e.target.checked)}
                  aria-label={`Todo ${rubro}`}
                />
                <span className="font-display text-sm font-semibold text-ink">
                  {rubro}
                </span>
                <span className="tabular text-xs text-ink-faint">
                  {filas.filter((p) => seleccion.has(clave(p))).length}/
                  {filas.length}
                </span>
              </div>
              <ul>
                {filas.map((p) => {
                  const rs = riesgos(p);
                  return (
                    <li
                      key={clave(p)}
                      className="flex items-center gap-3 border-b border-hairline/60 px-3 py-1.5 last:border-0"
                    >
                      <input
                        type="checkbox"
                        checked={seleccion.has(clave(p))}
                        onChange={() => toggle(clave(p))}
                        aria-label={p.patron}
                      />
                      <code className="font-mono text-sm text-ink">
                        {p.patron}
                      </code>
                      {rs.map((r) => (
                        <span
                          key={r}
                          className="rounded bg-atencion/10 px-1.5 py-0.5 text-[0.6rem] font-semibold uppercase text-atencion"
                        >
                          {r}
                        </span>
                      ))}
                      <span className="min-w-0 flex-1 truncate text-xs italic text-ink-faint">
                        {p.ejemplos[0] ? `«${p.ejemplos[0]}»` : ""}
                      </span>
                      <span className="tabular text-xs text-ink-soft">
                        {p.tipo_flujo} · n={p.evidencia}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </Card>
          );
        })}
      </div>

      <div className="sticky bottom-0 flex items-center gap-3 border-t border-hairline bg-surface/95 py-3">
        <span className="font-display text-base font-semibold text-ink">
          {nSel} seleccionadas
        </span>
        <div className="flex-1" />
        <Button
          variant="ghost"
          size="sm"
          onClick={() => marcar(nuevas.map(clave), false)}
        >
          Ninguna
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() =>
            setSel(
              new Set(nuevas.filter((p) => riesgos(p).length === 0).map(clave)),
            )
          }
        >
          Solo seguras
        </Button>
        <Button
          variant="cyan"
          size="sm"
          disabled={!gestiona || nSel === 0 || sembrar.isPending}
          onClick={() => sembrar.mutate()}
        >
          {sembrar.isPending ? "Sembrando…" : `Sembrar ${nSel}`}
        </Button>
      </div>
    </div>
  );
}
