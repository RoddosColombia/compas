// PanelDecisiones — D1 §4: la pestaña "Decisiones" del Presupuesto.
//
// Izquierda: editor de ajustes (agregar/editar/quitar, unidades humanas, selector de
// rubro opcional, restablecer) + escenarios nombrados (cargar/guardar/eliminar).
// Derecha (sticky): tarjeta de techo de gasto + PanelImpacto (BASE → CON AJUSTES) +
// valles de la serie ajustada. Todo compute-only (simular no escribe); guardar es
// explícito. Montos como string (regla 1); el motor no se toca.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { useAuth } from "@/auth/AuthContext";
import { VallesCard } from "@/components/decisiones/VallesCard";
import { PanelImpacto } from "@/components/supuestos/PanelImpacto";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { Cargando } from "@/components/ui/cargando";
import { KpiTileV2 } from "@/components/ui/kpi-tile";
import { GRUPO_LABEL } from "@/lib/control";
import {
  type Ajuste,
  type EscenarioGuardado,
  type TechoResultado,
  crearEscenario,
  eliminarEscenario,
  listarEscenarios,
  proyectarImpactos,
  resolver,
} from "@/lib/decisiones";
import { formatMesCorto } from "@/lib/money";
import { agruparRubros, listarRubros } from "@/lib/rubros";
import {
  esMontoHumanoValido,
  esPctValido,
  fraccionAPct,
  montoACanonico,
  montoAHumano,
  pctAFraccion,
} from "@/lib/unidades";

const HORIZONTE = 60; // el del juicio (spec §5); los gráficos muestran 18
const DEBOUNCE_MS = 500;

function ajusteVacio(): Ajuste {
  return {
    nombre: "",
    naturaleza: "gasto",
    modo: "absoluto",
    valor: "0",
    mes_inicio: "",
    mes_fin: null,
    rubro_id: null,
  };
}

function ajusteValido(a: Ajuste): boolean {
  if (!a.nombre.trim() || !/^\d{4}-\d{2}$/.test(a.mes_inicio)) return false;
  return a.modo === "porcentaje"
    ? esPctValido(fraccionAPct(a.valor))
    : esMontoHumanoValido(montoAHumano(a.valor));
}

