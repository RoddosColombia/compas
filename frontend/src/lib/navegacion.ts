// Navegación del cockpit — ÚNICA fuente del árbol del sidebar (regla 9: la
// navegación se deriva de un solo config de permisos; prohibido mapear rol→UI
// disperso). El Sidebar filtra cada ítem por la capacidad requerida.
//
// Árbol del Blueprint UX (3 grupos, 8 vistas):
//   Principal            → Inicio · Proyecciones
//   Planeación y control → Escenarios · Presupuesto · IVA
//   Operación            → Dashboards · Reportes · Datos

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
  Layers,
  LineChart,
  Receipt,
  Repeat,
  Tags,
  Wallet,
} from "lucide-react";
import type { ComponentType } from "react";

export interface ItemNav {
  label: string;
  path: string;
  icon: ComponentType<{ className?: string }>;
  cap: string;
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
      // La Cabina (C2): el ciclo completo del mes en una sola vista.
      {
        label: "Mes en curso",
        path: "/mes",
        icon: Gauge,
        cap: "dashboard:leer",
      },
      {
        label: "Proyecciones",
        path: "/proyeccion",
        icon: LineChart,
        cap: "dashboard:leer",
      },
    ],
  },
  {
    titulo: "Planeación y control",
    items: [
      {
        label: "Escenarios",
        path: "/escenarios",
        icon: Layers,
        cap: "dashboard:leer",
      },
      // Ciclo mensual (C1): abrir mes → sugerido → acotar → aprobar. NavLink
      // marca activo también en /meses/:mes/presupuesto (match por prefijo).
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
    ],
  },
  {
    titulo: "Operación",
    items: [
      {
        label: "Flujo diario",
        path: "/flujo-diario",
        icon: CalendarDays,
        cap: "dashboard:leer",
      },
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
      // Datos = captura (caja inicial, supuestos, cargas) → requiere gestión.
      {
        label: "Datos",
        path: "/datos",
        icon: Database,
        cap: "cargas:gestionar",
      },
    ],
  },
  {
    // Administración presupuestal: catálogos y captura. (Nav provisional —
    // reubicación fina del árbol pendiente de Claude Cowork; aquí solo se
    // vuelven ALCANZABLES rutas que estaban huérfanas.)
    titulo: "Administración",
    items: [
      {
        label: "Gastos recurrentes",
        path: "/gastos-recurrentes",
        icon: Repeat,
        cap: "dashboard:leer",
      },
      {
        label: "Movimientos bancarios",
        path: "/cargas",
        icon: Banknote,
        cap: "cargas:gestionar",
      },
      { label: "Caja", path: "/caja", icon: Coins, cap: "dashboard:leer" },
      {
        label: "Categorías",
        path: "/categorias",
        icon: Tags,
        cap: "dashboard:leer",
      },
      { label: "Reglas", path: "/reglas", icon: Filter, cap: "dashboard:leer" },
    ],
  },
];
