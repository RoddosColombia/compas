// frontend/src/lib/proyeccion.ts
//
// COCK-03: cliente del motor de proyección (GET /api/v1/proyeccion). Compute-only;
// el backend calcula todo (motor C7). El front solo presenta. Montos como string
// (regla 1) → formatCOP; NUNCA Number sobre un monto.

import { apiJson } from "@/lib/api";

export type Escenario = "pesimista" | "base" | "optimista";
// RF-F3 · P3a: nivel intermedio 'atencion' (ámbar) entre 'ok' y 'critico'.
export type EstadoMes = "ok" | "atencion" | "critico" | "negativo";

// E1·P6 — marca de ORIGEN de la cifra (dimensión distinta de EstadoMes/salud de caja).
export type MarcaOrigen =
  | "cerrado"
  | "cerrado_sospechoso"
  | "en_ejecucion"
  | "presupuesto";

/**
 * El mes en curso: completitud (B13) + el TERMÓMETRO de desviación (P6 del ciclo
 * mensual). La curva muestra el OBJETIVO; esto muestra la realidad AL LADO, para
 * responder otra pregunta: ¿qué tan buenos son nuestros objetivos?
 *
 * Lo real es "a la fecha" (día `dia` de `dias_del_mes`) y lo proyectado es del MES
 * completo: la pantalla tiene que decirlo o una desviación a mitad de mes engaña.
 * Los campos del termómetro son opcionales (aditivos): `null` = sin dato cargado, que
 * NO es lo mismo que cero.
 */
export interface MesEnCurso {
  mes: string; // 'YYYY-MM'
  cargado_hasta: string | null; // 'YYYY-MM-DD' | null si aún sin tx
  dia: number | null;
  dias_del_mes?: number;
  formula: string; // cómo se armó el mes (P4: el presupuesto aprobado)
  ejecutado: string; // Σ egresos reales del mes a la fecha (COP)
  proyectado: string; // Σ presupuesto definido del mes (COP)
  // P6 — las otras dos lecturas del termómetro
  ingreso_real?: string | null;
  ingreso_real_inicial?: string | null;
  ingreso_real_semanal?: string | null;
  ingreso_proyectado?: string | null;
  ingreso_proyectado_inicial?: string | null;
  ingreso_proyectado_semanal?: string | null;
  colocaciones_meta?: number | null;
  colocaciones_reales?: number | null;
}

export interface MesProyeccion {
  mes: string; // 'YYYY-MM'
  motos: number;
  cartera: number;
  recaudo_credito: string; // Vía 1 (cuota-a-cuota)
  cuotas_iniciales: string; // Vía 2
  ingreso_bruto: string;
  neto: string;
  provision: string; // informativo (P&G/NIIF 9), NO en el flujo (caja veraz)
  gastos_fijos: string;
  gps: string;
  costo_nueva: string;
  adelanto: string;
  pago_inventario: string;
  fondeo: string;
  int_deuda: string;
  iva: string; // egreso de IVA neto en el mes DIAN (≤ 0); 0.00 fuera de ese mes
  aval: string; // SUP-2: reserva del fondo AVAL propio / autoseguro (≤ 0)
  /**
   * SUP-5: la EXPLICACIÓN del ingreso, no solo su total.
   * `neto = ingreso_bruto + mora + recuperacion + default`.
   * En un mes anclado a la ejecución real vienen en 0: su ingreso sale del libro.
   */
  mora: string; // ≤ 0 (lo que no llega este mes)
  recuperacion: string; // ≥ 0 (lo que vuelve de la mora de antes)
  default: string; // ≤ 0 (lo que se pierde y no vuelve)
  egresos: string;
  flujo: string;
  caja: string;
  estado: EstadoMes;
}

/**
 * SUP-5: los drivers que EXPLICAN la curva en pantalla — valores EFECTIVOS del
 * escenario que se está viendo (cada escenario tiene su propia mora desde SUP-2).
 */
export interface SupuestosProyeccion {
  pct_mora: string;
  pct_recuperacion: string;
  pct_default: string;
  pct_provision: string;
  meses_rezago_recuperacion: number;
  pct_aval_recaudo: string;
  pct_prefondeo_iva: string;
  motos_base: number;
  crec_pct_mensual: string;
  crec_pct_mensual_2: string | null;
  crec_mes_corte: number | null;
  rampa_unidades: Record<string, number>;
}

/**
 * P2 del ciclo mensual — la plata con la que arranca la serie y DE DÓNDE salió.
 * `origen`: 'ciclo' = el efectivo real del cierre del mes anterior (lo normal) ·
 * 'semilla' = el parámetro `caja_inicial` porque el mes no está abierto en el ciclo ·
 * 'override' = re-anclaje explícito (rolling forecast, COCK-09).
 */
export interface ArranqueCaja {
  valor: string;
  origen: "ciclo" | "semilla" | "override";
  mes: string | null; // 'YYYY-MM' del mes leído del ciclo
  saldo_declarado: string | null; // el saldo del ciclo, sin el tránsito
  transito_heredado: string; // CR-WAVA: cobrado que aún no está en el banco
}

// Fondo de provisión de IVA (P1.4): serie informativa mes a mes (NO es flujo del motor).
export interface FondoMes {
  mes: string; // 'YYYY-MM'
  reserva: string; // aporte al fondo ese mes
  pago: string; // salida del fondo (pago DIAN) ese mes
  saldo: string; // saldo acumulado del fondo
}

