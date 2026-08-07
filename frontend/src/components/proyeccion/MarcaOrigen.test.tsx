// components/proyeccion/MarcaOrigen.test.tsx
//
// E1·P6 — la marca de ORIGEN (Real · En curso · Presupuesto · Proyección · Revisar
// carga) es una dimensión distinta de la salud de caja (EstadoMes). Un mes sin marca
// del backend es "Proyección".

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MarcaOrigen } from "@/components/proyeccion/MarcaOrigen";

describe("MarcaOrigen", () => {
  it("muestra la etiqueta de cada marca del backend", () => {
    const { rerender } = render(<MarcaOrigen marca="cerrado" />);
    expect(screen.getByText("Real")).toBeInTheDocument();
    rerender(<MarcaOrigen marca="en_ejecucion" />);
    expect(screen.getByText("En curso")).toBeInTheDocument();
    rerender(<MarcaOrigen marca="presupuesto" />);
    expect(screen.getByText("Presupuesto")).toBeInTheDocument();
    rerender(<MarcaOrigen marca="cerrado_sospechoso" />);
    expect(screen.getByText("Revisar carga")).toBeInTheDocument();
  });

  it("un mes sin marca (undefined) es 'Proyección'", () => {
    render(<MarcaOrigen marca={undefined} />);
    expect(screen.getByText("Proyección")).toBeInTheDocument();
  });
});
