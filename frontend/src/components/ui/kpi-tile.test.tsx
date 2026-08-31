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

// ── RV-V5: sparkline con overlay de escenario ──────────────────────────────
// Mismo patrón que RV-V4 en la Composición del Flujo y que RV-V2 rebanada 3
// en la curva de caja: cuando hay `sparklineEscenario` se dibuja una segunda
// polyline dashed sobre --color-chart-escenario en el mismo mini-SVG. Punto
// del extremo derecho también en el color del escenario. Escala compartida
// (min/max de las DOS series combinadas) para que ambas sean comparables al ojo.

describe("KpiTileV2 · sparkline overlay de escenario (RV-V5)", () => {
  it("sin `sparklineEscenario` solo hay UNA polyline (backward compat con r2)", () => {
    const { container } = render(
      <KpiTileV2
        label="Piso de caja"
        valor="0"
        contexto="c"
        sparkline={[10, 8, 6, 4]}
      />,
    );
    expect(container.querySelectorAll("polyline")).toHaveLength(1);
  });

  it("con `sparklineEscenario` dibuja DOS polylines en el mismo SVG", () => {
    const { container } = render(
      <KpiTileV2
        label="Piso de caja"
        valor="0"
        contexto="c"
        sparkline={[10, 8, 6, 4]}
        sparklineEscenario={[10, 9, 8, 7]}
      />,
    );
    expect(container.querySelectorAll("polyline")).toHaveLength(2);
  });

  it("la polyline del escenario es dashed y usa --color-chart-escenario", () => {
    const { container } = render(
      <KpiTileV2
        label="Piso de caja"
        valor="0"
        contexto="c"
        sparkline={[10, 8, 6, 4]}
        sparklineEscenario={[10, 9, 8, 7]}
      />,
    );
    const polylines = container.querySelectorAll("polyline");
    // La segunda polyline es el escenario (la primera es el base).
    const escenario = polylines[1];
    expect(escenario.getAttribute("stroke")).toBe(
      "var(--color-chart-escenario)",
    );
    expect(escenario.getAttribute("stroke-dasharray")).toBeTruthy();
  });

  it("el escenario solo se dibuja si la serie base también tiene ≥2 puntos", () => {
    // Sin base no tiene sentido dibujar el overlay (nada contra qué comparar).
    const { container } = render(
      <KpiTileV2
        label="X"
        valor="0"
        contexto="c"
        sparklineEscenario={[10, 9, 8, 7]}
      />,
    );
    expect(container.querySelectorAll("polyline")).toHaveLength(0);
  });

  it("el escenario con <2 puntos no rompe el base (backward silent)", () => {
    const { container } = render(
      <KpiTileV2
        label="X"
        valor="0"
        contexto="c"
        sparkline={[10, 8, 6, 4]}
        sparklineEscenario={[7]}
      />,
    );
    // Solo la del base.
    expect(container.querySelectorAll("polyline")).toHaveLength(1);
  });
});
