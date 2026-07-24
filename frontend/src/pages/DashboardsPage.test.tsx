// Dashboards — panel operativo. Muestra las series que el motor YA proyecta
// (cobranza, cartera activa, cuotas iniciales, ingreso bruto) y avisa honestamente
// que cartera por añada / mora por tramo / colocación requieren backend adicional.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { MesProyeccion, Proyeccion } from "@/lib/proyeccion";
import DashboardsPage from "@/pages/DashboardsPage";

function m(
  mes: string,
  cartera: number,
  recaudo: string,
  iniciales: string,
): MesProyeccion {
  return {
    mes,
    motos: 0,
    cartera,
    recaudo_credito: recaudo,
    cuotas_iniciales: iniciales,
    ingreso_bruto: "0",
    neto: "0",
    provision: "0",
    gastos_fijos: "0",
    gps: "0",
    costo_nueva: "0",
    adelanto: "0",
    pago_inventario: "0",
    fondeo: "0",
    int_deuda: "0",
    egresos: "0",
    flujo: "0",
    caja: "0",
    estado: "ok",
  };
}

const PROY: Proyeccion = {
  escenario: "base",
  caja_minima: "125000000.00",
  piso_caja: "40000000.00",
  mes_mas_ajustado: "2026-09",
  meses_bajo_minimo: 0,
  caja_final: "200000000.00",
  capital_requerido: "0.00",
  runway_meses: null,
  meses: [
    m("2026-07", 120, "30000000.00", "5000000.00"),
    m("2026-08", 160, "42000000.00", "5100000.00"),
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
      <DashboardsPage />
    </QueryClientProvider>,
  );
}

describe("DashboardsPage", () => {
  it("muestra las series operativas que el motor ya proyecta", async () => {
    renderPage();
    expect(await screen.findByText("Cobranza proyectada")).toBeInTheDocument();
    expect(screen.getByText("Cartera activa al cierre")).toBeInTheDocument();
  });

  it("avisa honestamente qué análisis requieren backend adicional", async () => {
    renderPage();
    await screen.findByText("Cobranza proyectada");
    expect(screen.getByText(/por añada/i)).toBeInTheDocument();
    expect(screen.getByText(/por tramo/i)).toBeInTheDocument();
  });
});
