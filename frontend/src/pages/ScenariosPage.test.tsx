// Escenarios — F1.1 §3: banda de rango con línea base, conclusión escrita
// desde los datos, y una KpiTileV2 por escenario (tono según piso vs. umbral,
// capital requerido en el contexto). Juicio a horizonte largo (60 m).

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

// Pisos con los tres tonos: pesimista NEGATIVO (critico), base perfora sin ser
// negativo (atencion), optimista sano (positivo).
const PISO: Record<Escenario, string> = {
  pesimista: "-226000000.00",
  base: "64000000.00",
  optimista: "170000000.00",
};

function proy(e: Escenario): Proyeccion {
  return {
    escenario: e,
    caja_minima: "125000000.00",
    fondo_provision: [],
    piso_caja: PISO[e],
    mes_mas_ajustado: "2027-05",
    meses_bajo_minimo: e === "optimista" ? 0 : 2,
    caja_final: "200000000.00",
    capital_requerido: e === "optimista" ? "0.00" : "256000000.00",
    runway_meses: null,
    meses: [m("2026-07", "80000000"), m("2026-08", PISO[e])],
  };
}

const mocks = vi.hoisted(() => ({ obtenerProyeccion: vi.fn() }));

vi.mock("@/lib/proyeccion", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/proyeccion")>();
  return { ...real, obtenerProyeccion: mocks.obtenerProyeccion };
});

function renderPage() {
  mocks.obtenerProyeccion.mockImplementation((p: { escenario?: Escenario }) =>
    Promise.resolve(proy(p.escenario ?? "base")),
  );
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ScenariosPage />
    </QueryClientProvider>,
  );
}

describe("ScenariosPage — F1.1 §3", () => {
  it("escribe la conclusión desde los datos", async () => {
    renderPage();
    expect(
      await screen.findByRole("heading", {
        name: /En el peor caso faltan \$ 256 M; en el mejor, sobra margen/,
      }),
    ).toBeInTheDocument();
  });

  it("consulta el horizonte del juicio (60 m) por escenario", async () => {
    renderPage();
    await screen.findByText("Pesimista · piso de caja");
    for (const esc of ["pesimista", "base", "optimista"]) {
      expect(mocks.obtenerProyeccion).toHaveBeenCalledWith({
        escenario: esc,
        horizonteMeses: 60,
      });
    }
  });

  it("una tarjeta por escenario con el capital requerido en contexto", async () => {
    renderPage();
    expect(
      await screen.findByText("Pesimista · piso de caja"),
    ).toBeInTheDocument();
    expect(screen.getByText("Base · piso de caja")).toBeInTheDocument();
    expect(screen.getByText("Optimista · piso de caja")).toBeInTheDocument();
    expect(screen.getAllByText(/capital requerido: \$ 256 M/).length).toBe(2); // pesimista y base
    expect(screen.getByText(/capital requerido: \$ 0/)).toBeInTheDocument();
  });

  it("el gráfico lleva las etiquetas directas con el piso por escenario", async () => {
    renderPage();
    expect(
      await screen.findByText(/Pesimista · piso -\$ 226 M/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Optimista · piso \$ 170 M/)).toBeInTheDocument();
  });
});
