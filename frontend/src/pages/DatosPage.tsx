// frontend/src/pages/DatosPage.tsx — "Supuestos" (reescrita en C3)
//
// El editor de supuestos con IMPACTO EN VIVO (C3 §2): editar nunca toca el
// vigente — el formulario es un BORRADOR local; con cada cambio válido se llama
// al preview compute-only (debounce 600 ms) y el panel derecho muestra VIGENTE →
// CON TUS CAMBIOS antes de guardar. Unidades humanas en la superficie (5 % y no
// 0.05; 1.200.000 con separador; meses calendario) — al backend siempre viajan
// los strings canónicos de la regla 1 (lib/unidades, tests de ida y vuelta).
// Validación en tres niveles: error (bloquea) / advertencia (pide confirmación)
// / nota (informa). Cada campo declara su contrato ⓘ (qué es, qué incluye, a qué
// alimenta — Apéndice A). Bloque ⑦ = CR-002: costos de alistamiento por moto
// vendida, desglosados por componente (el motor recibe la Σ de los activos,
// server-side). Guardar = diálogo con el diff + nota al audit log.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Decimal from "decimal.js-light";
import { type FormEvent, useEffect, useMemo, useRef, useState } from "react";

import { useAuth } from "@/auth/AuthContext";
import { PageHeader } from "@/components/layout/PageHeader";
import { PanelImpacto } from "@/components/supuestos/PanelImpacto";
import { Tornado } from "@/components/supuestos/Tornado";
import { AlertBanner } from "@/components/ui/alert-banner";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { Cargando } from "@/components/ui/cargando";
import { EstadoVacio } from "@/components/ui/estado-vacio";
import { ApiError } from "@/lib/api";
import {
  type ResumenCarga,
  cargarCronograma,
  obtenerSerieCartera,
} from "@/lib/carteraPrevia";
import {
  type ModeloCrearInput,
  type ModeloEditarInput,
  type ModeloMoto,
  crearModelo,
  desactivarModelo,
  editarModelo,
  listarModelos,
  reactivarModelo,
} from "@/lib/modelosMoto";
import { formatCOP, formatFecha } from "@/lib/money";
import {
  type CamposParametros,
  type ComponenteAlistamiento,
  type Parametros,
  guardarParametros,
  obtenerParametros,
  obtenerSensibilidad,
  previewProyeccion,
} from "@/lib/parametros";
import { obtenerProyeccion } from "@/lib/proyeccion";
import {
  esMontoHumanoValido,
  esPctValido,
  fraccionAPct,
  indiceAMes,
  mesAIndice,
  montoACanonico,
  montoAHumano,
  pctAFraccion,
  pctAnualEquivalente,
  resumenHorizonte,
} from "@/lib/unidades";

// ── Definición de campos: unidad humana + contrato ⓘ (Apéndice A) ───────────

type Unidad = "money" | "pct" | "int" | "dias" | "meses" | "mesCal";

interface CampoDef {
  key: string;
  label: string;
  unidad: Unidad;
  contrato: string;
}

interface BloqueDef {
  titulo: string;
  campos: CampoDef[];
}

// Bloques en ORDEN DE IMPACTO (no alfabético) — §2.
const BLOQUES: BloqueDef[] = [
  {
    titulo: "① Caja y mínimo de caja",
    campos: [
      {
        key: "caja_minima",
        label: "Mínimo de caja",
        unidad: "money",
        contrato:
          "La línea roja: si la caja proyectada baja de aquí, COMPAS lo marca como una baja del mínimo de caja. Es el mínimo operativo que decidiste sostener.",
      },
      {
        key: "caja_inicial",
        label: "Caja inicial",
        unidad: "money",
        contrato:
          "El punto de partida de la proyección. Con el ciclo mensual corriendo, se ancla sola a la caja real del último cierre.",
      },
    ],
  },
  {
    titulo: "② Colocación y crecimiento",
    campos: [
      {
        key: "motos_base",
        label: "Motos base / mes",
        unidad: "int",
        contrato:
          "La colocación arranca en este número y crece el % mensual, compuesto (85 y 5 % → 89, 93, 98…).",
      },
      {
        key: "crec_pct_mensual",
        label: "Crecimiento",
        unidad: "pct",
        contrato:
          "La colocación crece este % cada mes, compuesto. El crecimiento compuesto es potente: revisa el equivalente anual.",
      },
      {
        key: "horizonte_meses",
        label: "Horizonte",
        unidad: "meses",
        contrato:
          "Hasta dónde proyecta el motor por defecto. El mínimo de caja del norte (may-2027) debe quedar siempre adentro.",
      },
    ],
  },
  {
    titulo: "③ Cartera y mora",
    campos: [
      {
        key: "pct_mora",
        label: "Mora",
        unidad: "pct",
        contrato:
          "Del recaudo esperado, cuánto NO llega en el mes. La provisión de cartera se calcula aparte y NO resta caja (caja veraz).",
      },
      {
        key: "pct_recuperacion",
        label: "Recuperación",
        unidad: "pct",
        contrato: "De lo que cayó en mora, cuánto se recupera después.",
      },
      {
        key: "meses_rezago_recuperacion",
        label: "La recuperación llega después de",
        unidad: "meses",
        contrato:
          "La mora es diferimiento, no pérdida: el dinero vuelve, pero más tarde. Con 1 mes, lo que cae en mora este mes se recupera el siguiente. Con 0 se recupera el mismo mes (más optimista y menos realista).",
      },
      {
        key: "pct_default",
        label: "Incumplimiento (cartera perdida)",
        unidad: "pct",
        contrato: "Cuánto del recaudo esperado se pierde definitivamente.",
      },
      {
        key: "pct_provision",
        label: "Provisión de cartera (contable, no afecta la caja)",
        unidad: "pct",
        contrato: "Reserva contable informativa. NO entra al flujo de caja.",
      },
      {
        key: "pct_aval_recaudo",
        label: "Fondo AVAL propio (autoseguro)",
        unidad: "pct",
        contrato:
          "Reserva mensual para robo o siniestro, como % del recaudo de cuotas. A diferencia de la provisión, esta SÍ sale de la caja cada mes. En 0 % no existe.",
      },
      {
        key: "pct_prefondeo_iva",
        label: "Prefondeo del IVA",
        unidad: "pct",
        contrato:
          "Qué parte del IVA por pagar se va reservando mes a mes dentro del período. Al 100 % el fondo llega completo a la fecha DIAN; con menos, el resto golpea la caja el mes del pago.",
      },
    ],
  },
  {
    titulo: "④ Gastos",
    campos: [
      {
        key: "gastos_fijos",
        label: "Gastos fijos / mes",
        unidad: "money",
        contrato:
          "Los gastos que existen aunque no se venda una sola moto. La plantilla de Gastos recurrentes es su detalle informativo.",
      },
      {
        key: "gps_moto",
        label: "GPS mensual por moto",
        unidad: "money",
        contrato: "El costo recurrente del GPS por moto activa en cartera.",
      },
    ],
  },
  {
    titulo: "⑤ Inventario Auteco",
    campos: [
      {
        key: "adelanto_auteco",
        label: "Adelanto por moto",
        unidad: "money",
        contrato:
          "Anticipo por moto pactado con Auteco. En $ 0 por decisión del 26-jul-2026: sin adelantos mientras no los exijan.",
      },
      {
        key: "plazo_auteco_dias",
        label: "Plazo de pago",
        unidad: "dias",
        contrato:
          "El lote se paga a los N días; junto con la base y la tasa define cuánto y cuándo golpea el inventario a la caja.",
      },
      {
        key: "base_auteco_dias",
        label: "Días base de financiación",
        unidad: "dias",
        contrato:
          "Días de referencia del costo de financiación del lote (la espera que se financia).",
      },
      {
        key: "tasa_auteco",
        label: "Tasa de financiación",
        unidad: "pct",
        contrato:
          "El costo mensual de esperar el plazo: la financiación del inventario Auteco.",
      },
    ],
  },
  {
    titulo: "⑥ Deuda",
    campos: [
      {
        key: "deuda",
        label: "Cuota de deuda",
        unidad: "money",
        contrato:
          "El servicio mensual de la deuda con inversionistas: cuánto sale cada mes.",
      },
      {
        key: "tasa_deuda",
        label: "Tasa de deuda",
        unidad: "pct",
        contrato: "La tasa mensual del servicio de la deuda.",
      },
      {
        key: "mes_inicio_deuda",
        label: "Mes de inicio",
        unidad: "mesCal",
        contrato:
          "Desde qué mes calendario empieza a salir la cuota (el índice interno lo deriva COMPAS).",
      },
      {
        key: "meses_deuda",
        label: "Duración",
        unidad: "meses",
        contrato: "Por cuántos meses sale la cuota.",
      },
    ],
  },
];

