// KpiTile: baldosa de KPI del cockpit. Etiqueta (Raleway) + cifra (Montserrat,
// tabular-nums) + delta opcional con signo coloreado (verde sube / rojo baja).
// El color del delta ES comportamiento → se prueba.

import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { KpiTileV2 } from "@/components/ui/kpi-tile";

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

// ── RV-V3 rebanada 2: sparkline (mini-gráfica de tendencia) ──────────────────
// Contrato: la baldosa acepta una serie opcional (números crudos, sin formato)
// y la dibuja como polyline SVG inline sobre --color-chart-real (RV-V1 token).
// Sin serie → sin SVG (backward compat con los 18 usos existentes).

describe("KpiTileV2 · sparkline (RV-V3 rebanada 2)", () => {
  it("con `sparkline` renderiza un SVG polyline con un punto por valor", () => {
    const { container } = render(
      <KpiTileV2
        label="Piso de caja"
        valor="100000000"
        contexto="en may-27"
        sparkline={[80, 90, 85, 100, 95, 110]}
      />,
    );
    const svg = container.querySelector("svg[aria-label]");
    expect(svg).toBeInTheDocument();
    const line = svg?.querySelector("polyline");
    expect(line).toBeInTheDocument();
    const pts = line?.getAttribute("points")?.trim().split(/\s+/) ?? [];
    expect(pts).toHaveLength(6);
  });

  it("sin `sparkline` no renderiza SVG (backward compat con los 18 usos)", () => {
    const { container } = render(
      <KpiTileV2
        label="Piso de caja"
        valor="100000000"
        contexto="en may-27"
      />,
    );
    expect(container.querySelector("svg[aria-label]")).not.toBeInTheDocument();
  });

  it("el aria-label refleja la tendencia (sube/baja/estable) del primero al último punto", () => {
    const { container, rerender } = render(
      <KpiTileV2
        label="X"
        valor="0"
        contexto="c"
        sparkline={[10, 20, 30]}
      />,
    );
    expect(container.querySelector("svg")?.getAttribute("aria-label")).toMatch(
      /sube|subiendo/i,
    );

    rerender(
      <KpiTileV2
        label="X"
        valor="0"
        contexto="c"
        sparkline={[30, 20, 10]}
      />,
    );
    expect(container.querySelector("svg")?.getAttribute("aria-label")).toMatch(
      /baja|bajando/i,
    );

    rerender(
      <KpiTileV2
        label="X"
        valor="0"
        contexto="c"
        sparkline={[10, 10, 10]}
      />,
    );
    expect(container.querySelector("svg")?.getAttribute("aria-label")).toMatch(
      /estable|plano/i,
    );
  });

  it("con menos de 2 puntos no renderiza el sparkline (no hay tendencia posible)", () => {
    const { container: c1 } = render(
      <KpiTileV2 label="X" valor="0" contexto="c" sparkline={[42]} />,
    );
    expect(c1.querySelector("svg[aria-label]")).not.toBeInTheDocument();

    const { container: c0 } = render(
      <KpiTileV2 label="X" valor="0" contexto="c" sparkline={[]} />,
    );
    expect(c0.querySelector("svg[aria-label]")).not.toBeInTheDocument();
  });

  it("los tokens del stroke vienen del contrato RV-V1 (no hardcodea hex)", () => {
    const { container } = render(
      <KpiTileV2
        label="X"
        valor="0"
        contexto="c"
        sparkline={[1, 2, 3, 4]}
      />,
    );
    const line = container.querySelector("polyline");
    // Regla RV-V1: el color viene de la variable --color-chart-real, cero hex.
    expect(line?.getAttribute("stroke")).toBe("var(--color-chart-real)");
  });
});
