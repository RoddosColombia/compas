// KpiTile: baldosa de KPI del cockpit. Etiqueta (Raleway) + cifra (Montserrat,
// tabular-nums) + delta opcional con signo coloreado (verde sube / rojo baja).
// El color del delta ES comportamiento → se prueba.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { KpiTile } from "@/components/ui/kpi-tile";

describe("KpiTile", () => {
  it("muestra etiqueta, cifra y subtítulo", () => {
    render(
      <KpiTile label="Piso de caja" value="$40.000.000" sub="en 2026-09" />,
    );
    expect(screen.getByText("Piso de caja")).toBeInTheDocument();
    expect(screen.getByText("$40.000.000")).toBeInTheDocument();
    expect(screen.getByText("en 2026-09")).toBeInTheDocument();
  });

  it("colorea el delta positivo en verde y el negativo en rojo", () => {
    const { rerender } = render(
      <KpiTile
        label="Caja"
        value="$1"
        delta={{ texto: "+12%", tono: "sube" }}
      />,
    );
    expect(screen.getByText("+12%")).toHaveClass("text-green");
    rerender(
      <KpiTile
        label="Caja"
        value="$1"
        delta={{ texto: "-8%", tono: "baja" }}
      />,
    );
    expect(screen.getByText("-8%")).toHaveClass("text-red");
  });

  it("pinta la cifra en rojo cuando tono=peligro (perforación)", () => {
    render(<KpiTile label="Caja" value="-$5" tono="peligro" />);
    expect(screen.getByText("-$5")).toHaveClass("text-red");
  });
});
