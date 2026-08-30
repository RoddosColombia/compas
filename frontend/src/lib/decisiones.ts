// frontend/src/lib/decisiones.ts
//
// D1 "Decisiones sobre el motor": capa de impactos, valles, escenarios y solvers.
// Todo compute-only en el backend (motor intocable); el front solo presenta. Montos
// como string (regla 1). `valor` de un ajuste puede ser COP (absoluto) o fracción
// (porcentaje 0.10 = 10%) — NUNCA se pasa por Number.

import { apiFetch, apiJson } from "@/lib/api";
import type { Proyeccion, ProyeccionParams } from "@/lib/proyeccion";

export type NaturalezaAjuste = "gasto" | "ingreso";
export type ModoAjuste = "absoluto" | "porcentaje";

export interface Ajuste {
  nombre: string;
  naturaleza: NaturalezaAjuste;
  modo: ModoAjuste;
  valor: string; // COP (absoluto) o fracción (porcentaje)
  mes_inicio: string; // 'YYYY-MM'
  mes_fin: string | null; // null = hasta el final del horizonte
  rubro_id: string | null; // opcional: trazabilidad/vistas
}

export interface CausaValle {
  concepto: string;
  etiqueta: string; // lenguaje llano ("Pago de lote (Auteco)")
  monto: string; // magnitud del egreso ese mes
  promedio: string; // promedio de los meses vecinos
  vs_promedio: string | null; // desvío relativo (0.40 = 40%); null si promedio 0
}

// RF-F5 · Fundacional §2 — cada valle llega con sus 3 palancas de acción.
// Los dos primeros (gasto, ingreso) vienen resueltos vía `goal_seek`; el 3º
// (unidades) es un stub honesto (disponible=false) porque exige el pipeline
// completo (Mongo por iteración) que vive en FABS: la UI muestra un enlace
// en vez de un cero engañoso.
// RF-F7 · Fundacional §2 — "recomendaciones por impacto: reparto del recorte
// por rubro" (motor corrido al revés). Solo se adjunta a `recorte_gasto` cuando
// la palanca es alcanzable. Ordenado por gasto DESC. Todos los montos como
// string COP (regla 1); `pct_de_su_gasto` es un decimal como string (0.5000 =
// 50%, tope de la regla del 50% del backend).
export interface RecomendacionRubro {
  rubro_id: string;
  rubro_nombre: string;
  monto_recortar: string;
  gasto_actual: string;
  pct_de_su_gasto: string;
}

export interface PalancaMonto {
  monto: string;
  unidad: "COP/mes";
  alcanzable: boolean;
  referencia: string;
  mensaje: string;
  // RF-F7 — presente solo en `recorte_gasto` cuando `alcanzable && monto > 0`.
  recomendaciones_por_rubro?: RecomendacionRubro[];
}

export interface PalancaUnidades {
  monto: null;
  unidad: "motos/mes";
  alcanzable: false;
  disponible: false;
  ver_en: string;
  mes_referencia: string;
}

export interface PalancasValle {
  recorte_gasto: PalancaMonto;
  ingreso_extra: PalancaMonto;
  unidades_extra: PalancaUnidades;
}

export interface Valle {
  mes: string;
  caja: string;
  distancia_al_umbral: string; // negativo = perfora
  meses_para_prepararse: number; // desde hoy
  causas: CausaValle[];
  // RF-F3 · P2 — segmento del valle (solo cuando el umbral de atención está
  // configurado; null si no aplica). Todos vienen juntos o los tres son null.
  entrada?: string | null;
  salida?: string | null;
  duracion?: number | null;
  // RF-F5 · las 3 palancas por valle (opcional en el tipo por compat con mocks;
  // el backend siempre las emite hoy).
  palancas?: PalancasValle;
}

export interface Impactos {
  escenario: string;
  base: Proyeccion;
  ajustada: Proyeccion;
  valles_base: Valle[];
  valles_ajustada: Valle[];
  delta_por_mes: string[];
}

export interface Valles {
  escenario: string;
  caja_minima: string;
  // RF-F3 · P3a — umbral de atención (ámbar). null cuando no está configurado.
  caja_atencion?: string | null;
  valles: Valle[];
}

