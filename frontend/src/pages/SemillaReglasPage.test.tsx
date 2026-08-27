// RF-F1 — Semilla de reglas: el reporte se pinta agrupado, las de riesgo vienen
// desmarcadas, y "Sembrar" manda solo las seleccionadas.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import SemillaReglasPage from "@/pages/SemillaReglasPage";

const mocks = vi.hoisted(() => ({
  obtenerSemilla: vi.fn(),
  sembrarSemilla: vi.fn(),
}));

vi.mock("@/lib/reglas", () => ({
  obtenerSemilla: mocks.obtenerSemilla,
  sembrarSemilla: mocks.sembrarSemilla,
}));

vi.mock("@/auth/AuthContext", () => ({
  useAuth: () => ({ puede: () => true, rol: "financiero" }),
}));

const REPORTE = {
  total_movimientos: 100,
  parametros: {},
  propuestas: [
    {
      patron: "uber",
      rubro_id: "r1",
      rubro: "Transporte",
      tipo_flujo: "egreso",
      evidencia: 40,
      pureza: "1",
      prioridad: 100,
      ejemplos: ["Compra en Uber rides"],
      colisiona: false,
    },
    {
      patron: "inc",
      rubro_id: "r2",
      rubro: "Tecnología",
      tipo_flujo: "egreso",
      evidencia: 5,
      pureza: "1",
      prioridad: 101,
      ejemplos: ["Compra en Vercel inc"],
      colisiona: false,
    },
    {
      patron: "gmf",
      rubro_id: "r3",
      rubro: "Impuestos",
      tipo_flujo: "egreso",
      evidencia: 300,
      pureza: "1",
      prioridad: 102,
      ejemplos: ["GMF 4x1000"],
      colisiona: true, // ya cubierta → no seleccionable
    },
  ],
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <SemillaReglasPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("SemillaReglasPage", () => {
  it("pinta las propuestas nuevas y excluye las que ya existen", async () => {
    mocks.obtenerSemilla.mockResolvedValue(REPORTE);
    renderPage();
    expect(await screen.findByText("uber")).toBeInTheDocument();
    expect(screen.getByText("inc")).toBeInTheDocument();
    expect(screen.queryByText("gmf")).not.toBeInTheDocument(); // colisiona
  });

  it("la de 3 letras viene desmarcada; siembra solo las seleccionadas", async () => {
    mocks.obtenerSemilla.mockResolvedValue(REPORTE);
    mocks.sembrarSemilla.mockResolvedValue({
      creadas: 1,
      ya_existian: 0,
      errores: 0,
      detalle_errores: [],
    });
    renderPage();
    const uber = (await screen.findByLabelText("uber")) as HTMLInputElement;
    const inc = screen.getByLabelText("inc") as HTMLInputElement;
    expect(uber.checked).toBe(true); // segura → marcada
    expect(inc.checked).toBe(false); // "3 letras" → desmarcada

    fireEvent.click(screen.getByRole("button", { name: /Sembrar 1/ }));
    await waitFor(() => expect(mocks.sembrarSemilla).toHaveBeenCalledTimes(1));
    expect(mocks.sembrarSemilla).toHaveBeenCalledWith([
      { patron: "uber", rubro_id: "r1", tipo_flujo: "egreso" },
    ]);
  });
});
