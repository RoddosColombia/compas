// IVA — la vista liquida por período y muestra el próximo pago, el saldo a favor y el
// fondo de provisión. Comportamiento probado: tabla de períodos, KPI de próximo pago,
// y estado vacío cuando no hay facturas cargadas.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { LiquidacionIva } from "@/lib/iva";
import type { FondoMes, Proyeccion } from "@/lib/proyeccion";
import IvaPage from "@/pages/IvaPage";

const LIQ: LiquidacionIva = {
  periodicidad: "cuatrimestral",
  periodos: [
    {
      anio: 2026,
      periodo: 1,
      etiqueta: "2026-C1",
      generado: "190000.00",
      descontable: "95000.00",
      saldo: "95000.00",
      saldo_favor_previo: "0.00",
      neto_a_pagar: "95000.00",
      saldo_favor_nuevo: "0.00",
    },
  ],
};

const FONDO: FondoMes[] = [
  { mes: "2026-01", reserva: "23750.00", pago: "0.00", saldo: "23750.00" },
  { mes: "2026-05", reserva: "0.00", pago: "95000.00", saldo: "0.00" },
];

let liqData: LiquidacionIva = LIQ;

vi.mock("@/lib/iva", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/iva")>();
  return { ...real, obtenerLiquidacionIva: () => Promise.resolve(liqData) };
});

vi.mock("@/lib/proyeccion", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/proyeccion")>();
  return {
    ...real,
    obtenerProyeccion: () =>
      Promise.resolve({ fondo_provision: FONDO } as Proyeccion),
  };
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

describe("IvaPage", () => {
  it("muestra el próximo pago y la liquidación por período", async () => {
    liqData = LIQ;
    renderPage();
    expect(
      await screen.findByText("Próximo pago a la DIAN"),
    ).toBeInTheDocument();
    // el período (en el KPI y en la tabla) y su neto a pagar aparecen (formateados)
    expect(screen.getAllByText("2026-C1").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/95\.000,00/).length).toBeGreaterThan(0);
    // el fondo de provisión se muestra
    expect(screen.getByText("Fondo de provisión")).toBeInTheDocument();
  });

  it("muestra estado vacío sin facturas cargadas", async () => {
    liqData = { periodicidad: "cuatrimestral", periodos: [] };
    renderPage();
    expect(
      await screen.findByText(/Aún no hay facturas cargadas/),
    ).toBeInTheDocument();
  });
});
