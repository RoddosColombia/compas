// frontend/src/pages/CategoriasPage.test.tsx
//
// C1 categorías administrables: agrupación por grupo (§1.2), botones de mutación
// solo con rubros:gestionar (regla 9), sistema inmutable sin acciones, y el
// helper agruparRubros ordena por `orden` dentro del grupo.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { type Rubro, agruparRubros } from "@/lib/rubros";
import CategoriasPage from "@/pages/CategoriasPage";

const RUBROS: Rubro[] = [
  {
    id: "r1",
    grupo: "operacion",
    nombre: "Cafetería",
    tipo_flujo: "egreso",
    codigo: "2060",
    tipo: "variable",
    orden: 2,
    activo: true,
    es_sistema: false,
  },
  {
    id: "r2",
    grupo: "operacion",
    nombre: "Freelance",
    tipo_flujo: "egreso",
    codigo: "2140",
    tipo: "variable",
    orden: 1,
    activo: false,
    es_sistema: false,
  },
  {
    id: "r3",
    grupo: "ingresos_operativos",
    nombre: "Recaudo de cartera",
    tipo_flujo: "ingreso",
    codigo: "0110",
    tipo: "variable",
    orden: 1,
    activo: true,
    es_sistema: true,
  },
];

const puedeMock = vi.fn();

vi.mock("@/auth/AuthContext", () => ({
  useAuth: () => ({ puede: puedeMock, rol: "financiero" }),
}));

vi.mock("@/lib/rubros", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/rubros")>();
  return { ...real, listarRubros: () => Promise.resolve(RUBROS) };
});

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <CategoriasPage />
    </QueryClientProvider>,
  );
}

describe("agruparRubros (plan de cuentas)", () => {
  it("agrupa en el orden canónico (ingresos primero) y ordena por `orden`", () => {
    const grupos = agruparRubros(RUBROS);
    expect([...grupos.keys()]).toEqual(["ingresos_operativos", "operacion"]);
    expect(grupos.get("operacion")?.map((r) => r.nombre)).toEqual([
      "Freelance",
      "Cafetería",
    ]);
  });
});

describe("CategoriasPage", () => {
  it("con rubros:gestionar muestra acciones y el formulario de creación", async () => {
    puedeMock.mockImplementation(() => true);
    renderPage();
    expect(await screen.findByText("Cafetería")).toBeInTheDocument();
    // Fila normal activa → Editar/Desactivar; inactiva → Reactivar.
    expect(screen.getAllByRole("button", { name: "Editar" })).toHaveLength(2);
    expect(
      screen.getByRole("button", { name: "Desactivar" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Reactivar" }),
    ).toBeInTheDocument();
    // Sistema inmutable: sin botones, marcado.
    expect(screen.getByText("Inmutable")).toBeInTheDocument();
    expect(screen.getByText("Sistema")).toBeInTheDocument();
    // Form de creación visible.
    expect(screen.getByText("Nueva categoría")).toBeInTheDocument();
  });

  it("sin rubros:gestionar es solo-lectura (regla 9: UI desde capacidades)", async () => {
    puedeMock.mockImplementation(() => false);
    renderPage();
    expect(await screen.findByText("Cafetería")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Editar" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Desactivar" })).toBeNull();
    expect(screen.queryByText("Nueva categoría")).toBeNull();
    // La data sigue visible (GET es dashboard:leer).
    expect(screen.getByText("Recaudo de cartera")).toBeInTheDocument();
  });

  it("muestra estados: Activa / Inactiva / Sistema", async () => {
    puedeMock.mockImplementation(() => true);
    renderPage();
    await screen.findByText("Cafetería");
    expect(screen.getByText("Activa")).toBeInTheDocument();
    expect(screen.getByText("Inactiva")).toBeInTheDocument();
    expect(screen.getByText("Sistema")).toBeInTheDocument();
  });

  // RF-F9 · Fundacional §2 — «Plan de cuentas completo».

  it("RF-F9: el botón «Crear» se deshabilita hasta que nombre, código y clase estén llenos", async () => {
    puedeMock.mockImplementation(() => true);
    renderPage();
    await screen.findByText("Nueva categoría");
    const crear = screen.getByRole("button", { name: /crear/i });
    // El estado inicial: nombre "", código "", clase "variable" (default).
    // Falta nombre y código → botón deshabilitado.
    expect(crear).toBeDisabled();
    // Llenar solo el nombre → sigue deshabilitado (falta código).
    fireEvent.change(screen.getByLabelText(/nombre/i), {
      target: { value: "Nueva cat" },
    });
    expect(crear).toBeDisabled();
    // Llenar código → habilitado.
    fireEvent.change(screen.getByLabelText(/código/i), {
      target: { value: "2900" },
    });
    expect(crear).toBeEnabled();
    // Blanquear código de nuevo → vuelve a deshabilitarse.
    fireEvent.change(screen.getByLabelText(/código/i), { target: { value: "" } });
    expect(crear).toBeDisabled();
  });

  it("RF-F9: la clase no ofrece la opción vacía; sale con «variable» por defecto", async () => {
    puedeMock.mockImplementation(() => true);
    renderPage();
    await screen.findByText("Nueva categoría");
    const clase = screen.getByLabelText(/clase/i) as HTMLSelectElement;
    // No hay opción vacía (RF-F9 obliga la clase).
    const opciones = Array.from(clase.options).map((o) => o.value);
    expect(opciones).toEqual(["fijo", "variable"]);
    expect(clase.value).toBe("variable");
  });
});
