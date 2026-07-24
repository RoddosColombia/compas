// Inicio — pulso ejecutivo. Consume el escenario base del motor y resume el
// estado de la caja: KPIs, aviso de perforación y acceso a la proyección completa.
// El backend calcula todo; el front solo presenta.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { Proyeccion } from "@/lib/proyeccion";
import InicioPage from "@/pages/InicioPage";

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
      <MemoryRouter>
        <InicioPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("InicioPage", () => {
  it("resume el pulso con KPIs del motor", async () => {
    renderPage();
    expect(await screen.findByText("Piso de caja")).toBeInTheDocument();
    expect(screen.getByText("Capital requerido")).toBeInTheDocument();
    expect(screen.getByText("Runway")).toBeInTheDocument();
  });

  it("avisa la perforación de caja (rojo de sistema)", async () => {
    renderPage();
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("enlaza a la proyección completa", async () => {
    renderPage();
    const link = await screen.findByRole("link", {
      name: /proyección completa/i,
    });
    expect(link).toHaveAttribute("href", "/proyeccion");
  });
});
