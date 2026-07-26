// Escenarios — compara pesimista/base/optimista superpuestos. Consume el motor
// una vez por escenario. Comportamiento probado: muestra las tres tarjetas
// comparativas con sus métricas.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Escenario, MesProyeccion, Proyeccion } from "@/lib/proyeccion";
import ScenariosPage from "@/pages/ScenariosPage";

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

// Caja final creciente pesimista < base < optimista.
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
      <ScenariosPage />
    </QueryClientProvider>,
  );
}

describe("ScenariosPage", () => {
  it("muestra las tres tarjetas comparativas", async () => {
    renderPage();
    // los títulos de tarjeta son encabezados (la leyenda son spans)
    expect(
      await screen.findByRole("heading", { name: "Pesimista" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Base" })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Optimista" }),
    ).toBeInTheDocument();
  });

  it("compara caja final por escenario", async () => {
    renderPage();
    await screen.findByRole("heading", { name: "Pesimista" });
    // la caja final del optimista aparece formateada
    expect(screen.getByText(/260\.000\.000/)).toBeInTheDocument();
    // hay una métrica de capital requerido por tarjeta (3)
    expect(screen.getAllByText("Capital requerido")).toHaveLength(3);
  });
});
