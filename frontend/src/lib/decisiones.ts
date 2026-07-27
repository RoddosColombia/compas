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

export interface Valle {
  mes: string;
  caja: string;
  distancia_al_umbral: string; // negativo = perfora
  meses_para_prepararse: number; // desde hoy
  causas: CausaValle[];
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
  objetivo: "techo_gasto" | "goal_seek" | "punto_quiebre";
  ajustes?: Ajuste[];
  colchon?: string; // techo_gasto
  variable?: VariableGoalSeek; // goal_seek
  objetivo_caja?: string; // goal_seek
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

export type ResolverResultado =
  | TechoResultado
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
