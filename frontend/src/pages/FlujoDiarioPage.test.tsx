// Flujo de caja diario — muestra la evolución día a día con la data real.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CajaDiaria } from "@/lib/caja";
import FlujoDiarioPage from "@/pages/FlujoDiarioPage";

const DATA: CajaDiaria = {
  desde: "2026-03-01",
  hasta: "2026-07-31",
  caja_inicial: "0.00",
  total_ingresos: "5800000.00",
  total_egresos: "800000.00",
  flujo_neto: "5000000.00",
  caja_final: "5000000.00",
  dias: [
    {
      fecha: "2026-03-05",
      ingresos: "5800000.00",
      egresos: "800000.00",
      flujo: "5000000.00",
      caja: "5000000.00",
      n: 3,
    },
  ],
};

vi.mock("@/lib/caja", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/caja")>();
  return { ...real, obtenerCajaDiaria: () => Promise.resolve(DATA) };
});

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <FlujoDiarioPage />
    </QueryClientProvider>,
  );
}

describe("FlujoDiarioPage", () => {
  it("muestra los KPIs y la fila del día con la evolución del saldo", async () => {
    renderPage();
    expect(
      await screen.findByRole("heading", { name: "Flujo de caja diario" }),
    ).toBeInTheDocument();
    // el saldo final del día aparece formateado en COP
    expect(await screen.findByText("Saldo final")).toBeInTheDocument();
    expect(screen.getAllByText(/5\.000\.000/).length).toBeGreaterThan(0);
  });
});
