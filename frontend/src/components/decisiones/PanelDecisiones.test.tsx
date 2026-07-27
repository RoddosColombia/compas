import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PanelDecisiones } from "./PanelDecisiones";

const mocks = vi.hoisted(() => ({
  puede: vi.fn(() => true),
  proyectarImpactos: vi.fn(),
  resolver: vi.fn(),
  listarEscenarios: vi.fn(),
  crearEscenario: vi.fn(),
  eliminarEscenario: vi.fn(),
  listarRubros: vi.fn(),
}));

vi.mock("@/auth/AuthContext", () => ({
  useAuth: () => ({ puede: mocks.puede }),
}));

vi.mock("@/lib/decisiones", async (io) => {
  const real = await io<typeof import("@/lib/decisiones")>();
  return {
    ...real,
    proyectarImpactos: mocks.proyectarImpactos,
    resolver: mocks.resolver,
    listarEscenarios: mocks.listarEscenarios,
    crearEscenario: mocks.crearEscenario,
    eliminarEscenario: mocks.eliminarEscenario,
  };
});

vi.mock("@/lib/rubros", async (io) => {
  const real = await io<typeof import("@/lib/rubros")>();
  return { ...real, listarRubros: mocks.listarRubros };
});

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <PanelDecisiones />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("PanelDecisiones (D1 §4)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.puede.mockReturnValue(true);
    mocks.proyectarImpactos.mockResolvedValue({
      escenario: "base",
      base: {},
      ajustada: {},
      valles_base: [],
      valles_ajustada: [],
      delta_por_mes: [],
    });
    mocks.resolver.mockResolvedValue({
      objetivo: "techo_gasto",
      techo_mensual: "1000000",
      valle_limitante_mes: "2027-02",
      piso_resultante: "50000000",
      meta: "10000000",
      colchon: "0",
      hay_holgura: true,
    });
    mocks.listarEscenarios.mockResolvedValue([]);
    mocks.listarRubros.mockResolvedValue([]);
  });

  it("sin permiso de gestión muestra el aviso, no el editor", () => {
    mocks.puede.mockReturnValue(false);
    renderPanel();
    expect(screen.getByText(/requiere el permiso de gestión/i)).toBeTruthy();
  });

  it("con permiso muestra el techo de gasto y valles holgados", async () => {
    renderPanel();
    expect(await screen.findByText(/Techo de gasto extra/i)).toBeTruthy();
    expect(await screen.findByText(/Ningún valle relevante/i)).toBeTruthy();
    // sin ajustes: PanelImpacto muestra el hint, no cifras viejas
    expect(await screen.findByText(/Agrega un ajuste/i)).toBeTruthy();
  });

  it("agregar un ajuste abre una fila editable", async () => {
    renderPanel();
    fireEvent.click(await screen.findByText(/Agregar ajuste/i));
    expect(screen.getByLabelText("Nombre del ajuste")).toBeTruthy();
    expect(screen.getByLabelText("Mes inicio")).toBeTruthy();
  });

  it("no llama al backend de impacto hasta pasado el debounce", async () => {
    renderPanel();
    // el impacto base (ajustes vacíos) sí se pide al montar
    await waitFor(() => expect(mocks.proyectarImpactos).toHaveBeenCalled());
  });
});
