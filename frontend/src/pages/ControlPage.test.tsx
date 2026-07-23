// frontend/src/pages/ControlPage.test.tsx
//
// C5: la pestaña "Por cuenta" muestra la matriz rubro×banco (columnas = bancos
// presentes), y "Por categoría" sigue siendo la vista por defecto. Read-only.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ControlPorCuenta, VistaControl } from "@/lib/control";
import ControlPage from "@/pages/ControlPage";

const CONTROL: VistaControl = {
  mes: "2026-07",
  estado: "en_ejecucion",
  grupos: [],
  total: { definido: "0.00", ejecutado: "0.00", disponible: "0.00" },
  caja_disponible: "0.00",
  sin_presupuesto: [],
};

const POR_CUENTA: ControlPorCuenta = {
  mes: "2026-07",
  estado: "en_ejecucion",
  bancos: ["bancolombia", "global66"],
  grupos: [
    {
      grupo: "operacion",
      lineas: [
        {
          rubro_id: "r1",
          rubro: "Arriendos",
          por_banco: { bancolombia: "600000.00", global66: "300000.00" },
          total: "900000.00",
        },
      ],
      subtotal: {
        por_banco: { bancolombia: "600000.00", global66: "300000.00" },
        total: "900000.00",
      },
    },
  ],
  total: {
    por_banco: { bancolombia: "600000.00", global66: "300000.00" },
    total: "900000.00",
  },
  sin_presupuesto: [],
};

vi.mock("@/lib/meses", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/meses")>();
  return {
    ...real,
    listarMeses: () =>
      Promise.resolve({
        items: [
          {
            id: "m1",
            mes: "2026-07-01",
            estado: "en_ejecucion",
            saldo_inicial_caja: "0.00",
            saldos_banco: [],
            ingresos_esperados_semana: null,
          },
        ],
      }),
  };
});

vi.mock("@/lib/control", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/control")>();
  return {
    ...real,
    vistaControl: () => Promise.resolve(CONTROL),
    vistaControlPorCuenta: () => Promise.resolve(POR_CUENTA),
  };
});

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ControlPage />
    </QueryClientProvider>,
  );
}

describe("ControlPage — C5 por cuenta", () => {
  it("al cambiar a 'Por cuenta' muestra la matriz rubro×banco", async () => {
    renderPage();
    // arranca en "Por categoría"
    expect(
      await screen.findByRole("button", { name: "Por cuenta" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Por cuenta" }));
    // columnas por banco + celda de la matriz
    expect(await screen.findByText("Bancolombia")).toBeInTheDocument();
    expect(screen.getByText("Global66")).toBeInTheDocument();
    expect(screen.getByText("Arriendos")).toBeInTheDocument();
    // aparece en la fila, el subtotal y el total (una sola línea)
    expect(screen.getAllByText("$ 600.000,00").length).toBeGreaterThan(0);
    expect(screen.getAllByText("$ 300.000,00").length).toBeGreaterThan(0);
  });
});