export function PanelDecisiones({
  mesInicio,
}: {
  mesInicio?: string; // 'YYYY-MM' del selector de la Cabina; default = mes vigente
}) {
  const { puede } = useAuth();
  const puedeGestionar = puede("proyeccion:gestionar");
  const qc = useQueryClient();

  const [ajustes, setAjustes] = useState<Ajuste[]>([]);
  const [debounced, setDebounced] = useState<Ajuste[]>([]);
  const [escenarioId, setEscenarioId] = useState<string>("");
  const [nombreNuevo, setNombreNuevo] = useState("");

  const validos = useMemo(() => ajustes.filter(ajusteValido), [ajustes]);
  const validosKey = useMemo(() => JSON.stringify(validos), [validos]);
  const hayCambios = validos.length > 0;

  // Debounce: recalcula el impacto sin castigar cada tecla (patrón C3).
  // biome-ignore lint/correctness/useExhaustiveDependencies: se dispara por validosKey
  useEffect(() => {
    const t = setTimeout(() => setDebounced(validos), DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [validosKey]);

  const params = { horizonteMeses: HORIZONTE, mesInicio };

  const impactos = useQuery({
    queryKey: ["impactos", JSON.stringify(debounced), mesInicio],
    queryFn: () => proyectarImpactos(debounced, params),
    enabled: puedeGestionar,
  });

  const techo = useQuery({
    queryKey: ["resolver", "techo", JSON.stringify(debounced), mesInicio],
    queryFn: () =>
      resolver({ objetivo: "techo_gasto", ajustes: debounced }, params),
    enabled: puedeGestionar,
  });

  const escenarios = useQuery({
    queryKey: ["escenarios"],
    queryFn: listarEscenarios,
    enabled: puedeGestionar,
  });

  const guardar = useMutation({
    mutationFn: () =>
      crearEscenario({ nombre: nombreNuevo.trim(), ajustes: validos }),
    onSuccess: (e) => {
      setNombreNuevo("");
      setEscenarioId(e.id);
      qc.invalidateQueries({ queryKey: ["escenarios"] });
    },
  });

  const borrar = useMutation({
    mutationFn: (id: string) => eliminarEscenario(id),
    onSuccess: () => {
      setEscenarioId("");
      qc.invalidateQueries({ queryKey: ["escenarios"] });
    },
  });

  if (!puedeGestionar) {
    return (
      <AlertBanner variant="warn">
        La pestaña Decisiones simula cambios sobre la proyección; requiere el
        permiso de gestión de proyección.
      </AlertBanner>
    );
  }

  const cargarEscenario = (id: string) => {
    setEscenarioId(id);
    const e = escenarios.data?.find((x) => x.id === id);
    if (e) setAjustes(e.ajustes.map((a) => ({ ...a })));
  };

  const valles = impactos.data?.valles_ajustada ?? [];

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      {/* ── Izquierda: ajustes + escenarios ── */}
      <div className="flex flex-col gap-4">
        <EscenarioBar
          escenarios={escenarios.data ?? []}
          escenarioId={escenarioId}
          onCargar={cargarEscenario}
          onEliminar={(id) => borrar.mutate(id)}
          nombreNuevo={nombreNuevo}
          onNombre={setNombreNuevo}
          onGuardar={() => guardar.mutate()}
          puedeGuardar={hayCambios && nombreNuevo.trim().length > 0}
          guardando={guardar.isPending}
          errorGuardar={guardar.isError}
        />
        <AjustesEditor ajustes={ajustes} onChange={setAjustes} />
      </div>

      {/* ── Derecha: techo + impacto + valles ── */}
      <div className="flex flex-col gap-4 lg:sticky lg:top-4 lg:self-start">
        <TechoCard
          techo={
            techo.data?.objetivo === "techo_gasto" ? techo.data : undefined
          }
          cargando={techo.isFetching}
        />
        {/* PanelImpacto + valles */}
        <PanelImpacto
          vigente={impactos.data?.base}
          propuesto={impactos.data?.ajustada}
          calculando={impactos.isFetching}
          error={impactos.isError}
          hayCambios={hayCambios}
          titulo="Impacto de tus ajustes"
          etiquetaVigente="Base"
          etiquetaPropuesto="Con tus ajustes"
          hintVacio="Agrega un ajuste (p. ej. arriendo +$3 M desde sep-2026) y aquí verás la nueva curva, el valle movido y el delta — antes de guardar nada."
        />
        <VallesCard valles={valles} cargando={impactos.isFetching} />
      </div>
    </div>
  );
}

// ── Editor de ajustes ────────────────────────────────────────────────────────
function AjustesEditor({
  ajustes,
  onChange,
}: {
  ajustes: Ajuste[];
  onChange: (a: Ajuste[]) => void;
}) {
  const rubros = useQuery({ queryKey: ["rubros"], queryFn: listarRubros });
  const grupos = useMemo(
    () => agruparRubros((rubros.data ?? []).filter((r) => r.activo)),
    [rubros.data],
  );

  const set = (i: number, patch: Partial<Ajuste>) =>
    onChange(ajustes.map((a, j) => (j === i ? { ...a, ...patch } : a)));

  return (
    <Card className="flex flex-col gap-3 p-5">
      <div className="flex items-center justify-between">
        <CardTitle>Ajustes</CardTitle>
        {ajustes.length > 0 && (
          <button
            type="button"
            className="font-sans text-apoyo text-ink-soft underline hover:text-ink"
            onClick={() => onChange([])}
          >
            Restablecer
          </button>
        )}
      </div>

      {ajustes.length === 0 && (
        <p className="font-sans text-cuerpo text-ink-soft">
          Sin ajustes: la proyección es la base. Agrega uno para simular una
          decisión.
        </p>
      )}

      <div className="flex flex-col gap-4">
        {ajustes.map((a, i) => (
          <AjusteFila
            // biome-ignore lint/suspicious/noArrayIndexKey: filas efímeras del editor
            key={i}
            ajuste={a}
            grupos={grupos}
            onChange={(patch) => set(i, patch)}
            onQuitar={() => onChange(ajustes.filter((_, j) => j !== i))}
          />
        ))}
      </div>

      <Button
        type="button"
        variant="outline"
        size="sm"
        className="self-start"
        onClick={() => onChange([...ajustes, ajusteVacio()])}
      >
        + Agregar ajuste
      </Button>
    </Card>
  );
}

function AjusteFila({
  ajuste,
  grupos,
  onChange,
  onQuitar,
}: {
  ajuste: Ajuste;
  grupos: Map<string, { id: string; nombre: string }[]>;
  onChange: (patch: Partial<Ajuste>) => void;
  onQuitar: () => void;
}) {
  const esPct = ajuste.modo === "porcentaje";
  const valorHumano = esPct
    ? fraccionAPct(ajuste.valor)
    : montoAHumano(ajuste.valor);
  const onValor = (v: string) =>
    onChange({ valor: esPct ? pctAFraccion(v) : montoACanonico(v) });

  return (
    <div className="flex flex-col gap-2 rounded-md border border-hairline p-3">
      <div className="flex items-center gap-2">
        <input
          className="min-w-0 flex-1 rounded-md border border-hairline px-2 py-1 font-sans text-cuerpo"
          placeholder="Nombre (p. ej. Arriendo sede nueva)"
          value={ajuste.nombre}
          onChange={(e) => onChange({ nombre: e.target.value })}
          aria-label="Nombre del ajuste"
        />
        <button
          type="button"
          className="font-sans text-apoyo text-ink-soft hover:text-critico"
          onClick={onQuitar}
          aria-label="Quitar ajuste"
        >
          Quitar
        </button>
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Campo label="Naturaleza">
          <select
            className="w-full rounded-md border border-hairline px-2 py-1 font-sans text-cuerpo"
            value={ajuste.naturaleza}
            onChange={(e) =>
              onChange({ naturaleza: e.target.value as Ajuste["naturaleza"] })
            }
          >
            <option value="gasto">Gasto</option>
            <option value="ingreso">Ingreso</option>
          </select>
        </Campo>
        <Campo label="Modo">
          <select
            className="w-full rounded-md border border-hairline px-2 py-1 font-sans text-cuerpo"
            value={ajuste.modo}
            onChange={(e) =>
              onChange({ modo: e.target.value as Ajuste["modo"] })
            }
          >
            <option value="absoluto">Monto fijo</option>
            <option value="porcentaje">Porcentaje</option>
          </select>
        </Campo>
        <Campo label={esPct ? "Porcentaje (%)" : "Monto mensual"}>
          <input
            className="w-full rounded-md border border-hairline px-2 py-1 font-sans text-cuerpo tabular"
            value={valorHumano}
            onChange={(e) => onValor(e.target.value)}
            aria-label="Valor del ajuste"
            inputMode="decimal"
          />
        </Campo>
        <Campo label="Rubro (opcional)">
          <select
            className="w-full rounded-md border border-hairline px-2 py-1 font-sans text-cuerpo"
            value={ajuste.rubro_id ?? ""}
            onChange={(e) => onChange({ rubro_id: e.target.value || null })}
          >
            <option value="">— sin rubro —</option>
            {[...grupos.entries()].map(([g, rs]) => (
              <optgroup key={g} label={GRUPO_LABEL[g] ?? g}>
                {rs.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.nombre}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </Campo>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <Campo label="Desde el mes">
          <input
            type="month"
            className="w-full rounded-md border border-hairline px-2 py-1 font-sans text-cuerpo"
            value={ajuste.mes_inicio}
            onChange={(e) => onChange({ mes_inicio: e.target.value })}
            aria-label="Mes inicio"
          />
        </Campo>
        <Campo label="Hasta (opcional)">
          <input
            type="month"
            className="w-full rounded-md border border-hairline px-2 py-1 font-sans text-cuerpo"
            value={ajuste.mes_fin ?? ""}
            onChange={(e) => onChange({ mes_fin: e.target.value || null })}
            aria-label="Mes fin"
          />
        </Campo>
      </div>
    </div>
  );
}

function Campo({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    // biome-ignore lint/a11y/noLabelWithoutControl: el control (input/select) va como children
    <label className="flex flex-col gap-1 font-sans text-apoyo text-ink-faint">
      <span>{label}</span>
      {children}
    </label>
  );
}

// ── Escenarios nombrados ──────────────────────────────────────────────────────
function EscenarioBar({
  escenarios,
  escenarioId,
  onCargar,
  onEliminar,
  nombreNuevo,
  onNombre,
  onGuardar,
  puedeGuardar,
  guardando,
  errorGuardar,
}: {
  escenarios: EscenarioGuardado[];
  escenarioId: string;
  onCargar: (id: string) => void;
  onEliminar: (id: string) => void;
  nombreNuevo: string;
  onNombre: (v: string) => void;
  onGuardar: () => void;
  puedeGuardar: boolean;
  guardando: boolean;
  errorGuardar: boolean;
}) {
  return (
    <Card className="flex flex-col gap-3 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <select
          className="min-w-0 flex-1 rounded-md border border-hairline px-2 py-1 font-sans text-cuerpo"
          value={escenarioId}
          onChange={(e) => onCargar(e.target.value)}
          aria-label="Cargar escenario"
        >
          <option value="">— cargar escenario —</option>
          {escenarios.map((e) => (
            <option key={e.id} value={e.id}>
              {e.nombre}
            </option>
          ))}
        </select>
        {escenarioId && (
          <button
            type="button"
            className="font-sans text-apoyo text-ink-soft hover:text-critico"
            onClick={() => onEliminar(escenarioId)}
          >
            Eliminar
          </button>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <input
          className="min-w-0 flex-1 rounded-md border border-hairline px-2 py-1 font-sans text-cuerpo"
          placeholder="Guardar estos ajustes como…"
          value={nombreNuevo}
          onChange={(e) => onNombre(e.target.value)}
          aria-label="Nombre del escenario"
        />
        <Button
          type="button"
          variant="cyan"
          size="sm"
          onClick={onGuardar}
          disabled={!puedeGuardar || guardando}
        >
          Guardar
        </Button>
      </div>
      {errorGuardar && (
        <AlertBanner variant="warn">
          No se pudo guardar el escenario (¿nombre repetido?). Cambia el nombre
          e intenta de nuevo.
        </AlertBanner>
      )}
    </Card>
  );
}

// ── Tarjeta de techo de gasto (§4.7) ──────────────────────────────────────────
function TechoCard({
  techo,
  cargando,
}: {
  techo: TechoResultado | undefined;
  cargando: boolean;
}) {
  if (cargando && !techo) return <Cargando variante="card" />;
  if (!techo) return null;
  if (!techo.hay_holgura) {
    return (
      <KpiTileV2
        label="Techo de gasto mensual sostenido"
        valor="0"
        valorTexto="Sin margen"
        tono="critico"
        contexto={`El valle de ${formatMesCorto(techo.valle_limitante_mes)} ya está en el límite: no hay espacio para sumar gasto permanente sin perforar.`}
      />
    );
  }
  return (
    <KpiTileV2
      label="Techo de gasto mensual sostenido"
      valor={techo.techo_mensual}
      tono="atencion"
      contexto={`Lo máximo que puedes sumar CADA mes de aquí en adelante sin que ningún valle baje del umbral (no es un cupo de un solo mes). Lo limita ${formatMesCorto(techo.valle_limitante_mes)}.`}
    />
  );
}
