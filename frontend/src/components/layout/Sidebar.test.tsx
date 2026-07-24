// Sidebar del cockpit: árbol del Blueprint derivado de capacidades (regla 9).
// Comportamiento probado: (1) muestra grupos+ítems permitidos, (2) oculta el ítem
// cuya capacidad falta, (3) marca activo el de la ruta actual (aria-current).

import { render, screen } from "@testing-library/react";
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
  it("muestra los 3 grupos y las 8 vistas cuando hay permiso pleno", () => {
    renderEn("/proyeccion", () => true);
    for (const g of ["Principal", "Planeación y control", "Operación"]) {
      expect(screen.getByText(g)).toBeInTheDocument();
    }
    for (const v of [
      "Inicio",
      "Proyecciones",
      "Escenarios",
      "Presupuesto",
      "IVA",
      "Dashboards",
      "Reportes",
      "Datos",
    ]) {
      expect(screen.getByRole("link", { name: v })).toBeInTheDocument();
    }
  });

  it("oculta Datos si falta cargas:gestionar", () => {
    renderEn("/proyeccion", (cap) => cap !== "cargas:gestionar");
    expect(
      screen.queryByRole("link", { name: "Datos" }),
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