const CONTRATO_ALISTAMIENTO =
  "Todo lo que RODDOS paga por alistar cada moto vendida: matrícula (trámite), instalación del GPS y SOAT. Configurable por componente; la proyección resta la suma de los activos.";

const CONTRATO_CUOTA_INICIAL =
  "Lo que el cliente paga al llevarse la moto, COMPLETO (incluye lo que se le cobra por matrícula). Los costos reales de matrícula, GPS y SOAT salen aparte, por Costos de alistamiento.";

// Umbrales de la validación de 3 niveles (§2) — constantes, no números mágicos.
const ADV_CRECIMIENTO_PCT = 3; // % mensual
const ADV_MORA_PCT = 10; // %
const ADV_CAMBIO_RELATIVO = 0.5; // ±50 % vs. vigente
const HORIZONTE_MIN = 1;
const HORIZONTE_MAX = 180;
const PREVIEW_HORIZONTE = 60; // el juicio mira lejos (patrón F1)
const DEBOUNCE_MS = 600;

function hoyMes(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function hoyISO(): string {
  const d = new Date();
  const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}

// ── humano ↔ canónico por unidad ─────────────────────────────────────────────

function aHumano(
  unidad: Unidad,
  canonico: string | number,
  ref: string,
): string {
  switch (unidad) {
    case "money":
      return montoAHumano(String(canonico));
    case "pct":
      return fraccionAPct(String(canonico));
    case "mesCal":
      return indiceAMes(Number(canonico), ref);
    default:
      return String(canonico);
  }
}

function aCanonico(
  unidad: Unidad,
  humano: string,
  ref: string,
): string | number {
  switch (unidad) {
    case "money":
      return montoACanonico(humano);
    case "pct":
      return pctAFraccion(humano);
    case "mesCal":
      return mesAIndice(humano, ref);
    default:
      return Number(humano);
  }
}

const CAMPOS: CampoDef[] = BLOQUES.flatMap((b) => b.campos);

export default function DatosPage() {
  const { puede } = useAuth();
  const puedeGestionar = puede("proyeccion:gestionar");
  const q = useQuery({ queryKey: ["parametros"], queryFn: obtenerParametros });

  return (
    <div className="flex flex-col gap-6">
      {q.isLoading && <Cargando variante="card" />}
      {q.data === null && !q.isLoading && (
        <>
          <PageHeader
            titulo="Supuestos"
            descripcion="Los supuestos que alimentan el motor. Es el cimiento: sin ellos no hay caja proyectada."
          />
          <EstadoVacio
            mensaje="Aún no hay supuestos configurados. Sigue la guía de configuración del motor para cargarlos por primera vez."
            quien="financiero o admin"
          />
          <ModelosPanel puedeGestionar={puedeGestionar} />
        </>
      )}
      {q.data && <Editor vigente={q.data} puedeGestionar={puedeGestionar} />}
    </div>
  );
}

// ── El editor con borrador + impacto ─────────────────────────────────────────

function Editor({
  vigente,
  puedeGestionar,
}: {
  vigente: Parametros;
  puedeGestionar: boolean;
}) {
  const qc = useQueryClient();
  const ref = hoyMes();

  const humanoDe = (p: Parametros): Record<string, string> => {
    const out: Record<string, string> = {};
    for (const c of CAMPOS) {
      out[c.key] = aHumano(
        c.unidad,
        p[c.key as keyof Parametros] as never,
        ref,
      );
    }
    return out;
  };
  const compsDe = (p: Parametros): ComponenteAlistamiento[] =>
    (p.componentes_alistamiento ?? []).map((c) => ({
      ...c,
      valor: montoAHumano(c.valor),
    }));

  const [borr, setBorr] = useState<Record<string, string>>(() =>
    humanoDe(vigente),
  );
  const [comps, setComps] = useState<ComponenteAlistamiento[]>(() =>
    compsDe(vigente),
  );
  // FIX-L: rampa de colocación por mes (YYYY-MM → unidades). Editable en Supuestos.
  const [rampa, setRampa] = useState<Record<string, number>>(
    () => vigente.rampa_unidades ?? {},
  );
  // SUP-1: segundo tramo de crecimiento (opcional). Se maneja como bloque aparte —
  // igual que componentes y rampa — porque AMBOS campos vacíos = "sin tramo 2"
  // (null/null), algo que el mapa genérico de CAMPOS no sabe expresar.
  const tramo2De = (p: Parametros) => ({
    tasa:
      p.crec_pct_mensual_2 !== null && p.crec_pct_mensual_2 !== undefined
        ? fraccionAPct(p.crec_pct_mensual_2)
        : "",
    corte: p.crec_mes_corte ? String(p.crec_mes_corte) : "",
  });
  const [tramo2, setTramo2] = useState(() => tramo2De(vigente));
  // biome-ignore lint/correctness/useExhaustiveDependencies: re-sincronizar SOLO cuando cambia la vigencia
  useEffect(() => {
    setBorr(humanoDe(vigente));
    setComps(compsDe(vigente));
    setRampa(vigente.rampa_unidades ?? {});
    setTramo2(tramo2De(vigente));
  }, [vigente.id, vigente.modificado_por]);

  const modelos = useQuery({
    queryKey: ["modelos-moto"],
    queryFn: () => listarModelos(),
  });

  // ── validación en 3 niveles ──
  const validacion = useMemo(
    () => validar(borr, comps, vigente, modelos.data ?? [], ref, tramo2),
    [borr, comps, vigente, modelos.data, ref, tramo2],
  );
  const sinErrores = Object.keys(validacion.errores).length === 0;

  // ── canónico + cambios ──
  const canon = useMemo<CamposParametros | null>(() => {
    if (!sinErrores) return null;
    try {
      return canonicalizar(borr, comps, rampa, ref, tramo2);
    } catch {
      return null;
    }
  }, [borr, comps, rampa, ref, sinErrores, tramo2]);

  const canonVigente = useMemo(() => aCampos(vigente), [vigente]);
  const canonJson = canon ? JSON.stringify(canon) : null;
  const hayCambios =
    canonJson !== null && canonJson !== JSON.stringify(canonVigente);
  const nCambios = useMemo(
    () => (canon ? contarCambios(canon, canonVigente) : 0),
    [canon, canonVigente],
  );

  // ── preview con debounce (la joya) ──
  const [previewJson, setPreviewJson] = useState<string | null>(null);
  useEffect(() => {
    if (!hayCambios || !canonJson) {
      setPreviewJson(null);
      return;
    }
    const t = setTimeout(() => setPreviewJson(canonJson), DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [canonJson, hayCambios]);

  const preview = useQuery({
    queryKey: ["preview", previewJson],
    queryFn: () =>
      previewProyeccion(JSON.parse(previewJson as string), {
        escenario: "base",
        horizonteMeses: PREVIEW_HORIZONTE,
      }),
    enabled: previewJson !== null && puedeGestionar,
  });
  const proyVigente = useQuery({
    queryKey: ["proyeccion", "base", PREVIEW_HORIZONTE],
    queryFn: () =>
      obtenerProyeccion({
        escenario: "base",
        horizonteMeses: PREVIEW_HORIZONTE,
      }),
  });

  const sensibilidad = useQuery({
    queryKey: ["sensibilidad"],
    queryFn: obtenerSensibilidad,
  });

  // ── guardar ──
  const [dialogo, setDialogo] = useState(false);
  const guardar = useMutation({
    mutationFn: (nota: string) =>
      guardarParametros({
        vigente_desde: hoyISO(),
        ...(nota.trim() ? { nota: nota.trim() } : {}),
        ...(canon as CamposParametros),
      }),
    onSuccess: () => {
      setDialogo(false);
      qc.invalidateQueries({ queryKey: ["parametros"] });
      qc.invalidateQueries({ queryKey: ["proyeccion"] });
      qc.invalidateQueries({ queryKey: ["sensibilidad"] });
      qc.invalidateQueries({ queryKey: ["comparar"] });
    },
  });

  const descartar = () => {
    setBorr(humanoDe(vigente));
    setComps(compsDe(vigente));
    setRampa(vigente.rampa_unidades ?? {});
    setTramo2(tramo2De(vigente));
  };

  const set = (k: string, v: string) => setBorr((f) => ({ ...f, [k]: v }));

  return (
    <>
      <PageHeader
        titulo="Supuestos"
        descripcion={`Vigente desde ${formatFecha(vigente.vigente_desde)} · ningún cambio se guarda sin ver su efecto.`}
        acciones={
          hayCambios && puedeGestionar ? (
            <div className="flex items-center gap-2">
              <span className="rounded-full bg-atencion/10 px-2.5 py-0.5 font-sans text-apoyo font-semibold text-atencion">
                Borrador con {nCambios} {nCambios === 1 ? "cambio" : "cambios"}
              </span>
              <Button variant="outline" size="sm" onClick={descartar}>
                Descartar
              </Button>
              <Button
                variant="cyan"
                size="sm"
                disabled={!sinErrores}
                onClick={() => setDialogo(true)}
              >
                Guardar supuestos
              </Button>
            </div>
          ) : undefined
        }
      />

      {validacion.mixError && (
        <AlertBanner variant="danger">{validacion.mixError}</AlertBanner>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_380px]">
        {/* ── Izquierda: el formulario por bloques ── */}
        <div className="flex flex-col gap-5">
          {BLOQUES.map((b) => (
            <Card key={b.titulo} className="flex flex-col gap-3 p-5">
              <CardTitle>{b.titulo}</CardTitle>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {b.campos.map((c) => (
                  <CampoSupuesto
                    key={c.key}
                    def={c}
                    valor={borr[c.key] ?? ""}
                    onChange={(v) => set(c.key, v)}
                    error={validacion.errores[c.key]}
                    disabled={!puedeGestionar}
                  />
                ))}
              </div>
              {b.titulo.startsWith("②") && borr.crec_pct_mensual && (
                <p className="font-sans text-apoyo text-ink-faint">
                  {esPctValido(borr.crec_pct_mensual)
                    ? `${borr.crec_pct_mensual} % mensual ≈ +${pctAnualEquivalente(pctAFraccion(borr.crec_pct_mensual))} % anual (compuesto) · horizonte: ${
                        /^\d+$/.test(borr.horizonte_meses ?? "") &&
                        Number(borr.horizonte_meses) >= 1
                          ? resumenHorizonte(Number(borr.horizonte_meses), ref)
                          : "—"
                      }`
                    : ""}
                </p>
              )}
              {b.titulo.startsWith("⑤") &&
                borr.adelanto_auteco !== undefined &&
                montoSeguro(borr.adelanto_auteco)?.isZero() && (
                  <p className="font-sans text-apoyo text-ink-faint">
                    Adelanto Auteco: $ 0 — decisión CEO 2026-07-26 (sin
                    adelantos mientras no los exijan).
                  </p>
                )}
            </Card>
          ))}

          {/* ⑦ CR-002 */}
          <ComponentesCard
            comps={comps}
            setComps={setComps}
            disabled={!puedeGestionar}
            costoPlano={vigente.costo_moto_nueva}
          />

          {/* ⑧ FIX-L: rampa de unidades por mes */}
          <RampaCard
            rampa={rampa}
            setRampa={setRampa}
            disabled={!puedeGestionar}
          />

          {/* ⑨ SUP-1: segundo tramo de crecimiento */}
          <Tramo2Card
            tramo2={tramo2}
            setTramo2={setTramo2}
            crecTramo1={borr.crec_pct_mensual ?? ""}
            errores={validacion.errores}
            disabled={!puedeGestionar}
          />

          {/* ⑩ SUP-4: carga semanal del cronograma */}
          <CronogramaCard puedeGestionar={puedeGestionar} />

          {hayCambios && validacion.advertencias.length > 0 && (
            <AlertBanner variant="warn">
              <ul className="list-inside list-disc">
                {validacion.advertencias.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            </AlertBanner>
          )}
        </div>

        {/* ── Derecha, sticky: el panel de impacto ── */}
        {puedeGestionar && (
          <div className="lg:sticky lg:top-4 lg:self-start">
            <PanelImpacto
              vigente={proyVigente.data}
              propuesto={preview.data}
              calculando={
                preview.isFetching ||
                (hayCambios && previewJson === null) ||
                proyVigente.isLoading
              }
              error={preview.isError || proyVigente.isError}
              hayCambios={hayCambios}
            />
          </div>
        )}
      </div>

      {/* ── Tornado de sensibilidad (§3) ── */}
      {sensibilidad.data && <Tornado data={sensibilidad.data} />}
      {sensibilidad.isError && (
        <p className="font-sans text-apoyo text-ink-faint">
          El panel de sensibilidad se calcula cuando el motor tiene
          configuración completa.
        </p>
      )}

      <ModelosPanel puedeGestionar={puedeGestionar} />

      {dialogo && canon && (
        <GuardarDialog
          diff={diffCampos(canon, canonVigente, ref)}
          advertencias={validacion.advertencias}
          impacto={preview.data ?? null}
          vigenteProy={proyVigente.data ?? null}
          guardando={guardar.isPending}
          error={
            guardar.error instanceof ApiError ? guardar.error.message : null
          }
          alConfirmar={(nota) => guardar.mutate(nota)}
          alCerrar={() => setDialogo(false)}
        />
      )}
    </>
  );
}

function montoSeguro(humano: string): Decimal | null {
  try {
    return new Decimal(montoACanonico(humano));
  } catch {
    return null;
  }
}

// ── canónico / diff / validación ─────────────────────────────────────────────

/** SUP-1: {tasa, corte} humanos → canónico. Ambos vacíos = sin tramo 2. */
export interface Tramo2Borrador {
  tasa: string;
  corte: string;
}

export function tramo2ACanonico(t: Tramo2Borrador): {
  crec_pct_mensual_2: string | null;
  crec_mes_corte: number | null;
} {
  const tasa = t.tasa.trim();
  const corte = t.corte.trim();
  if (!tasa && !corte) {
    return { crec_pct_mensual_2: null, crec_mes_corte: null };
  }
  return {
    crec_pct_mensual_2: pctAFraccion(tasa),
    crec_mes_corte: Number(corte),
  };
}

function canonicalizar(
  borr: Record<string, string>,
  comps: ComponenteAlistamiento[],
  rampa: Record<string, number>,
  ref: string,
  tramo2: Tramo2Borrador = { tasa: "", corte: "" },
): CamposParametros {
  const out: Record<string, string | number | unknown> = {};
  for (const c of CAMPOS) {
    out[c.key] = aCanonico(c.unidad, borr[c.key] ?? "", ref);
  }
  const compsCanon = comps.map((c, i) => ({
    nombre: c.nombre,
    valor: montoACanonico(c.valor),
    activo: c.activo,
    orden: i + 1,
  }));
  out.componentes_alistamiento = compsCanon.length > 0 ? compsCanon : null;
  // El backend deriva costo_moto_nueva de la Σ activos; se envía la Σ para que
  // el payload sea coherente (y el valor plano cuando no hay componentes).
  if (compsCanon.length > 0) {
    let suma = new Decimal(0);
    for (const c of compsCanon) {
      if (c.activo) suma = suma.plus(c.valor);
    }
    out.costo_moto_nueva = suma.toString();
  }
  // FIX-L: rampa canónica al FINAL (mismo orden de claves que aCampos → diff estable).
  out.rampa_unidades = Object.fromEntries(
    Object.entries(rampa).sort(([a], [b]) => a.localeCompare(b)),
  );
  Object.assign(out, tramo2ACanonico(tramo2)); // SUP-1
  return out as unknown as CamposParametros;
}

function aCampos(p: Parametros): CamposParametros {
  const out: Record<string, unknown> = {};
  for (const c of CAMPOS) {
    const v = p[c.key as keyof Parametros];
    // normalizar por Decimal para comparar "0.05" == "0.050"
    out[c.key] =
      c.unidad === "money" || c.unidad === "pct"
        ? new Decimal(String(v)).toString()
        : Number(v);
  }
  out.componentes_alistamiento =
    p.componentes_alistamiento && p.componentes_alistamiento.length > 0
      ? p.componentes_alistamiento.map((c, i) => ({
          nombre: c.nombre,
          valor: new Decimal(c.valor).toString(),
          activo: c.activo,
          orden: i + 1,
        }))
      : null;
  if (p.componentes_alistamiento && p.componentes_alistamiento.length > 0) {
    out.costo_moto_nueva = new Decimal(p.costo_moto_nueva).toString();
  }
  out.rampa_unidades = Object.fromEntries(
    Object.entries(p.rampa_unidades ?? {}).sort(([a], [b]) =>
      a.localeCompare(b),
    ),
  );
  // SUP-1: normalizar por Decimal para que "0.03" == "0.030" en el diff
  out.crec_pct_mensual_2 =
    p.crec_pct_mensual_2 !== null && p.crec_pct_mensual_2 !== undefined
      ? new Decimal(p.crec_pct_mensual_2).toString()
      : null;
  out.crec_mes_corte = p.crec_mes_corte ?? null;
  return out as unknown as CamposParametros;
}

function contarCambios(a: CamposParametros, b: CamposParametros): number {
  let n = 0;
  for (const c of CAMPOS) {
    if (
      String(a[c.key as keyof CamposParametros]) !==
      String(b[c.key as keyof CamposParametros])
    )
      n++;
  }
  if (
    JSON.stringify(a.componentes_alistamiento) !==
    JSON.stringify(b.componentes_alistamiento)
  )
    n++;
  if (JSON.stringify(a.rampa_unidades) !== JSON.stringify(b.rampa_unidades))
    n++;
  // SUP-1: el tramo 2 cuenta como UN cambio (tasa + corte son una sola decisión)
  if (
    String(a.crec_pct_mensual_2) !== String(b.crec_pct_mensual_2) ||
    String(a.crec_mes_corte) !== String(b.crec_mes_corte)
  )
    n++;
  return n;
}

export interface FilaDiff {
  label: string;
  antes: string;
  despues: string;
}

function diffCampos(
  canon: CamposParametros,
  vigente: CamposParametros,
  ref: string,
): FilaDiff[] {
  const filas: FilaDiff[] = [];
  for (const c of CAMPOS) {
    const a = String(vigente[c.key as keyof CamposParametros]);
    const d = String(canon[c.key as keyof CamposParametros]);
    if (a !== d) {
      filas.push({
        label: c.label,
        antes: presentar(c.unidad, a, ref),
        despues: presentar(c.unidad, d, ref),
      });
    }
  }
  if (
    JSON.stringify(canon.componentes_alistamiento) !==
    JSON.stringify(vigente.componentes_alistamiento)
  ) {
    filas.push({
      label: "Costos de alistamiento (componentes)",
      antes: resumenComps(vigente.componentes_alistamiento),
      despues: resumenComps(canon.componentes_alistamiento),
    });
  }
  if (
    JSON.stringify(canon.rampa_unidades) !==
    JSON.stringify(vigente.rampa_unidades)
  ) {
    filas.push({
      label: "Unidades reales por mes",
      antes: resumenRampa(vigente.rampa_unidades),
      despues: resumenRampa(canon.rampa_unidades),
    });
  }
  // SUP-1: el tramo 2 en el diff de guardado
  if (
    String(vigente.crec_pct_mensual_2 ?? null) !==
      String(canon.crec_pct_mensual_2 ?? null) ||
    String(vigente.crec_mes_corte ?? null) !==
      String(canon.crec_mes_corte ?? null)
  ) {
    filas.push({
      label: "Crecimiento · segundo tramo",
      antes: resumenTramo2(vigente.crec_pct_mensual_2, vigente.crec_mes_corte),
      despues: resumenTramo2(canon.crec_pct_mensual_2, canon.crec_mes_corte),
    });
  }
  return filas;
}

function resumenTramo2(
  tasa: string | null | undefined,
  corte: number | null | undefined,
): string {
  if (!tasa || !corte) return "un solo tramo";
  return `${fraccionAPct(tasa)} % desde el mes ${corte + 1}`;
}

function resumenRampa(r: Record<string, number> | undefined): string {
  const entradas = Object.entries(r ?? {}).sort(([a], [b]) =>
    a.localeCompare(b),
  );
  if (entradas.length === 0) return "sin rampa";
  return entradas.map(([mes, u]) => `${mes}: ${u}`).join(" · ");
}

function presentar(unidad: Unidad, canonico: string, ref: string): string {
  switch (unidad) {
    case "money":
      return formatCOP(canonico);
    case "pct":
      return `${fraccionAPct(canonico)} %`;
    case "mesCal":
      return indiceAMes(Number(canonico), ref);
    case "dias":
      return `${canonico} días`;
    case "meses":
      return `${canonico} meses`;
    default:
      return canonico;
  }
}

function resumenComps(
  comps: ComponenteAlistamiento[] | null | undefined,
): string {
  if (!comps || comps.length === 0) return "sin desglose";
  let suma = new Decimal(0);
  let activos = 0;
  for (const c of comps) {
    if (c.activo) {
      suma = suma.plus(c.valor);
      activos++;
    }
  }
  return `${activos} activos · Total ${formatCOP(suma)}`;
}

interface Validacion {
  errores: Record<string, string>;
  advertencias: string[];
  notas: string[];
  mixError: string | null;
}

function validar(
  borr: Record<string, string>,
  comps: ComponenteAlistamiento[],
  vigente: Parametros,
  modelos: ModeloMoto[],
  ref: string,
  tramo2: Tramo2Borrador = { tasa: "", corte: "" },
): Validacion {
  const errores: Record<string, string> = {};
  const advertencias: string[] = [];
  const notas: string[] = [];

  // SUP-1: el segundo tramo va completo o vacío (nunca a medias, que proyectaría
  // en silencio con un solo tramo).
  const t2tasa = tramo2.tasa.trim();
  const t2corte = tramo2.corte.trim();
  if (t2tasa || t2corte) {
    if (!t2tasa) errores.crec_pct_mensual_2 = "falta la tasa del tramo 2";
    else if (!esPctValido(t2tasa))
      errores.crec_pct_mensual_2 = "porcentaje inválido (usa 3 o 3,5)";
    if (!t2corte) errores.crec_mes_corte = "falta el mes de corte";
    else if (!/^\d+$/.test(t2corte) || Number(t2corte) < 1)
      errores.crec_mes_corte = "mes de corte inválido (entero ≥ 1)";
    else if (Number(t2corte) > 180)
      errores.crec_mes_corte = "el corte no puede pasar de 180 meses";
  }

  for (const c of CAMPOS) {
    const v = (borr[c.key] ?? "").trim();
    if (v === "") {
      errores[c.key] = "obligatorio";
      continue;
    }
    if (c.unidad === "money") {
      if (!esMontoHumanoValido(v)) {
        errores[c.key] = "monto inválido (usa 1.200.000 o 1200000)";
        continue;
      }
      if (montoSeguro(v)?.isNegative()) {
        errores[c.key] = "no puede ser negativo";
      }
    }
    if (c.unidad === "pct") {
      if (!esPctValido(v)) {
        errores[c.key] = "porcentaje inválido (ej: 5 o 1,6)";
        continue;
      }
      const pct = Number(v.replace(",", "."));
      if (pct < 0 || pct > 100) {
        errores[c.key] = "debe estar entre 0 y 100 %";
      }
    }
    if (
      (c.unidad === "int" || c.unidad === "dias" || c.unidad === "meses") &&
      !/^\d+$/.test(v)
    ) {
      errores[c.key] = "debe ser un número entero";
    }
    if (c.unidad === "mesCal") {
      if (!/^\d{4}-\d{2}$/.test(v)) {
        errores[c.key] = "elige un mes";
      } else if (mesAIndice(v, ref) < 0) {
        errores[c.key] = "no puede ser un mes pasado";
      }
    }
  }

  const horizonte = Number(borr.horizonte_meses);
  if (
    !errores.horizonte_meses &&
    (horizonte < HORIZONTE_MIN || horizonte > HORIZONTE_MAX)
  ) {
    errores.horizonte_meses = `entre ${HORIZONTE_MIN} y ${HORIZONTE_MAX} meses`;
  }

  for (const comp of comps) {
    if (!esMontoHumanoValido(comp.valor)) {
      errores.componentes = `componente «${comp.nombre}»: monto inválido`;
    }
    if (comp.nombre.trim() === "") {
      errores.componentes = "todo componente necesita nombre";
    }
  }

  // ── advertencias (§2): piden confirmación explícita al guardar ──
  const crec = Number((borr.crec_pct_mensual ?? "").replace(",", "."));
  if (!errores.crec_pct_mensual && crec > ADV_CRECIMIENTO_PCT) {
    advertencias.push(
      `Crecimiento de ${borr.crec_pct_mensual} % mensual = +${pctAnualEquivalente(
        pctAFraccion(borr.crec_pct_mensual),
      )} % anual compuesto. ¿Confirmas?`,
    );
  }
  const mora = Number((borr.pct_mora ?? "").replace(",", "."));
  if (!errores.pct_mora && mora > ADV_MORA_PCT) {
    advertencias.push(`Mora de ${borr.pct_mora} % — inusualmente alta.`);
  }
  const umbral = montoSeguro(borr.caja_minima ?? "");
  const gastos = montoSeguro(borr.gastos_fijos ?? "");
  if (umbral && gastos && umbral.lessThan(gastos.div(2))) {
    advertencias.push(
      "El mínimo de caja quedó por debajo de medio mes de gastos fijos.",
    );
  }
  // cambios de más de ±50 % vs. el vigente (montos y porcentajes)
  for (const c of CAMPOS) {
    if (errores[c.key] || (c.unidad !== "money" && c.unidad !== "pct"))
      continue;
    try {
      const nuevo = new Decimal(String(aCanonico(c.unidad, borr[c.key], ref)));
      const previo = new Decimal(String(vigente[c.key as keyof Parametros]));
      if (previo.isZero()) continue;
      const cambio = nuevo.minus(previo).div(previo).abs();
      if (cambio.greaterThan(ADV_CAMBIO_RELATIVO)) {
        advertencias.push(
          `«${c.label}» cambia ${cambio.times(100).toDecimalPlaces(0)} % vs. el vigente.`,
        );
      }
    } catch {
      // campo aún ilegible: ya está cubierto por errores
    }
  }

  // ── error de mix (bloquea: la proyección saldría mal) ──
  let mixError: string | null = null;
  const activos = modelos.filter((m) => m.activo);
  if (activos.length > 0) {
    let mix = new Decimal(0);
    for (const m of activos) mix = mix.plus(m.participacion_mix);
    if (!mix.equals(1)) {
      mixError = `La participación en ventas de los modelos activos suma ${mix.times(100).toString()} % (debe ser 100 %). Corrige la participación en Modelos antes de guardar.`;
      errores.__mix = mixError;
    }
  }

  return { errores, advertencias, notas, mixError };
}

// ── Campo con contrato ⓘ ─────────────────────────────────────────────────────

const SUFIJO: Record<Unidad, string> = {
  money: "COP",
  pct: "%",
  int: "",
  dias: "días",
  meses: "meses",
  mesCal: "",
};

function CampoSupuesto({
  def,
  valor,
  onChange,
  error,
  disabled,
}: {
  def: CampoDef;
  valor: string;
  onChange: (v: string) => void;
  error?: string;
  disabled?: boolean;
}) {
  const sufijo = SUFIJO[def.unidad];
  const id = `campo-${def.key}`;
  return (
    <div className="flex flex-col gap-1">
      <label
        htmlFor={id}
        className="flex items-center gap-1 font-sans text-apoyo font-medium text-ink-soft"
      >
        {def.label}
        <span title={def.contrato} className="cursor-help text-ink-decor">
          ⓘ
        </span>
      </label>
      <span className="flex items-center gap-1.5">
        {def.unidad === "mesCal" ? (
          <input
            id={id}
            type="month"
            value={valor}
            disabled={disabled}
            onChange={(e) => onChange(e.target.value)}
            className={campoClase(error)}
          />
        ) : (
          <input
            id={id}
            inputMode={
              def.unidad === "money" || def.unidad === "pct"
                ? "decimal"
                : "numeric"
            }
            value={valor}
            disabled={disabled}
            onChange={(e) =>
              onChange(
                def.unidad === "money"
                  ? reformatearMonto(e.target.value)
                  : e.target.value,
              )
            }
            className={campoClase(error)}
          />
        )}
        {sufijo && (
          <span className="font-sans text-apoyo text-ink-faint">{sufijo}</span>
        )}
      </span>
      {error && (
        <span className="font-sans text-apoyo font-medium text-critico">
          {error}
        </span>
      )}
    </div>
  );
}

function campoClase(error?: string): string {
  return `tabular w-full rounded-md border bg-surface px-3 py-1.5 font-sans text-cuerpo text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan disabled:bg-surface-muted disabled:text-ink-faint ${
    error ? "border-critico" : "border-hairline"
  }`;
}

/** Separador de miles es-CO mientras se escribe; tolera el texto a medias. */
function reformatearMonto(v: string): string {
  const limpio = v.replace(/[^\d,]/g, "");
  if (limpio === "") return "";
  const [entera, dec] = limpio.split(",");
  const conMiles = entera.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return dec !== undefined ? `${conMiles},${dec}` : conMiles;
}

// ── ⑦ CR-002: componentes de alistamiento ────────────────────────────────────

const _MES_RE = /^\d{4}-(0[1-9]|1[0-2])$/;

function _seedRampa(
  rampa: Record<string, number>,
): { mes: string; unidades: string }[] {
  return Object.entries(rampa)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([mes, u]) => ({ mes, unidades: String(u) }));
}

// ⑩ SUP-4 (CEO 2026-08-22): la carga semanal. El CEO sube el cronograma (los lunes)
// y COMPAS actualiza la cartera ya originada + la meta del mes en curso. No guarda
// las ~9.900 cuotas: agrega ~80 semanas, que es lo que el motor necesita.
function CronogramaCard({ puedeGestionar }: { puedeGestionar: boolean }) {
  const qc = useQueryClient();
  const [resumen, setResumen] = useState<ResumenCarga | null>(null);
  const serie = useQuery({
    queryKey: ["cartera-previa-serie"],
    queryFn: obtenerSerieCartera,
  });
  const cargar = useMutation({
    mutationFn: cargarCronograma,
    onSuccess: (r) => {
      setResumen(r);
      qc.invalidateQueries({ queryKey: ["cartera-previa-serie"] });
      qc.invalidateQueries({ queryKey: ["parametros"] });
      qc.invalidateQueries({ queryKey: ["proyeccion"] });
      qc.invalidateQueries({ queryKey: ["sensibilidad"] });
    },
  });

  return (
    <Card className="p-5">
      <CardTitle>⑩ Cartera ya originada</CardTitle>
      <p className="mt-0.5 font-sans text-apoyo text-ink-faint">
        Sube el cronograma de pagos (una vez por semana) y COMPAS actualiza lo
        que falta por recaudar de los créditos vivos —cada uno con su cuota
        real— y deja el mes en curso en lo que falta por colocar para la meta.
      </p>

      {serie.data && (
        <p className="mt-3 font-sans text-cuerpo text-ink-soft">
          Hoy el motor cuenta con{" "}
          <span className="tabular font-semibold text-ink">
            {formatCOP(serie.data.recaudo_total)}
          </span>{" "}
          por cobrar de lo ya originado, en {serie.data.semanas} semanas.
        </p>
      )}

      {puedeGestionar && (
        <label className="mt-4 flex cursor-pointer flex-col items-center gap-1 rounded-lg border border-dashed border-hairline bg-surface-muted/40 px-4 py-6 text-center transition-colors hover:border-cyan">
          <span className="font-sans text-cuerpo font-medium text-ink">
            {cargar.isPending
              ? "Procesando el cronograma…"
              : "Haz clic para elegir el cronograma"}
          </span>
          <span className="font-sans text-apoyo text-ink-faint">
            el .xlsx de «Cronograma General»
          </span>
          <input
            type="file"
            accept=".xlsx"
            className="hidden"
            disabled={cargar.isPending}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) cargar.mutate(f);
              e.target.value = "";
            }}
          />
        </label>
      )}

      {cargar.isError && (
        <div className="mt-3">
          <AlertBanner variant="danger">
            {cargar.error instanceof ApiError
              ? cargar.error.message
              : "No se pudo cargar el cronograma."}
          </AlertBanner>
        </div>
      )}

      {resumen && (
        <div className="mt-4 flex flex-col gap-1 font-sans text-cuerpo text-ink-soft">
          <p>
            <span className="font-semibold text-ink">{resumen.creditos}</span>{" "}
            créditos vivos ·{" "}
            <span className="tabular font-semibold text-ink">
              {formatCOP(resumen.recaudo_futuro)}
            </span>{" "}
            por cobrar en {resumen.semanas} semanas.
          </p>
          <p>
            Mora medida hoy:{" "}
            <span className="tabular font-semibold text-atencion">
              {formatCOP(resumen.vencido_sin_pagar)}
            </span>{" "}
            en {resumen.creditos_en_mora} créditos — es lo vencido sin pagar, no
            se proyecta.
          </p>
          {Object.entries(resumen.rampa_mes_en_curso).map(([mes, faltan]) => (
            <p key={mes}>
              Mes en curso ({mes}): faltan{" "}
              <span className="font-semibold text-ink">{faltan}</span> motos
              para la meta; las ya colocadas recaudan con su cuota real.
            </p>
          ))}
          {resumen.errores.length > 0 && (
            <AlertBanner variant="warn">
              {resumen.errores.length} fila(s) ilegibles se omitieron:{" "}
              {resumen.errores[0]}
            </AlertBanner>
          )}
        </div>
      )}
    </Card>
  );
}

// ⑨ SUP-1 (CEO 2026-08-17): un crecimiento mensual alto es razonable al arrancar y
// absurdo compuesto a 10 años. Aquí el CEO declara desde qué mes baja el ritmo.
function Tramo2Card({
  tramo2,
  setTramo2,
  crecTramo1,
  errores,
  disabled,
}: {
  tramo2: Tramo2Borrador;
  setTramo2: (t: Tramo2Borrador) => void;
  crecTramo1: string;
  errores: Record<string, string>;
  disabled: boolean;
}) {
  const activo = tramo2.tasa.trim() !== "" || tramo2.corte.trim() !== "";
  const corte = Number(tramo2.corte.trim() || "0");
  return (
    <Card className="p-5">
      <CardTitle>⑨ Crecimiento a largo plazo</CardTitle>
      <p className="mt-0.5 font-sans text-apoyo text-ink-faint">
        Opcional: a partir de cierto mes la colocación crece a otro ritmo. Vacío
        = un solo tramo (el {crecTramo1 || "—"} % de arriba para todo el
        horizonte).
      </p>
      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1">
          <span className="font-sans text-apoyo font-medium text-ink-soft">
            Hasta el mes
          </span>
          <input
            inputMode="numeric"
            disabled={disabled}
            aria-label="Mes de corte del segundo tramo"
            className="rounded-md border border-hairline bg-surface px-2 py-1.5 font-sans text-cuerpo text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan disabled:opacity-60"
            placeholder="18"
            value={tramo2.corte}
            onChange={(e) => setTramo2({ ...tramo2, corte: e.target.value })}
          />
          {errores.crec_mes_corte && (
            <span className="font-sans text-apoyo text-critico">
              {errores.crec_mes_corte}
            </span>
          )}
        </label>
        <label className="flex flex-col gap-1">
          <span className="font-sans text-apoyo font-medium text-ink-soft">
            Luego crece (%/mes)
          </span>
          <input
            inputMode="decimal"
            disabled={disabled}
            aria-label="Ritmo mensual del segundo tramo"
            className="rounded-md border border-hairline bg-surface px-2 py-1.5 font-sans text-cuerpo text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan disabled:opacity-60"
            placeholder="3"
            value={tramo2.tasa}
            onChange={(e) => setTramo2({ ...tramo2, tasa: e.target.value })}
          />
          {errores.crec_pct_mensual_2 && (
            <span className="font-sans text-apoyo text-critico">
              {errores.crec_pct_mensual_2}
            </span>
          )}
        </label>
      </div>
      {activo && !errores.crec_mes_corte && !errores.crec_pct_mensual_2 && (
        <p className="mt-3 font-sans text-apoyo text-ink-faint">
          Meses 1–{corte} al {crecTramo1 || "—"} % · desde el mes {corte + 1} al{" "}
          {tramo2.tasa || "—"} % mensual.
        </p>
      )}
    </Card>
  );
}

function RampaCard({
  rampa,
  setRampa,
  disabled,
}: {
  rampa: Record<string, number>;
  setRampa: (r: Record<string, number>) => void;
  disabled: boolean;
}) {
  const [filas, setFilas] = useState(() => _seedRampa(rampa));
  const lastEmit = useRef(JSON.stringify(rampa));
  // Re-sincroniza SOLO ante un cambio EXTERNO (descartar / nueva vigencia): si el prop
  // difiere de lo último que emitimos, re-seed (sin borrar filas en edición).
  useEffect(() => {
    const inc = JSON.stringify(rampa);
    if (inc !== lastEmit.current) {
      setFilas(_seedRampa(rampa));
      lastEmit.current = inc;
    }
  }, [rampa]);

  const emitir = (nuevas: { mes: string; unidades: string }[]) => {
    setFilas(nuevas);
    const rec: Record<string, number> = {};
    for (const f of nuevas) {
      const u = Number(f.unidades);
      if (
        _MES_RE.test(f.mes) &&
        f.unidades.trim() !== "" &&
        Number.isInteger(u) &&
        u >= 0
      ) {
        rec[f.mes] = u;
      }
    }
    lastEmit.current = JSON.stringify(rec);
    setRampa(rec);
  };

  const set = (i: number, cambio: Partial<{ mes: string; unidades: string }>) =>
    emitir(filas.map((f, j) => (j === i ? { ...f, ...cambio } : f)));

  return (
    <Card className="flex flex-col gap-3 p-5">
      <div>
        <CardTitle>⑧ Unidades reales por mes (primeros meses)</CardTitle>
        <p className="mt-0.5 font-sans text-apoyo text-ink-faint">
          Colocación REAL de los primeros meses (reemplaza la proyección esos
          meses). El primer mes sin dato vuelve a “motos base” y de ahí crece
          encadenado. Vacío = sin rampa (comportamiento por defecto).
        </p>
      </div>
      {filas.length > 0 && (
        <div className="flex flex-col gap-2">
          {filas.map((f, i) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: filas de editor efímeras (el mes puede estar vacío/duplicado mientras se edita)
            <div key={`rampa-${i}`} className="flex items-center gap-2">
              <input
                type="month"
                aria-label={`Mes rampa ${i + 1}`}
                disabled={disabled}
                className="rounded-md border border-hairline bg-surface px-2 py-1 font-sans text-sm text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan"
                value={f.mes}
                onChange={(e) => set(i, { mes: e.target.value })}
              />
              <input
                type="number"
                min={0}
                step={1}
                aria-label={`Unidades rampa ${i + 1}`}
                disabled={disabled}
                placeholder="unidades"
                className="tabular w-28 rounded-md border border-hairline bg-surface px-2 py-1 text-right font-sans text-sm text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan"
                value={f.unidades}
                onChange={(e) => set(i, { unidades: e.target.value })}
              />
              {!disabled && (
                <button
                  type="button"
                  className="font-sans text-sm font-medium text-critico hover:underline"
                  onClick={() => emitir(filas.filter((_, j) => j !== i))}
                >
                  Quitar
                </button>
              )}
            </div>
          ))}
        </div>
      )}
      {!disabled && (
        <div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => emitir([...filas, { mes: "", unidades: "" }])}
          >
            Agregar mes
          </Button>
        </div>
      )}
    </Card>
  );
}

