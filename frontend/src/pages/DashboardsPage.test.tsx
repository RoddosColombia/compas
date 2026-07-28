// Dashboards — panel operativo. Muestra las series del motor (cobranza, cartera,
// ingreso), la colocación y cartera por añada (DASH-01) y la mora por tramo derivada
// del LoanTape real de SISMO-V3 (aging).

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
    iva: "0",
    egresos: "0",
    flujo: "0",
    caja: "0",
    estado: "ok",
  };
}

const PROY: Proyeccion = {
  escenario: "base",
  caja_minima: "125000000.00",
  fondo_provision: [],
  piso_caja: "40000000.00",
  mes_mas_ajustado: "2026-09",
  meses_bajo_minimo: 0,
  caja_final: "200000000.00",
  capital_requerido: "0.00",
  runway_meses: null,
  ventana_reconciliada: null,
  interes_obligaciones: {},
  meses: [
    m("2026-07", 120, "30000000.00", "5000000.00"),
    m("2026-08", 160, "42000000.00", "5100000.00"),
  ],
};

const OPER = {
  escenario: "base",
  meses: [
    {
      mes: "2026-07",
      colocacion: 50,
      cartera: 120,
      por_anada: [{ anada: "2026-07", activos: 120 }],
    },
    {
      mes: "2026-08",
      colocacion: 51,
      cartera: 160,
      por_anada: [
        { anada: "previa", activos: 40 },
        { anada: "2026-07", activos: 60 },
        { anada: "2026-08", activos: 60 },
      ],
    },
  ],
};

const AGING = {
  fecha_corte: "2026-07-22",
  tramos: [
    {
      tramo: "al_dia",
      etiqueta: "Al día",
      n_creditos: 80,
      saldo_en_mora: "0.00",
    },
    {
      tramo: "1_30",
      etiqueta: "1-30 días",
      n_creditos: 10,
      saldo_en_mora: "1500000.00",
    },
    {
      tramo: "31_60",
      etiqueta: "31-60 días",
      n_creditos: 5,
      saldo_en_mora: "900000.00",
    },
    {
      tramo: "61_90",
      etiqueta: "61-90 días",
      n_creditos: 2,
      saldo_en_mora: "400000.00",
    },
    {
      tramo: "90_mas",
      etiqueta: "90+ días",
      n_creditos: 3,
      saldo_en_mora: "1200000.00",
    },
  ],
};

vi.mock("@/lib/proyeccion", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/proyeccion")>();
  return {
    ...real,
    obtenerProyeccion: () => Promise.resolve(PROY),
    obtenerOperacion: () => Promise.resolve(OPER),
  };
});

vi.mock("@/lib/loantape", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/loantape")>();
  return { ...real, obtenerAging: () => Promise.resolve(AGING) };
});

vi.mock("@/auth/AuthContext", () => ({
  useAuth: () => ({ puede: () => false }),
}));

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

  it("la conclusión de cobranza dice 'pasa de X a Y' (no un multiplicador con punto)", async () => {
    renderPage();
    // QA F1.1 arrastre: nada de "×104.6"; formato es-CO, honesto de punta a punta.
    const concl = await screen.findByRole("heading", {
      name: /La cobranza proyectada pasa de .* a .*\/mes en 2 meses/,
    });
    expect(concl).toBeInTheDocument();
    expect(concl.textContent).not.toMatch(/multiplica|×|\d\.\d/);
  });

  it("muestra colocación y cartera por añada con conclusión calculada (DASH-01/§4)", async () => {
    renderPage();
    // los títulos ahora son CONCLUSIONES escritas desde los datos
    expect(
      await screen.findByRole("heading", { name: /La colocación pasa de/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /por cohorte de colocación/ }),
    ).toBeInTheDocument();
    // pie honesto: el desglose espejo de la colocación hasta el run-off
    expect(
      screen.getByText(/igualará a la colocación hasta ~dic-2027/),
    ).toBeInTheDocument();
    // el último mes desglosa la añada 'previa' (créditos preexistentes)
    expect(screen.getAllByText("previa").length).toBeGreaterThan(0);
  });

  it("muestra la mora por tramo del LoanTape real (aging)", async () => {
    renderPage();
    expect(
      await screen.findByRole("heading", { name: "Mora por tramo" }),
    ).toBeInTheDocument();
    // los tramos del aging aparecen con su etiqueta y monto
    expect(await screen.findByText("90+ días")).toBeInTheDocument();
    // sin centavos en las barras (política F1 §3)
    expect(screen.queryByText(/1\.200\.000,00/)).toBeNull();
    expect(
      screen.getAllByText((t) => t.replace(/\s/g, " ") === "$ 1.200.000")
        .length,
    ).toBeGreaterThan(0);
    expect(screen.getByText(/corte 2026-07-22/)).toBeInTheDocument();
  });
});
