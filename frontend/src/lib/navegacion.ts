// Navegación del cockpit — ÚNICA fuente del árbol del sidebar (regla 9: la
// navegación se deriva de un solo config de permisos; prohibido mapear rol→UI
// disperso). El Sidebar filtra cada ítem por la capacidad requerida y colapsa
// automáticamente los items que declaran `subItems`.
//
// RV-V6/V7 (Fase B del navegador · 2026-09-01): 19 → 11 entradas top-level.
// El "mes" pasa a ser un objeto con 7 sub-vistas colapsables (Cabina · Ciclo ·
// Presupuesto · IVA · Metas · Obligaciones · Flujo diario), y los 3 catálogos
// (Categorías · Reglas · Semilla) se colapsan bajo "Catálogos". Las rutas
// individuales NO cambian — solo la presentación.

import {
  Banknote,
  BarChart3,
  CalendarDays,
  CalendarRange,
  Coins,
  Database,
  FileText,
  Filter,
  Gauge,
  Home,
  Landmark,
  Layers,
  LineChart,
  Receipt,
  Repeat,
  Settings2,
  Sprout,
  Tags,
  Target,
  Wallet,
} from "lucide-react";
import type { ComponentType } from "react";

export interface ItemNav {
  label: string;
  path: string;
  icon: ComponentType<{ className?: string }>;
  cap: string;
  /** RV-V6/V7: si trae subItems, el sidebar lo pinta como grupo colapsable
   * y `path` es solo el destino por default al hacer clic en el header (no
   * un enlace navegable en sí). El header se auto-expande cuando la ruta
   * actual matchea uno de los sub-paths. */
  subItems?: ItemNav[];
}

export interface GrupoNav {
  titulo: string;
  items: ItemNav[];
}

export const NAVEGACION: GrupoNav[] = [
  {
    titulo: "Principal",
    items: [
      { label: "Inicio", path: "/inicio", icon: Home, cap: "dashboard:leer" },
      {
        // RV-V6/V7: el mes como OBJETO con pestañas. Colapsa 7 vistas antes
        // dispersas (Mes en curso, Ciclo mensual, Presupuesto, IVA, Metas,
        // Obligaciones, Flujo diario) bajo un solo header. Los paths reales
        // no cambian — cada subitem sigue en su ruta actual.
        label: "Mes",
        path: "/mes",
        icon: Gauge,
        cap: "dashboard:leer",
        subItems: [
          { label: "Cabina", path: "/mes", icon: Gauge, cap: "dashboard:leer" },
          {
            label: "Ciclo mensual",
            path: "/meses",
            icon: CalendarRange,
            cap: "dashboard:leer",
          },
          {
            label: "Presupuesto",
            path: "/control",
            icon: Wallet,
            cap: "dashboard:leer",
          },
          { label: "IVA", path: "/iva", icon: Receipt, cap: "dashboard:leer" },
          {
            label: "Metas de ingreso",
            path: "/metas",
            icon: Target,
            cap: "dashboard:leer",
          },
          {
            label: "Obligaciones",
            path: "/obligaciones",
            icon: Landmark,
            cap: "dashboard:leer",
          },
          {
            label: "Flujo diario",
            path: "/flujo-diario",
            icon: CalendarDays,
            cap: "dashboard:leer",
          },
        ],
      },
      {
        label: "Proyecciones",
        path: "/proyeccion",
        icon: LineChart,
        cap: "dashboard:leer",
      },
      {
        label: "Escenarios",
        path: "/escenarios",
        icon: Layers,
        cap: "dashboard:leer",
      },
    ],
  },
  {
    titulo: "Análisis",
    items: [
      {
        label: "Dashboards",
        path: "/dashboards",
        icon: BarChart3,
        cap: "dashboard:leer",
      },
      {
        label: "Reportes",
        path: "/reportes",
        icon: FileText,
        cap: "dashboard:leer",
      },
    ],
  },
  {
    titulo: "Configuración",
    items: [
      // Supuestos (C3): el editor de los drivers del motor, con impacto en vivo.
      {
        label: "Supuestos",
        path: "/datos",
        icon: Database,
        cap: "cargas:gestionar",
      },
      {
        // Datos maestros — Categorías + Reglas + Semilla de reglas colapsados.
        label: "Catálogos",
        path: "/categorias",
        icon: Settings2,
        cap: "dashboard:leer",
        subItems: [
          {
            label: "Categorías",
            path: "/categorias",
            icon: Tags,
            cap: "dashboard:leer",
          },
          {
            label: "Reglas",
            path: "/reglas",
            icon: Filter,
            cap: "dashboard:leer",
          },
          {
            label: "Semilla de reglas",
            path: "/reglas/semilla",
            icon: Sprout,
            cap: "reglas:gestionar",
          },
        ],
      },
    ],
  },
  {
    titulo: "Bancos",
    items: [
      {
        label: "Movimientos bancarios",
        path: "/cargas",
        icon: Banknote,
        cap: "cargas:gestionar",
      },
      { label: "Caja", path: "/caja", icon: Coins, cap: "dashboard:leer" },
      {
        label: "Gastos recurrentes",
        path: "/gastos-recurrentes",
        icon: Repeat,
        cap: "dashboard:leer",
      },
    ],
  },
];
