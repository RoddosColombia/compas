// frontend/src/pages/CajaPage.test.tsx
//
// C4 pantalla de caja: muestra los saldos por banco del mes en ejecución, el
// formulario de reporte solo con caja:reportar (regla 9), y es solo-lectura sin la
// capacidad. El "¿cuadra?" y los cálculos vienen del backend.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Mes } from "@/lib/meses";
import CajaPage from "@/pages/CajaPage";

const MESES: { items: Mes[] } = {
  items: [
    {
      id: "m1",
      mes: "2026-07-01",
      estado: "en_ejecucion",
      saldo_inicial_caja: "0.00",
      saldos_banco: [
        { banco: "global66", saldo: "1000000.00", fecha_reporte: "2026-07-15" },
      ],
      ingresos_esperados_semana: null,
    },
    {
      id: "m0",
      mes: "2026-06-01",
      estado: "cerrado",
      saldo_inicial_caja: "0.00",
      saldos_banco: [],
      ingresos_esperados_semana: null,
    },
  ],
};

const puedeMock = vi.fn();

vi.mock("@/auth/AuthContext", () => ({
  useAuth: () => ({ puede: puedeMock, rol: "financiero" }),
}));

vi.mock("@/lib/meses", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/meses")>();
  return { ...real, listarMeses: () => Promise.resolve(MESES) };
});

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <CajaPage />
    </QueryClientProvider>,
  );
}

describe("CajaPage", () => {
  it("muestra los saldos del mes en ejecución y el formulario con caja:reportar", async () => {
    puedeMock.mockImplementation(() => true);
    renderPage();
    // saldo reportado del mes en ejecución (formato COP es-CO)
    expect(await screen.findByText("$ 1.000.000,00")).toBeInTheDocument();
    // "Global66" sale en la fila de saldos Y como <option> del formulario
    expect(screen.getAllByText("Global66").length).toBeGreaterThan(0);
    // formulario de reporte visible con la capacidad
    expect(screen.getByText("Reportar saldo")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Reportar" }),
    ).toBeInTheDocument();
  });

  it("sin caja:reportar es solo-lectura (regla 9)", async () => {
    puedeMock.mockImplementation(() => false);
    renderPage();
    // los saldos se ven (dashboard), pero el formulario de reporte no
    expect(await screen.findByText("Global66")).toBeInTheDocument();
    expect(screen.queryByText("Reportar saldo")).toBeNull();
    expect(screen.queryByRole("button", { name: "Reportar" })).toBeNull();
  });
});
