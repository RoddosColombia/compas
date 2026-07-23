// frontend/src/pages/ReglasPage.test.tsx
//
// C3 pantalla de reglas: bloques por tipo (partición D1-ii visible), botones de
// mutación solo con reglas:gestionar (regla 9), propuesta APRENDIDA con botón
// Aprobar, y aviso "categoría inactiva" (D2) cuando el rubro destino está
// desactivado.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Regla } from "@/lib/reglas";
import type { Rubro } from "@/lib/rubros";
import ReglasPage from "@/pages/ReglasPage";

const RUBROS: Rubro[] = [
  {
    id: "r-caf",
    grupo: "operacion",
    nombre: "Cafetería",
    tipo_flujo: "egreso",
    orden: 1,
    activo: true,
    es_sistema: false,
  },
  {
    id: "r-rent",
    grupo: "operacion",
    nombre: "Renting",
    tipo_flujo: "egreso",
    orden: 2,
    activo: false,
    es_sistema: false,
  },
  {
    id: "r-rec",
    grupo: "otros",
    nombre: "Recaudo",
    tipo_flujo: "ingreso",
    orden: 34,
    activo: true,
    es_sistema: true,
  },
];

const REGLAS: Regla[] = [
  {
    id: "g1",
    patron: "cafeteria",
    patron_normalizado: "cafeteria",
    rubro_id: "r-caf",
    tipo_flujo: "egreso",
    prioridad: 10,
    origen: "manual",
    activa: true,
    creada_por: "u1",
  },
  {
    id: "g2",
    patron: "renting",
    patron_normalizado: "renting",
    rubro_id: "r-rent", // rubro INACTIVO → aviso D2
    tipo_flujo: "egreso",
    prioridad: 20,
    origen: "manual",
    activa: true,
    creada_por: "u1",
  },
  {
    id: "g3",
    patron: "Abono",
    patron_normalizado: "abono",
    rubro_id: "r-rec",
    tipo_flujo: "ingreso",
    prioridad: 1,
    origen: "aprendida",
    activa: false, // propuesta pendiente de aprobar (§1.9)
    creada_por: "u2",
  },
];

const puedeMock = vi.fn();

vi.mock("@/auth/AuthContext", () => ({
  useAuth: () => ({ puede: puedeMock, rol: "financiero" }),
}));

vi.mock("@/lib/reglas", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/reglas")>();
  return { ...real, listarReglas: () => Promise.resolve(REGLAS) };
});

vi.mock("@/lib/rubros", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/rubros")>();
  return { ...real, listarRubros: () => Promise.resolve(RUBROS) };
});

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ReglasPage />
    </QueryClientProvider>,
  );
}

describe("ReglasPage", () => {
  it("agrupa por tipo y muestra destino + aviso de categoría inactiva (D2)", async () => {
    puedeMock.mockImplementation(() => true);
    renderPage();
    expect(await screen.findByText("cafeteria")).toBeInTheDocument();
    expect(screen.getByText("Egresos")).toBeInTheDocument();
    expect(screen.getByText("Ingresos")).toBeInTheDocument();
    // 'Cafetería' sale en la celda destino Y como <option> del form de creación.
    expect(screen.getAllByText("Cafetería").length).toBeGreaterThan(0);
    // D2: regla activa apuntando a rubro inactivo → aviso + estado "Sin efecto".
    expect(screen.getByText("categoría inactiva")).toBeInTheDocument();
    expect(screen.getByText("Sin efecto")).toBeInTheDocument();
  });

  it("propuesta aprendida muestra botón Aprobar y NO Reactivar (§1.9)", async () => {
    puedeMock.mockImplementation(() => true);
    renderPage();
    await screen.findByText("Abono");
    expect(screen.getByText("Propuesta")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Aprobar" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reactivar" })).toBeNull();
  });

  it("con reglas:gestionar muestra acciones, form y aplicar-pendientes", async () => {
    puedeMock.mockImplementation(() => true);
    renderPage();
    await screen.findByText("cafeteria");
    expect(screen.getAllByRole("button", { name: "Editar" }).length).toBe(3);
    expect(
      screen.getByRole("button", { name: "Aplicar a pendientes" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Nueva regla")).toBeInTheDocument();
  });

  it("sin reglas:gestionar es solo-lectura (regla 9)", async () => {
    puedeMock.mockImplementation(() => false);
    renderPage();
    expect(await screen.findByText("cafeteria")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Editar" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Aprobar" })).toBeNull();
    expect(
      screen.queryByRole("button", { name: "Aplicar a pendientes" }),
    ).toBeNull();
    expect(screen.queryByText("Nueva regla")).toBeNull();
  });
});