export interface EscenarioGuardado {
  id: string;
  nombre: string;
  descripcion: string | null;
  ajustes: Ajuste[];
  creado_por: string;
  actualizado_at: string;
  activo: boolean;
}

function qs(p: ProyeccionParams): string {
  const q = new URLSearchParams();
  if (p.escenario) q.set("escenario", p.escenario);
  if (p.horizonteMeses) q.set("horizonte_meses", String(p.horizonteMeses));
  if (p.mesInicio) q.set("mes_inicio", p.mesInicio);
  const s = q.toString();
  return s ? `?${s}` : "";
}

// ── §2 — proyección BASE vs CON AJUSTES (simular no escribe) ─────────────────
export async function proyectarImpactos(
  ajustes: Ajuste[],
  p: ProyeccionParams = {},
): Promise<Impactos> {
  return apiJson(`/proyeccion/impactos${qs(p)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ajustes }),
  });
}

// ── §3 — valles de la proyección vigente ─────────────────────────────────────
export async function obtenerValles(p: ProyeccionParams = {}): Promise<Valles> {
  return apiJson(`/proyeccion/valles${qs(p)}`);
}

// ── §5 — solvers ─────────────────────────────────────────────────────────────
export type VariableGoalSeek =
  | "ingreso_pct"
  | "ingreso_absoluto"
  | "gasto_absoluto";

export interface ResolverBody {
  objetivo:
    | "techo_gasto"
    | "techo_gasto_ventana" // RF-F4
    | "goal_seek"
    | "punto_quiebre";
  ajustes?: Ajuste[];
  colchon?: string; // techo_gasto
  variable?: VariableGoalSeek; // goal_seek
  objetivo_caja?: string; // goal_seek
  ventana_meses?: number; // RF-F4 · default 9
}

export interface TechoResultado {
  objetivo: "techo_gasto";
  techo_mensual: string;
  valle_limitante_mes: string;
  piso_resultante: string;
  meta: string;
  colchon: string;
  hay_holgura: boolean;
}

export interface GoalSeekResultado {
  objetivo: "goal_seek";
  variable: VariableGoalSeek;
  valor: string | null; // null = sin solución
  alcanzable: boolean;
  piso_resultante: string | null;
  objetivo_caja: string;
  mensaje: string;
}

export interface QuiebreResultado {
  objetivo: "punto_quiebre";
  valor: string | null;
  mes: string | null;
  perfora: boolean;
}

// RF-F4 — techo restringido a los primeros `ventana` meses, contra el umbral de
// atención (si está configurado; si no, contra el crítico). La bandera roja
// `perfora_atencion` la enciende el backend cuando el valle DE LA VENTANA (base,
// sin ajuste) ya está bajo la referencia.
export interface TechoVentanaResultado {
  objetivo: "techo_gasto_ventana";
  techo_mensual: string;
  valle_limitante_mes: string;
  piso_resultante: string;
  referencia: string;
  ventana: number;
  hay_holgura: boolean;
  perfora_atencion: boolean;
}

export type ResolverResultado =
  | TechoResultado
  | TechoVentanaResultado
  | GoalSeekResultado
  | QuiebreResultado;

export async function resolver(
  body: ResolverBody,
  p: ProyeccionParams = {},
): Promise<ResolverResultado> {
  return apiJson(`/proyeccion/resolver${qs(p)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// ── §2 — escenarios nombrados (CRUD auditado) ────────────────────────────────
export interface EscenarioInput {
  nombre: string;
  descripcion?: string | null;
  ajustes: Ajuste[];
}

export async function listarEscenarios(): Promise<EscenarioGuardado[]> {
  const r = await apiJson<{ items: EscenarioGuardado[] }>(
    "/escenarios-impacto",
  );
  return r.items;
}

export async function crearEscenario(
  input: EscenarioInput,
): Promise<EscenarioGuardado> {
  return apiJson("/escenarios-impacto", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export async function editarEscenario(
  id: string,
  input: Partial<EscenarioInput> & { activo?: boolean },
): Promise<EscenarioGuardado> {
  return apiJson(`/escenarios-impacto/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export async function eliminarEscenario(id: string): Promise<void> {
  await apiFetch(`/escenarios-impacto/${id}`, { method: "DELETE" });
}
