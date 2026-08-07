// components/proyeccion/MesEnCursoCallout.test.tsx
//
// E1·P6 — el mes en curso: comparación (proyectado/ejecutado/desviación) + completitud
// (B13, "cargado hasta el día N") con la fórmula en lenguaje de negocio (honestidad R5)
// + copy de efecto-arrastre.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MesEnCursoCallout } from "@/components/proyeccion/MesEnCursoCallout";
import type { MesEnCurso } from "@/lib/proyeccion";

const MEC: MesEnCurso = {
  mes: "2026-08",
  cargado_hasta: "2026-08-06",
  dia: 6,
  formula: "ejecutado + max(0, definido - ejecutado) por concepto",
  ejecutado: "41000000.00",
  proyectado: "168000000.00",
};

describe("MesEnCursoCallout — B13 + comparación", () => {
  it("muestra la completitud y la fórmula en lenguaje de negocio", () => {
    render(<MesEnCursoCallout mesEnCurso={MEC} />);
    expect(screen.getByText(/cargado hasta el 6/i)).toBeInTheDocument();
    expect(
      screen.getByText(/ejecutado \+ lo que resta del presupuesto/i),
    ).toBeInTheDocument();
  });

  it("muestra la comparación presupuesto / ejecutado / resta", () => {
    render(<MesEnCursoCallout mesEnCurso={MEC} />);
    expect(screen.getByText(/presupuesto del mes/i)).toBeInTheDocument();
    expect(screen.getByText(/ejecutado \(al día 6\)/i)).toBeInTheDocument();
    // honestidad R5: la 3ª cifra es lo que RESTA del presupuesto (no una "desviación"
    // engañosa entre el parcial y el mes completo). Label exacto: la fórmula también
    // contiene "resta del presupuesto".
    expect(screen.getByText("Resta del presupuesto")).toBeInTheDocument();
  });

  it("muestra el copy de efecto-arrastre con el mes", () => {
    render(<MesEnCursoCallout mesEnCurso={MEC} />);
    expect(screen.getByText(/cuando cierres agosto/i)).toBeInTheDocument();
  });

  it("sin movimientos aún, lo dice y no rompe", () => {
    render(
      <MesEnCursoCallout
        mesEnCurso={{
          ...MEC,
          cargado_hasta: null,
          dia: null,
          ejecutado: "0.00",
        }}
      />,
    );
    expect(screen.getByText(/aún sin movimientos/i)).toBeInTheDocument();
  });
});
