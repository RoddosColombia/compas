// Reportes — resumen ejecutivo de la proyección para junta/inversionistas, con
// export a PDF (impresión del navegador). Comportamiento probado: arma el resumen
// desde el escenario base del motor y ofrece descargar el PDF.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { Escenario, MesProyeccion, Proyeccion } from "@/lib/proyeccion";
import ReportesPage from "@/pages/ReportesPage";

function m(mes: string, caja: string): MesProyeccion {
  return {
    mes,
    motos: 0,
    cartera: 0,
    recaudo_credito: "0",
    cuotas_iniciales: "0",
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
    iva: "0",
    egresos: "0",
    flujo: "0",
    caja,
    estado: "ok",
  };
}

const FINAL: Record<Escenario, string> = {
  pesimista: "50000000.00",
  base: "120000000.00",
  optimista: "260000000.00",
};

function proy(e: Escenario): Proyeccion {
  return {
    escenario: e,
    caja_minima: "125000000.00",
    fondo_provision: [],
    piso_caja: "40000000.00",
    mes_mas_ajustado: "2026-09",
    meses_bajo_minimo: e === "optimista" ? 0 : 2,
    caja_final: FINAL[e],
    capital_requerido: e === "optimista" ? "0.00" : "85000000.00",
    runway_meses: null,
    ventana_reconciliada: null,
    interes_obligaciones: {},
    meses: [m("2026-07", "80000000"), m("2026-08", FINAL[e])],
  };
}

vi.mock("@/lib/proyeccion", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/proyeccion")>();
  return {
    ...real,
    obtenerProyeccion: (p: { escenario?: Escenario }) =>
      Promise.resolve(proy(p.escenario ?? "base")),
  };
});

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ReportesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ReportesPage", () => {
  it("arma el resumen ejecutivo desde el motor", async () => {
    renderPage();
    expect(await screen.findByText("Resumen ejecutivo")).toBeInTheDocument();
    // §7: titular de juicio reconciliador + cuarteto estándar de KPIs
    expect(
      screen.getByText(/perfora el mínimo|se mantiene sobre el mínimo/),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Piso de caja").length).toBeGreaterThan(0);
    // "Capital requerido" aparece como KPI y como columna de la tabla comparativa
    expect(screen.getAllByText("Capital requerido").length).toBeGreaterThan(0);
  });

  it("ofrece descargar el PDF", async () => {
    renderPage();
    expect(
      await screen.findByRole("button", { name: /descargar pdf/i }),
    ).toBeInTheDocument();
  });
});
