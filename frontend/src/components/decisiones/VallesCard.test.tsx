// RF-F3 · P2 — VallesCard muestra el segmento (entrada/salida/duración) cuando el
// backend lo trae, y lo omite (fallback) cuando viene en null (sin umbral configurado).

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { VallesCard } from "@/components/decisiones/VallesCard";
import type { Valle } from "@/lib/decisiones";

const CAUSA_VACIA: Valle["causas"] = [];

function valle(overrides: Partial<Valle> = {}): Valle {
  return {
    mes: "2027-05",
    caja: "50000000.00",
    distancia_al_umbral: "20000000.00",
    meses_para_prepararse: 3,
    causas: CAUSA_VACIA,
    ...overrides,
  };
}

describe("VallesCard", () => {
  it("sin segmento (umbral no configurado), no muestra la línea ámbar", () => {
    render(<VallesCard valles={[valle()]} cargando={false} />);
    // solo el fondo
    expect(screen.queryByText(/Bajo atención de/)).toBeNull();
  });

  it("con segmento (entrada/salida/duración), muestra el rango con «Bajo atención de … a … · N meses»", () => {
    render(
      <VallesCard
        valles={[
          valle({
            entrada: "2027-03",
            salida: "2027-06",
            duracion: 3,
          }),
        ]}
        cargando={false}
      />,
    );
    // formatMesCorto usa abreviaturas es-CO tipo "mar 27"
    const linea = screen.getByText(/Bajo atención de/);
    expect(linea).toBeInTheDocument();
    expect(linea.textContent).toMatch(/3 meses/);
  });

  it("con segmento abierto (salida null), lo dice explícito", () => {
    render(
      <VallesCard
        valles={[
          valle({
            entrada: "2027-03",
            salida: null,
            duracion: 4,
          }),
        ]}
        cargando={false}
      />,
    );
    expect(screen.getByText(/aún no sale/)).toBeInTheDocument();
  });

  // RF-F3 · P3b — chips de cambio vs. última versión aprobada.

  it("marca «nuevo» cuando el mes está en mesesNuevos", () => {
    render(
      <VallesCard
        valles={[valle({ mes: "2027-05" })]}
        cargando={false}
        mesesNuevos={new Set(["2027-05"])}
      />,
    );
    expect(screen.getByText("nuevo")).toBeInTheDocument();
    expect(screen.queryByText("más profundo")).toBeNull();
  });

  it("marca «más profundo» cuando el mes está en mesesMasProfundos", () => {
    render(
      <VallesCard
        valles={[valle({ mes: "2027-05" })]}
        cargando={false}
        mesesMasProfundos={new Set(["2027-05"])}
      />,
    );
    expect(screen.getByText("más profundo")).toBeInTheDocument();
    expect(screen.queryByText("nuevo")).toBeNull();
  });

  it("si por bug llegan las dos, gana «nuevo» (disjuntos por diseño en backend)", () => {
    render(
      <VallesCard
        valles={[valle({ mes: "2027-05" })]}
        cargando={false}
        mesesNuevos={new Set(["2027-05"])}
        mesesMasProfundos={new Set(["2027-05"])}
      />,
    );
    expect(screen.getByText("nuevo")).toBeInTheDocument();
    expect(screen.queryByText("más profundo")).toBeNull();
  });

  it("sin sets, no pinta ningún chip (compat)", () => {
    render(<VallesCard valles={[valle()]} cargando={false} />);
    expect(screen.queryByText("nuevo")).toBeNull();
    expect(screen.queryByText("más profundo")).toBeNull();
  });
});