function ComponentesCard({
  comps,
  setComps,
  disabled,
  costoPlano,
}: {
  comps: ComponenteAlistamiento[];
  setComps: (c: ComponenteAlistamiento[]) => void;
  disabled: boolean;
  costoPlano: string;
}) {
  let suma: Decimal | null = new Decimal(0);
  for (const c of comps) {
    const v = montoSeguro(c.valor);
    if (v === null) {
      suma = null;
      break;
    }
    if (c.activo) suma = suma.plus(v);
  }

  const set = (i: number, cambio: Partial<ComponenteAlistamiento>) =>
    setComps(comps.map((c, j) => (j === i ? { ...c, ...cambio } : c)));

  return (
    <Card className="flex flex-col gap-3 p-5">
      <div>
        <CardTitle>
          ⑦ Costos de alistamiento por moto vendida{" "}
          <span
            title={CONTRATO_ALISTAMIENTO}
            className="cursor-help font-sans text-cuerpo text-ink-decor"
          >
            ⓘ
          </span>
        </CardTitle>
        <p className="mt-0.5 font-sans text-apoyo text-ink-faint">
          La proyección resta la suma de los componentes ACTIVOS por cada moto
          colocada.
        </p>
      </div>

      {comps.length === 0 && (
        <p className="font-sans text-cuerpo text-ink-soft">
          Sin desglose: aplica el valor plano de {formatCOP(costoPlano)}.
          {!disabled && " Agrega componentes para desglosarlo."}
        </p>
      )}

      {comps.map((c, i) => (
        <div
          key={`comp-${i}-${c.orden}`}
          className="flex flex-wrap items-center gap-2"
        >
          <input
            aria-label={`Nombre componente ${i + 1}`}
            value={c.nombre}
            disabled={disabled}
            onChange={(e) => set(i, { nombre: e.target.value })}
            className={`${campoClase()} max-w-56`}
          />
          <input
            aria-label={`Valor ${c.nombre}`}
            inputMode="decimal"
            value={c.valor}
            disabled={disabled}
            onChange={(e) =>
              set(i, { valor: reformatearMonto(e.target.value) })
            }
            className={`${campoClase()} max-w-40 text-right`}
          />
          <label className="flex items-center gap-1.5 font-sans text-apoyo text-ink-soft">
            <input
              type="checkbox"
              checked={c.activo}
              disabled={disabled}
              onChange={(e) => set(i, { activo: e.target.checked })}
            />
            activo
          </label>
          {!disabled && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => setComps(comps.filter((_, j) => j !== i))}
            >
              Quitar
            </Button>
          )}
        </div>
      ))}

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-hairline pt-3">
        <span className="font-sans text-cuerpo text-ink">
          Total activo:{" "}
          <span className="tabular font-semibold">
            {suma ? formatCOP(suma) : "—"}
          </span>
        </span>
        {!disabled && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() =>
              setComps([
                ...comps,
                {
                  nombre: "",
                  valor: "",
                  activo: true,
                  orden: comps.length + 1,
                },
              ])
            }
          >
            Agregar componente
          </Button>
        )}
      </div>
    </Card>
  );
}

