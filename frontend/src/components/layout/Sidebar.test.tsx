// Sidebar del cockpit: árbol del Blueprint derivado de capacidades (regla 9).
// Comportamiento probado: (1) muestra grupos+ítems permitidos, (2) oculta el ítem
// cuya capacidad falta, (3) marca activo el de la ruta actual (aria-current).

import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { Sidebar } from "@/components/layout/Sidebar";

function renderEn(pathname: string, puede: (cap: string) => boolean) {
  return render(
    <MemoryRouter initialEntries={[pathname]}>
      <Sidebar rol="admin" puede={puede} onCerrarSesion={vi.fn()} />
    </MemoryRouter>,
  );
}

describe("Sidebar", () => {
  it("muestra los 4 grupos y las vistas top-level cuando hay permiso pleno", () => {
    // RV-V6/V7 · Fase B (2026-09-01): 4 grupos (Principal · Análisis ·
    // Configuración · Bancos), 11 items top-level. Los 4 items dentro de
    // grupos colapsables (Mes · Catálogos) NO son visibles por default —
    // se prueban por separado más abajo.
    renderEn("/proyeccion", () => true);
    for (const g of ["Principal", "Análisis", "Configuración", "Bancos"]) {
      expect(screen.getByText(g)).toBeInTheDocument();
    }
    // Los 9 items top-level que son links directos (no colapsables)
    for (const v of [
      "Inicio",
      "Proyecciones",
      "Escenarios",
      "Dashboards",
      "Reportes",
      "Supuestos",
      "Movimientos bancarios",
      "Caja",
      "Gastos recurrentes",
    ]) {
      expect(screen.getByRole("link", { name: v })).toBeInTheDocument();
    }
    // Los 2 items colapsables (Mes · Catálogos) son BUTTONS, no links
    expect(screen.getByRole("button", { name: /^Mes/ })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /^Catálogos/ }),
    ).toBeInTheDocument();
  });

  it("oculta Supuestos si falta cargas:gestionar", () => {
    renderEn("/proyeccion", (cap) => cap !== "cargas:gestionar");
    expect(
      screen.queryByRole("link", { name: "Supuestos" }),
    ).not.toBeInTheDocument();
    // el resto sigue visible
    expect(
      screen.getByRole("link", { name: "Proyecciones" }),
    ).toBeInTheDocument();
  });

  it("marca activa la vista de la ruta actual", () => {
    renderEn("/proyeccion", () => true);
    const activa = screen.getByRole("link", { name: "Proyecciones" });
    expect(activa).toHaveAttribute("aria-current", "page");
    const otra = screen.getByRole("link", { name: "Inicio" });
    expect(otra).not.toHaveAttribute("aria-current", "page");
  });

  it("muestra el rol y permite cerrar sesión", () => {
    const onCerrarSesion = vi.fn();
    render(
      <MemoryRouter>
        <Sidebar
          rol="admin"
          puede={() => true}
          onCerrarSesion={onCerrarSesion}
        />
      </MemoryRouter>,
    );
    expect(screen.getByText("admin")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /salir/i })).toBeInTheDocument();
  });
});

// ─── RV-V6/V7: Fase B del navegador · 19 → 11 entradas top-level ────────────
// El sidebar colapsa las 6 vistas del MES bajo un solo grupo "Mes" (7 subitems
// con el mismo path que tenían antes; solo cambia la presentación) y los 3
// catálogos bajo "Datos maestros". Total visible al top: 11 items en 4 grupos.

import { NAVEGACION } from "@/lib/navegacion";

describe("RV-V6/V7 · Fase B del navegador (19→11 entradas)", () => {
  it("el top-level suma exactamente 11 items (Fase B del Blueprint)", () => {
    const topLevel = NAVEGACION.flatMap((g) => g.items);
    expect(topLevel).toHaveLength(11);
  });

  it("existe un grupo `Mes` colapsable con las 7 sub-vistas del mes", () => {
    const mes = NAVEGACION.flatMap((g) => g.items).find(
      (i) => i.label === "Mes",
    );
    expect(mes).toBeDefined();
    expect(mes?.subItems).toBeDefined();
    // 7 sub-vistas: Cabina · Ciclo · Presupuesto · IVA · Metas · Obligaciones · Flujo diario
    expect(mes?.subItems).toHaveLength(7);
    const labels = mes?.subItems?.map((s) => s.label) ?? [];
    expect(labels).toEqual(
      expect.arrayContaining([
        "Cabina",
        "Ciclo mensual",
        "Presupuesto",
        "IVA",
        "Metas de ingreso",
        "Obligaciones",
        "Flujo diario",
      ]),
    );
  });

  it("existe un grupo `Catálogos` colapsable con las 3 vistas de datos maestros", () => {
    const cat = NAVEGACION.flatMap((g) => g.items).find(
      (i) => i.label === "Catálogos",
    );
    expect(cat).toBeDefined();
    expect(cat?.subItems).toHaveLength(3);
    const labels = cat?.subItems?.map((s) => s.label) ?? [];
    expect(labels).toEqual(
      expect.arrayContaining(["Categorías", "Reglas", "Semilla de reglas"]),
    );
  });

  it("el grupo `Mes` se expande automáticamente cuando la ruta actual es una sub-vista", () => {
    renderEn("/control", () => true); // /control = Presupuesto (sub-vista de Mes)
    // El label del padre aparece
    expect(screen.getByRole("button", { name: /^Mes/ })).toBeInTheDocument();
    // Los sub-items son visibles (expandido)
    expect(
      screen.getByRole("link", { name: "Presupuesto" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "IVA" })).toBeInTheDocument();
  });

  it("el grupo `Mes` está colapsado por default cuando la ruta NO es una sub-vista", () => {
    renderEn("/proyeccion", () => true);
    // El botón del grupo existe
    const boton = screen.getByRole("button", { name: /^Mes/ });
    expect(boton).toBeInTheDocument();
    // aria-expanded=false por default
    expect(boton).toHaveAttribute("aria-expanded", "false");
    // Los sub-items NO son visibles (colapsado)
    expect(
      screen.queryByRole("link", { name: "Presupuesto" }),
    ).not.toBeInTheDocument();
  });

  it("el clic en el grupo colapsable lo abre y expone los sub-items", () => {
    renderEn("/proyeccion", () => true);
    const boton = screen.getByRole("button", { name: /^Mes/ });
    expect(boton).toHaveAttribute("aria-expanded", "false");
    // Clic vía RTL (dispara el handler de React y aplica el state update)
    act(() => {
      fireEvent.click(boton);
    });
    // Ahora los sub-items son visibles
    expect(
      screen.getByRole("link", { name: "Presupuesto" }),
    ).toBeInTheDocument();
    expect(boton).toHaveAttribute("aria-expanded", "true");
  });

  it("un grupo colapsable oculta subitems por permisos (Semilla de reglas exige reglas:gestionar)", () => {
    // Con permiso pleno excepto reglas:gestionar
    renderEn("/reglas", (cap) => cap !== "reglas:gestionar");
    // Datos maestros se auto-expande (la ruta actual /reglas pertenece).
    expect(screen.getByRole("link", { name: "Reglas" })).toBeInTheDocument();
    // "Semilla de reglas" NO debe aparecer (filtrada por capacidad)
    expect(
      screen.queryByRole("link", { name: "Semilla de reglas" }),
    ).not.toBeInTheDocument();
  });
});
