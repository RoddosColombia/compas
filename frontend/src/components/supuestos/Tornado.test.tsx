// Tornado (C3 §6.7): orden por |impacto| en pesos desc y frase de conclusión.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Tornado, ordenarTornado } from "@/components/supuestos/Tornado";
import type { Sensibilidad } from "@/lib/parametros";

const DATA: Sensibilidad = {
  escenario: "base",
  horizonte_meses: 60,
  piso_base: "77800000.00",
  variables: [
    {
      variable: "pct_mora",
      etiqueta: "% de mora",
      variacion: "±1 punto",
      piso_base: "77800000.00",
      piso_mas: "72800000.00", // −5 M
      piso_menos: "82800000.00", // +5 M
    },
    {
      variable: "gastos_fijos",
      etiqueta: "Gastos fijos",
      variacion: "±10 %",
      piso_base: "77800000.00",
      piso_mas: "23800000.00", // −54 M ← el más grande
      piso_menos: "131800000.00",
    },
    {
      variable: "cuota_semanal",
      etiqueta: "Cuota semanal",
      variacion: "±5 %",
      piso_base: "77800000.00",
      piso_mas: "97800000.00", // +20 M
      piso_menos: "57800000.00",
    },
  ],
};

describe("ordenarTornado", () => {
  it("ordena por |impacto| en pesos descendente", () => {
    const filas = ordenarTornado(DATA);
    expect(filas.map((f) => f.etiqueta)).toEqual([
      "Gastos fijos",
      "Cuota semanal",
      "% de mora",
    ]);
    expect(filas[0].magnitud.toString()).toBe("54000000");
  });
});

describe("Tornado (render)", () => {
  it("la frase de conclusión nombra las dos variables que más pesan", () => {
    render(<Tornado data={DATA} />);
    expect(screen.getByText("¿Qué mueve mi umbral?")).toBeInTheDocument();
    expect(
      screen.getByText(/depende sobre todo de gastos fijos y de cuota semanal/),
    ).toBeInTheDocument();
  });

  it("cada barra lleva su variación y su delta en pesos", () => {
    render(<Tornado data={DATA} />);
    const items = screen.getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Gastos fijos");
    expect(items[0]).toHaveTextContent("±10 %");
    expect(items[0].textContent?.replace(/\s/g, " ")).toContain("$ 54 M");
    // la barra más grande ocupa el 100 %
    expect(screen.getByTestId("barra-Gastos fijos")).toHaveStyle({
      width: "100%",
    });
  });
});
