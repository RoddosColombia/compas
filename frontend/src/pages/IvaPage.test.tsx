// IVA (/iva) — shell de la pantalla: estado vacío accionable, cargando y error.
// La liquidación/tabla/titular se prueban en sus piezas. TODO cálculo en el backend.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { FacturaRow } from "@/lib/facturas";
import type { LiquidacionIva } from "@/lib/iva";
import IvaPage from "@/pages/IvaPage";

let facturasData: FacturaRow[] = [];
const LIQ_VACIA: LiquidacionIva = {
  periodicidad: "cuatrimestral",
  periodos: [],
};

vi.mock("@/lib/iva", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/iva")>();
  return { ...real, obtenerLiquidacionIva: () => Promise.resolve(LIQ_VACIA) };
});

vi.mock("@/lib/facturas", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/facturas")>();
  return { ...real, listarFacturas: () => Promise.resolve(facturasData) };
});

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <IvaPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("IvaPage — shell", () => {
  it("estado vacío accionable sin facturas cargadas", async () => {
    facturasData = [];
    renderPage();
    expect(
      await screen.findByText(/Aún no hay facturas cargadas/),
    ).toBeInTheDocument();
    // ofrece la acción (cierra el hallazgo Fase 0: el vacío llevaba a ningún lado)
    expect(
      screen.getAllByRole("button", { name: /Cargar facturas/ }).length,
    ).toBeGreaterThan(0);
  });
});
