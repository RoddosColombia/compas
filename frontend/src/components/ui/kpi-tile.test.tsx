// KpiTile: baldosa de KPI del cockpit. Etiqueta (Raleway) + cifra (Montserrat,
// tabular-nums) + delta opcional con signo coloreado (verde sube / rojo baja).
// El color del delta ES comportamiento → se prueba.

import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { KpiTile, KpiTileV2 } from "@/components/ui/kpi-tile";

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

// ── F1: KpiTile v2 — cifra → juicio → acción ────────────────────────────────

describe("KpiTileV2 (sistema F1)", () => {
  it("abrevia la cifra y conserva el valor exacto en title (auditabilidad)", () => {
    render(
      <KpiTileV2
        label="Piso de caja"
        valor="-63897875.14"
        contexto="en may-27"
      />,
    );
    const cifra = screen.getByText("-$ 63,9 M");
    expect(cifra).toBeInTheDocument();
    // hover = valor exacto con centavos (formatCOP)
    expect(cifra.getAttribute("title")?.replace(/\s/g, " ")).toContain(
      "63.897.875,14",
    );
    expect(screen.getByText("en may-27")).toBeInTheDocument();
  });

  it("la comparación muestra delta + contra qué", () => {
    render(
      <KpiTileV2
        label="Piso de caja"
        valor="-63897875.14"
        comparacion={{
          delta: { texto: "▼ -$ 93,9 M", direccion: "baja", tono: "critico" },
          contra: "vs. el umbral",
        }}
      />,
    );
    expect(screen.getByText("▼ -$ 93,9 M")).toBeInTheDocument();
    expect(screen.getByText(/vs\. el umbral/)).toBeInTheDocument();
  });

  it("el tono lleva SÍMBOLO además de color (nunca color solo)", () => {
    render(
      <KpiTileV2
        label="Capital requerido"
        valor="93900000"
        contexto="para sostener el umbral"
        tono="critico"
      />,
    );
    expect(screen.getByText("✗")).toHaveClass("text-critico");
    expect(screen.getByText("$ 93,9 M")).toHaveClass("text-critico");
  });

  it("con `to` la baldosa entera es un enlace al detalle", () => {
    render(
      <MemoryRouter>
        <KpiTileV2
          label="Caja hoy"
          valor="704700000"
          contexto="conciliada hoy ✓"
          to="/mes"
        />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link")).toHaveAttribute("href", "/mes");
  });

  it("valorTexto presenta cifras no monetarias sin abreviar", () => {
    render(
      <KpiTileV2
        label="Meses bajo el mínimo"
        valor="0"
        valorTexto="1 de 18"
        contexto="único: may-27"
      />,
    );
    expect(screen.getByText("1 de 18")).toBeInTheDocument();
  });
});