// ── Diálogo de guardado: diff + impacto + nota ───────────────────────────────

function GuardarDialog({
  diff,
  advertencias,
  impacto,
  vigenteProy,
  guardando,
  error,
  alConfirmar,
  alCerrar,
}: {
  diff: FilaDiff[];
  advertencias: string[];
  impacto: import("@/lib/proyeccion").Proyeccion | null;
  vigenteProy: import("@/lib/proyeccion").Proyeccion | null;
  guardando: boolean;
  error: string | null;
  alConfirmar: (nota: string) => void;
  alCerrar: () => void;
}) {
  const [nota, setNota] = useState("");
  const [confirmado, setConfirmado] = useState(advertencias.length === 0);

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!confirmado) return;
    alConfirmar(nota);
  }

  return (
    <div className="fixed inset-0 z-20 flex items-center justify-center bg-black/40 p-4">
      <dialog
        open
        aria-label="Guardar supuestos"
        className="static max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-xl border border-hairline bg-surface p-6 text-inherit shadow-lg"
      >
        <h3 className="mb-1 font-display text-seccion text-ink">
          Guardar supuestos
        </h3>
        <p className="mb-4 font-sans text-apoyo text-ink-faint">
          Se crea una vigencia nueva desde hoy. El cambio queda auditado (con tu
          nota, si la escribes).
        </p>

        <p className="mb-1 font-sans text-apoyo font-semibold tracking-wide text-ink-faint uppercase">
          Cambios ({diff.length})
        </p>
        <ul className="mb-4 flex flex-col gap-1 font-sans text-cuerpo">
          {diff.map((f) => (
            <li key={f.label} className="flex flex-wrap gap-1.5">
              <span className="text-ink-soft">{f.label}:</span>
              <span className="tabular text-ink-faint line-through">
                {f.antes}
              </span>
              <span aria-hidden="true" className="text-ink-faint">
                →
              </span>
              <span className="tabular font-semibold text-ink">
                {f.despues}
              </span>
            </li>
          ))}
        </ul>

        {impacto && vigenteProy && (
          <p className="mb-4 font-sans text-cuerpo text-ink">
            Impacto: piso de caja{" "}
            <span className="tabular text-ink-soft">
              {formatCOP(vigenteProy.piso_caja)}
            </span>{" "}
            →{" "}
            <span className="tabular font-semibold">
              {formatCOP(impacto.piso_caja)}
            </span>
            {impacto.meses_bajo_minimo > 0 &&
              ` · mes crítico ${impacto.mes_mas_ajustado}`}
          </p>
        )}

        {advertencias.length > 0 && (
          <div className="mb-4 flex flex-col gap-2">
            <AlertBanner variant="warn">
              <ul className="list-inside list-disc">
                {advertencias.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            </AlertBanner>
            <label className="flex items-start gap-2 font-sans text-cuerpo text-ink">
              <input
                type="checkbox"
                checked={confirmado}
                onChange={(e) => setConfirmado(e.target.checked)}
                className="mt-1"
              />
              Entiendo las advertencias y confirmo el cambio.
            </label>
          </div>
        )}

        <form onSubmit={onSubmit} className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 font-sans text-cuerpo">
            <span className="text-apoyo font-medium text-ink-soft">
              Nota (opcional, por qué el cambio)
            </span>
            <input
              maxLength={300}
              value={nota}
              onChange={(e) => setNota(e.target.value)}
              placeholder="ej: bajamos el crecimiento por decisión de junta"
              className={campoClase()}
            />
          </label>

          {error && <AlertBanner variant="danger">{error}</AlertBanner>}

          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={alCerrar}>
              Cancelar
            </Button>
            <Button
              type="submit"
              variant="green"
              disabled={guardando || !confirmado}
            >
              {guardando ? "Guardando…" : "Guardar supuestos"}
            </Button>
          </div>
        </form>
      </dialog>
    </div>
  );
}