export interface Proyeccion {
  escenario: string;
  /** SUP-5: qué supone esta curva. Opcional: el preview no lo trae. */
  supuestos?: SupuestosProyeccion;
  /** P2: con qué plata arranca la serie y de dónde salió. Opcional (aditivo). */
  arranque?: ArranqueCaja | null;
  caja_minima: string; // el umbral crítico
  // RF-F3 · P3a — umbral de atención (ámbar). null cuando no está configurado.
  caja_atencion?: string | null;
  fondo_provision: FondoMes[];
  piso_caja: string;
  mes_mas_ajustado: string;
  meses_bajo_minimo: number;
  caja_final: string;
  capital_requerido: string;
  runway_meses: string | null;
  meses: MesProyeccion[];
  // D2 §4 — reconciliación de obligaciones (Auteco real vs. paramétrico):
  // [desde, hasta] de los meses con facturas reales, o null si no hay facturas.
  ventana_reconciliada: [string, string] | null;
  // interés real de obligaciones por mes de pago (string COP positivo). Es el MISMO
  // interés que ya vive dentro de `fondeo` (Costo) — solo para mostrar, jamás sumar.
  interes_obligaciones: Record<string, string>;
  // E1·P6 — origen de cada cifra (P5 shape). Opcionales en el tipo (aditivo, no rompe
  // consumidores/mocks viejos); el backend P5 SIEMPRE los emite. Consumir con ?? vacío.
  meses_anclados?: Record<string, MarcaOrigen>;
  sin_mapear?: string[];
  mes_en_curso?: MesEnCurso | null;
}

export const ESCENARIO_LABEL: Record<Escenario, string> = {
  pesimista: "Pesimista",
  base: "Base",
  optimista: "Optimista",
};

export const ESTADO_LABEL: Record<EstadoMes, string> = {
  ok: "OK",
  atencion: "Atención",
  critico: "Crítico",
  negativo: "Negativo",
};

export interface ProyeccionParams {
  escenario?: Escenario;
  horizonteMeses?: number;
  mesInicio?: string; // 'YYYY-MM'
}

export async function obtenerProyeccion(
  p: ProyeccionParams = {},
): Promise<Proyeccion> {
  const q = new URLSearchParams();
  if (p.escenario) q.set("escenario", p.escenario);
  if (p.horizonteMeses) q.set("horizonte_meses", String(p.horizonteMeses));
  if (p.mesInicio) q.set("mes_inicio", p.mesInicio);
  const qs = q.toString();
  return apiJson(`/proyeccion${qs ? `?${qs}` : ""}`);
}

// ── RF-F2: diff contra la última versión aprobada ──

export interface VersionDiff {
  hay_anterior: boolean;
  version_anterior?: number;
  mes_aprobado_anterior?: string;
  piso?: { anterior: string; actual: string; delta: string };
  mes_mas_ajustado?: { anterior: string; actual: string };
  valles?: {
    anterior: number;
    actual: number;
    nuevos: string[];
    desaparecidos: string[];
    // RF-F3 · P3b — valles que siguen en el MISMO mes pero con caja MENOR: el
    // valle empeoró contra la última aprobación. Categoría disjunta con `nuevos`.
    mas_profundos?: {
      mes: string;
      anterior: string;
      actual: string;
      delta: string; // negativo = más hondo
    }[];
  };
}

export async function obtenerVersionDiff(
  p: { escenario?: Escenario; horizonteMeses?: number } = {},
): Promise<VersionDiff> {
  const q = new URLSearchParams();
  if (p.escenario) q.set("escenario", p.escenario);
  if (p.horizonteMeses) q.set("horizonte_meses", String(p.horizonteMeses));
  const qs = q.toString();
  return apiJson(`/proyeccion/version/diff${qs ? `?${qs}` : ""}`);
}

// DASH-01: agregación operativa (Dashboards). Cartera activa desglosada por AÑADA
// (cohorte de colocación; 'previa' = los 111 créditos preexistentes) + colocación.
export interface AnadaCartera {
  anada: string; // 'YYYY-MM' | 'previa'
  activos: number;
}

export interface MesOperacion {
  mes: string; // 'YYYY-MM'
  colocacion: number;
  cartera: number;
  por_anada: AnadaCartera[];
}

export interface Operacion {
  escenario: string;
  meses: MesOperacion[];
}

export async function obtenerOperacion(
  p: ProyeccionParams = {},
): Promise<Operacion> {
  const q = new URLSearchParams();
  if (p.escenario) q.set("escenario", p.escenario);
  if (p.horizonteMeses) q.set("horizonte_meses", String(p.horizonteMeses));
  if (p.mesInicio) q.set("mes_inicio", p.mesInicio);
  const qs = q.toString();
  return apiJson(`/proyeccion/operacion${qs ? `?${qs}` : ""}`);
}

// COCK-09: actuals (caja real de bancos) vs proyección + rolling forecast.
export type AnclaModo = "cerrado" | "movimientos";

export interface Comparacion {
  escenario: string;
  ancla_modo: AnclaModo;
  ancla: { mes: string; caja_real: string } | null; // null si no hay mes ancla
  actuals: { mes: string; caja_real: string }[]; // tramo real (histórico)
  forecast: { mes: string; caja: string }[]; // proyección re-anclada
}

export interface ComparacionParams extends ProyeccionParams {
  ancla?: AnclaModo;
}

export async function obtenerComparacion(
  p: ComparacionParams = {},
): Promise<Comparacion> {
  const q = new URLSearchParams();
  if (p.escenario) q.set("escenario", p.escenario);
  if (p.ancla) q.set("ancla", p.ancla);
  if (p.horizonteMeses) q.set("horizonte_meses", String(p.horizonteMeses));
  if (p.mesInicio) q.set("mes_inicio", p.mesInicio);
  const qs = q.toString();
  return apiJson(`/proyeccion/comparar${qs ? `?${qs}` : ""}`);
}
