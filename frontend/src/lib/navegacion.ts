// Navegación del cockpit — ÚNICA fuente del árbol del sidebar (regla 9: la
// navegación se deriva de un solo config de permisos; prohibido mapear rol→UI
// disperso). El Sidebar filtra cada ítem por la capacidad requerida.
//
// Árbol del Blueprint UX (3 grupos, 8 vistas):
//   Principal            → Inicio · Proyecciones
//   Planeación y control → Escenarios · Presupuesto · IVA
//   Operación            → Dashboards · Reportes · Datos

import {
  BarChart3,
  Database,
  FileText,
  Home,
  Layers,
  LineChart,
  Receipt,
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
];