// ── Panel de modelos de moto (CR-002: la matrícula SALE de la UI) ────────────

const MODELO_VACIO: ModeloCrearInput = {
  nombre: "",
  costo_auteco: "",
  precio_venta_con_iva: "",
  cuota_inicial: "",
  cuota_semanal: "",
  plazo_semanas: 0,
  // CR-002: campo placebo retirado de la UI (su semántica real —lo que se cobra
  // al cliente— vive dentro de la cuota inicial). El dominio lo conserva por
  // compatibilidad; se envía 0 en creaciones nuevas.
  matricula: "0",
  participacion_mix: "",
};

function ModelosPanel({ puedeGestionar }: { puedeGestionar: boolean }) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["modelos-moto"],
    queryFn: () => listarModelos(),
  });
  const [nuevo, setNuevo] = useState<ModeloCrearInput>(MODELO_VACIO);
  const [editando, setEditando] = useState<ModeloMoto | null>(null);

  const invalidar = () => {
    qc.invalidateQueries({ queryKey: ["modelos-moto"] });
    qc.invalidateQueries({ queryKey: ["proyeccion"] });
    qc.invalidateQueries({ queryKey: ["sensibilidad"] });
  };
  const crear = useMutation({
    mutationFn: crearModelo,
    onSuccess: () => {
      invalidar();
      setNuevo(MODELO_VACIO);
    },
  });
  const editar = useMutation({
    mutationFn: editarModelo,
    onSuccess: () => {
      invalidar();
      setEditando(null);
    },
  });
  const desactivar = useMutation({
    mutationFn: desactivarModelo,
    onSuccess: invalidar,
  });
  const reactivar = useMutation({
    mutationFn: reactivarModelo,
    onSuccess: invalidar,
  });

  const setN = (k: keyof ModeloCrearInput, v: string) =>
    setNuevo((m) => ({
      ...m,
      [k]: k === "plazo_semanas" ? Number(v) : v,
    }));

  return (
    <Card className="p-5">
      <CardTitle>Modelos de moto</CardTitle>
      <p className="mt-0.5 font-sans text-apoyo text-ink-faint">
        Cada modelo aporta a la participación en ventas con su cuota, plazo y
        cuota inicial.
      </p>

      {q.isLoading && <Cargando variante="tabla" className="mt-3" />}

      {q.data && (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full font-sans text-cuerpo">
            <thead>
              <tr className="border-b border-hairline text-left text-ink-faint">
                <th className="px-3 py-2 font-semibold">Modelo</th>
                <th className="px-3 py-2 text-right font-semibold">
                  Cuota sem.
                </th>
                <th className="px-3 py-2 text-right font-semibold">
                  <span title={CONTRATO_CUOTA_INICIAL} className="cursor-help">
                    Cuota inicial ⓘ
                  </span>
                </th>
                <th className="px-3 py-2 text-right font-semibold">Plazo</th>
                <th className="px-3 py-2 text-right font-semibold">
                  Participación
                </th>
                <th className="px-3 py-2 font-semibold">Estado</th>
                {puedeGestionar && <th className="px-3 py-2" />}
              </tr>
            </thead>
            <tbody>
              {q.data.map((m) => (
                <ModeloFila
                  key={m.id}
                  m={m}
                  puedeGestionar={puedeGestionar}
                  onEditar={() => setEditando(m)}
                  onDesactivar={() => desactivar.mutate(m.id)}
                  onReactivar={() => reactivar.mutate(m.id)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {puedeGestionar && (
        <form
          className="mt-5 border-t border-hairline pt-4"
          onSubmit={(e) => {
            e.preventDefault();
            crear.mutate(nuevo);
          }}
        >
          <p className="mb-2 font-sans text-apoyo font-semibold tracking-wider text-ink-faint uppercase">
            Agregar modelo
          </p>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <CampoModelo
              label="Nombre"
              value={nuevo.nombre}
              onChange={(v) => setN("nombre", v)}
            />
            <CampoModelo
              label="Cuota semanal"
              inputMode="decimal"
              value={nuevo.cuota_semanal}
              onChange={(v) => setN("cuota_semanal", v)}
            />
            <CampoModelo
              label="Cuota inicial"
              hint={CONTRATO_CUOTA_INICIAL}
              inputMode="decimal"
              value={nuevo.cuota_inicial}
              onChange={(v) => setN("cuota_inicial", v)}
            />
            <CampoModelo
              label="Plazo (semanas)"
              inputMode="numeric"
              value={nuevo.plazo_semanas ? String(nuevo.plazo_semanas) : ""}
              onChange={(v) => setN("plazo_semanas", v)}
            />
            <CampoModelo
              label="Costo Auteco"
              inputMode="decimal"
              value={nuevo.costo_auteco}
              onChange={(v) => setN("costo_auteco", v)}
            />
            <CampoModelo
              label="Precio venta (con IVA)"
              inputMode="decimal"
              value={nuevo.precio_venta_con_iva}
              onChange={(v) => setN("precio_venta_con_iva", v)}
            />
            <CampoModelo
              label="Participación en ventas (%)"
              hint="fracción — ej: 0.5 = 50 %"
              inputMode="decimal"
              value={nuevo.participacion_mix}
              onChange={(v) => setN("participacion_mix", v)}
            />
          </div>
          {crear.isError && (
            <div className="mt-3">
              <AlertBanner variant="danger">
                {crear.error instanceof ApiError
                  ? crear.error.message
                  : "No se pudo crear el modelo."}
              </AlertBanner>
            </div>
          )}
          <div className="mt-3">
            <Button type="submit" variant="cyan" disabled={crear.isPending}>
              {crear.isPending ? "Agregando…" : "Agregar modelo"}
            </Button>
          </div>
        </form>
      )}

      {editando && (
        <EditarModeloDialog
          m={editando}
          guardando={editar.isPending}
          error={editar.error instanceof ApiError ? editar.error.message : null}
          onCerrar={() => setEditando(null)}
          onGuardar={(cambios) => {
            if (Object.keys(cambios).length === 1) setEditando(null);
            else editar.mutate(cambios);
          }}
        />
      )}
    </Card>
  );
}

// CR-002: sin `matricula` — retirada de la UI (placebo; el motor la ignora).
const CAMPOS_MODELO: { key: keyof ModeloEditarInput; label: string }[] = [
  { key: "nombre", label: "Nombre" },
  { key: "cuota_semanal", label: "Cuota semanal" },
  { key: "cuota_inicial", label: "Cuota inicial" },
  { key: "plazo_semanas", label: "Plazo (semanas)" },
  { key: "costo_auteco", label: "Costo Auteco" },
  { key: "precio_venta_con_iva", label: "Precio venta (con IVA)" },
  { key: "participacion_mix", label: "Participación en ventas (%)" },
];

// PLAN-52: campos del segundo plan (vacíos ambos = el modelo vuelve a un solo plan)
const CAMPOS_PLAN2: {
  key: keyof ModeloEditarInput;
  label: string;
  hint?: string;
}[] = [
  { key: "plan2_plazo_semanas", label: "Plan 2 · plazo (semanas)" },
  { key: "plan2_cuota_semanal", label: "Plan 2 · cuota semanal" },
  {
    key: "peso_plan1",
    label: "Peso del plan 1",
    hint: "fracción — ej: 0.7 = 70 % de las ventas del modelo al plan 1, el resto al plan 2",
  },
];

function EditarModeloDialog({
  m,
  guardando,
  error,
  onCerrar,
  onGuardar,
}: {
  m: ModeloMoto;
  guardando: boolean;
  error: string | null;
  onCerrar: () => void;
  onGuardar: (cambios: ModeloEditarInput) => void;
}) {
  const valores = (mm: ModeloMoto): Record<string, string> => ({
    nombre: mm.nombre,
    cuota_semanal: mm.cuota_semanal,
    cuota_inicial: mm.cuota_inicial,
    plazo_semanas: String(mm.plazo_semanas),
    costo_auteco: mm.costo_auteco,
    precio_venta_con_iva: mm.precio_venta_con_iva,
    participacion_mix: mm.participacion_mix,
    plan2_plazo_semanas: mm.plan2_plazo_semanas
      ? String(mm.plan2_plazo_semanas)
      : "",
    plan2_cuota_semanal: mm.plan2_cuota_semanal ?? "",
    peso_plan1: mm.peso_plan1 ?? "1",
  });
  const [v, setV] = useState<Record<string, string>>(valores(m));
  const actual: Record<string, string> = valores(m);

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const cambios: Record<string, unknown> = { id: m.id };
    for (const { key } of CAMPOS_MODELO) {
      const nuevo = (v[key] ?? "").trim();
      if (nuevo !== actual[key]) {
        cambios[key] = key === "plazo_semanas" ? Number(nuevo) : nuevo;
      }
    }
    // PLAN-52: los dos campos del plan 2 vacíos = quitar el plan (peso vuelve a 1);
    // si hay valores, solo viajan los que cambian (el backend valida coherencia).
    const p2Plazo = (v.plan2_plazo_semanas ?? "").trim();
    const p2Cuota = (v.plan2_cuota_semanal ?? "").trim();
    const teniaPlan2 = m.plan2_plazo_semanas !== null;
    if (!p2Plazo && !p2Cuota) {
      if (teniaPlan2) cambios.quitar_plan2 = true;
    } else {
      if (p2Plazo !== actual.plan2_plazo_semanas) {
        cambios.plan2_plazo_semanas = Number(p2Plazo);
      }
      if (p2Cuota !== actual.plan2_cuota_semanal) {
        cambios.plan2_cuota_semanal = p2Cuota;
      }
    }
    const peso = (v.peso_plan1 ?? "").trim();
    if (peso && peso !== actual.peso_plan1 && !cambios.quitar_plan2) {
      cambios.peso_plan1 = peso;
    }
    onGuardar(cambios as unknown as ModeloEditarInput);
  }

  return (
    <div className="fixed inset-0 z-10 flex items-center justify-center bg-black/40 p-4">
      <dialog
        open
        aria-label={`Editar modelo ${m.nombre}`}
        className="static w-full max-w-lg rounded-xl border border-hairline bg-surface p-6 text-inherit shadow-lg"
      >
        <h3 className="mb-4 font-display text-seccion text-ink">
          Editar modelo · {m.nombre}
        </h3>
        <form onSubmit={onSubmit}>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {CAMPOS_MODELO.map((c) => (
              <CampoModelo
                key={c.key}
                label={c.label}
                hint={
                  c.key === "cuota_inicial" ? CONTRATO_CUOTA_INICIAL : undefined
                }
                inputMode={c.key === "nombre" ? undefined : "decimal"}
                value={v[c.key] ?? ""}
                onChange={(nv) => setV((s) => ({ ...s, [c.key]: nv }))}
              />
            ))}
          </div>
          <p className="mt-4 mb-2 font-sans text-apoyo font-semibold tracking-wider text-ink-faint uppercase">
            Segundo plan de pago (opcional — vacío = un solo plan)
          </p>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {CAMPOS_PLAN2.map((c) => (
              <CampoModelo
                key={c.key}
                label={c.label}
                hint={c.hint}
                inputMode="decimal"
                value={v[c.key] ?? ""}
                onChange={(nv) => setV((s) => ({ ...s, [c.key]: nv }))}
              />
            ))}
          </div>
          {error && (
            <div className="mt-3">
              <AlertBanner variant="danger">{error}</AlertBanner>
            </div>
          )}
          <div className="mt-4 flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onCerrar}>
              Cancelar
            </Button>
            <Button type="submit" variant="cyan" disabled={guardando}>
              {guardando ? "Guardando…" : "Guardar cambios"}
            </Button>
          </div>
        </form>
      </dialog>
    </div>
  );
}

function ModeloFila({
  m,
  puedeGestionar,
  onEditar,
  onDesactivar,
  onReactivar,
}: {
  m: ModeloMoto;
  puedeGestionar: boolean;
  onEditar: () => void;
  onDesactivar: () => void;
  onReactivar: () => void;
}) {
  return (
    <tr className="border-b border-hairline/60 last:border-0">
      <td className="px-3 py-2 font-medium text-ink">
        {m.nombre}
        {m.es_sistema && (
          <span className="ml-2 rounded bg-surface-muted px-1.5 py-0.5 font-sans text-apoyo text-ink-faint">
            sistema
          </span>
        )}
      </td>
      <td className="tabular px-3 py-2 text-right text-ink-soft">
        {formatCOP(m.cuota_semanal)}
        {m.plan2_cuota_semanal ? (
          <div className="text-ink-faint">
            {formatCOP(m.plan2_cuota_semanal)}
          </div>
        ) : null}
      </td>
      <td
        className="tabular px-3 py-2 text-right text-ink-soft"
        title={CONTRATO_CUOTA_INICIAL}
      >
        {formatCOP(m.cuota_inicial)}
      </td>
      <td className="tabular px-3 py-2 text-right text-ink-soft">
        {m.plazo_semanas} sem
        {m.plan2_plazo_semanas ? (
          <div className="text-ink-faint">{m.plan2_plazo_semanas} sem</div>
        ) : null}
      </td>
      <td className="tabular px-3 py-2 text-right text-ink-soft">
        {m.participacion_mix}
        {m.plan2_plazo_semanas ? (
          <div
            className="text-ink-faint"
            title={`Reparto entre planes: ${m.peso_plan1} del mix al plan de ${m.plazo_semanas} sem; el resto al de ${m.plan2_plazo_semanas} sem`}
          >
            peso {m.peso_plan1}
          </div>
        ) : null}
      </td>
      <td className="px-3 py-2">
        <span
          className={`rounded-full px-2 py-0.5 font-sans text-apoyo font-medium ${
            m.activo
              ? "bg-positivo/10 text-positivo"
              : "bg-surface-muted text-ink-faint"
          }`}
        >
          {m.activo ? "Activo" : "Inactivo"}
        </span>
      </td>
      {puedeGestionar && (
        <td className="px-3 py-2 text-right">
          <div className="flex justify-end gap-1">
            {!m.es_sistema && (
              <Button variant="ghost" size="sm" onClick={onEditar}>
                Editar
              </Button>
            )}
            {m.activo ? (
              <Button variant="ghost" size="sm" onClick={onDesactivar}>
                Desactivar
              </Button>
            ) : (
              <Button variant="ghost" size="sm" onClick={onReactivar}>
                Reactivar
              </Button>
            )}
          </div>
        </td>
      )}
    </tr>
  );
}

function CampoModelo({
  label,
  hint,
  value,
  onChange,
  inputMode,
}: {
  label: string;
  hint?: string;
  value: string;
  onChange: (v: string) => void;
  inputMode?: "decimal" | "numeric";
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="flex items-center gap-1 font-sans text-apoyo font-medium text-ink-soft">
        {label}
        {hint && (
          <span title={hint} className="cursor-help text-ink-decor">
            ⓘ
          </span>
        )}
      </span>
      <input
        inputMode={inputMode}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={campoClase()}
      />
    </label>
  );
}
