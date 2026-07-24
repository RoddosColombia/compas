// frontend/src/pages/ProyeccionPage.test.tsx
//
// COCK-03: la vista Proyecciones. Verifica que el ingreso se muestra DISCRIMINADO
// (recaudo de crédito vs cuota inicial), los KPIs del motor (piso, capital requerido,
// meses bajo mínimo) y el selector de escenario. Todo lo calcula el backend; el front
// solo presenta.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Proyeccion } from "@/lib/proyeccion";
import ProyeccionPage from "@/pages/ProyeccionPage";

const PROY: Proyeccion = {
  escenario: "base",
  caja_minima: "125000000.00",
  piso_caja: "40000000.00",
  mes_mas_ajustado: "2026-09",
  meses_bajo_minimo: 2,
  caja_final: "200000000.00",
  capital_requerido: "85000000.00",
  runway_meses: null,
  meses: [
    {
      mes: "2026-07",
      motos: 50,
      cartera: 120,
      recaudo_credito: "30000000.00",
      cuotas_iniciales: "5000000.00",
      ingreso_bruto: "35000000.00",
      neto: "34000000.00",
      provision: "-700000.00",
      gastos_fijos: "-125000000.00",
      gps: "-4000000.00",
      costo_nueva: "-3000000.00",
      adelanto: "0.00",
      pago_inventario: "0.00",
      fondeo: "0.00",
      int_deuda: "-300000.00",
      egresos: "-132300000.00",
      flujo: "-98300000.00",
      caja: "40000000.00",
      estado: "critico",
    },
    {
      mes: "2026-08",
      motos: 51,
      cartera: 160,
      recaudo_credito: "42000000.00",
      cuotas_iniciales: "5100000.00",
      ingreso_bruto: "47100000.00",
      neto: "45000000.00",
      provision: "-900000.00",
      gastos_fijos: "-125000000.00",
      gps: "-5000000.00",
      costo_nueva: "-3100000.00",
      adelanto: "0.00",
      pago_inventario: "0.00",
      fondeo: "0.00",
      int_deuda: "-300000.00",
      egresos: "-133400000.00",
      flujo: "-88400000.00",
      caja: "200000000.00",
      estado: "ok",
    },
  ],
};

vi.mock("@/lib/proyeccion", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/proyeccion")>();
  return { ...real, obtenerProyeccion: () => Promise.resolve(PROY) };
});

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ProyeccionPage />
    </QueryClientProvider>,
  );
}

describe("ProyeccionPage", () => {
  it("muestra KPIs del motor (piso, capital requerido, meses bajo mínimo)", async () => {
    renderPage();
    expect(await screen.findByText("Piso de caja")).toBeInTheDocument();
    expect(screen.getByText("Capital requerido")).toBeInTheDocument();
    expect(screen.getByText("Meses bajo el mínimo")).toBeInTheDocument();
    // el mes más ajustado se muestra como subtítulo del piso
    expect(screen.getByText("en 2026-09")).toBeInTheDocument();
  });

  it("muestra el ingreso DISCRIMINADO (recaudo crédito vs cuota inicial)", async () => {
    renderPage();
    await screen.findByText("2026-07");
    // las dos vías tienen columnas separadas
    expect(screen.getByText("Recaudo crédito")).toBeInTheDocument();
    expect(screen.getByText("Cuota inicial")).toBeInTheDocument();
    // una fila por mes
    expect(screen.getByText("2026-08")).toBeInTheDocument();
  });

  it("ofrece los tres escenarios", async () => {
    renderPage();
    await screen.findByText("Piso de caja");
    for (const e of ["Pesimista", "Base", "Optimista"]) {
      expect(screen.getByRole("button", { name: e })).toBeInTheDocument();
    }
  });
});
