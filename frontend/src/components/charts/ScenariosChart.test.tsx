// ScenariosChart: superpone las curvas de caja de varios escenarios contra el
// umbral. Comportamiento probado: dibuja una polilínea por serie (con ≥2 meses) y
// nada si no hay series suficientes.

import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ScenariosChart } from "@/components/charts/ScenariosChart";
import type { MesProyeccion } from "@/lib/proyeccion";

function mes(m: string, caja: string): MesProyeccion {
  return {
    mes: m,
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

const serie = (caja1: string, caja2: string) => [
  mes("2026-07", caja1),
  mes("2026-08", caja2),
];

describe("ScenariosChart", () => {
  it("dibuja una polilínea por escenario", () => {
    const { container } = render(
      <ScenariosChart
        umbral="100"
        series={[
          { escenario: "pesimista", color: "amber", meses: serie("90", "60") },
          { escenario: "base", color: "cyan", meses: serie("120", "140") },
          {
            escenario: "optimista",
            color: "green",
            meses: serie("150", "200"),
          },
        ]}
      />,
    );
    expect(container.querySelectorAll("polyline")).toHaveLength(3);
  });

  it("no dibuja nada sin series con suficientes meses", () => {
    const { container } = render(<ScenariosChart umbral="100" series={[]} />);
    expect(container.querySelector("svg")).toBeNull();
  });
});
