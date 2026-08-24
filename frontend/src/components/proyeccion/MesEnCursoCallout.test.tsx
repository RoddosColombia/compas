// components/proyeccion/MesEnCursoCallout.test.tsx
//
// El mes en curso: comparación presupuesto/ejecutado/resta + completitud (B13) + el
// TERMÓMETRO de desviación (P6 del ciclo mensual): tres lecturas contra el objetivo del
// mes, que NO tocan la proyección.
//
// Dos expectativas cambiaron por decisión del CEO (2026-08-23), no por acomodar código:
//   · la fórmula del mes en curso ya no es la Regla A ("ejecutado + lo que resta del
//     presupuesto") sino el PRESUPUESTO — P4;
//   · el copy de arrastre ahora dice que la gráfica proyecta el OBJETIVO del mes.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MesEnCursoCallout } from "@/components/proyeccion/MesEnCursoCallout";
import type { MesEnCurso } from "@/lib/proyeccion";

/** Sin termómetro: solo lo que existía antes de P6 (candado de compatibilidad). */
const MEC: MesEnCurso = {
  mes: "2026-08",
  cargado_hasta: "2026-08-06",
  dia: 6,
  formula: "el presupuesto aprobado del mes",
  ejecutado: "41000000.00",
  proyectado: "168000000.00",
};

/** Con termómetro: la foto de agosto-2026 (meta 60, 35 colocadas, día 12 de 31). */
const CON_TERMOMETRO: MesEnCurso = {
  ...MEC,
  cargado_hasta: "2026-08-12",
  dia: 12,
  dias_del_mes: 31,
  ejecutado: "150673128.72",
  proyectado: "208000000.00",
  ingreso_real: "99424130.00",
  ingreso_real_inicial: "59480000.00",
  ingreso_real_semanal: "39944130.00",
  ingreso_proyectado: "252783377.70",
  ingreso_proyectado_inicial: "109230000.00",
  ingreso_proyectado_semanal: "161295930.00",
  colocaciones_meta: 60,
  colocaciones_reales: 35,
};

describe("MesEnCursoCallout — B13 + comparación", () => {
  it("muestra la completitud y cómo se arma el mes (P4: el presupuesto)", () => {
    render(<MesEnCursoCallout mesEnCurso={MEC} />);
    expect(screen.getByText(/cargado hasta el 6/i)).toBeInTheDocument();
    expect(
      screen.getByText(/el presupuesto aprobado del mes/i),
    ).toBeInTheDocument();
  });

  it("muestra la comparación presupuesto / ejecutado / resta", () => {
    render(<MesEnCursoCallout mesEnCurso={MEC} />);
    expect(screen.getByText(/presupuesto del mes/i)).toBeInTheDocument();
    expect(screen.getByText(/ejecutado \(al día 6\)/i)).toBeInTheDocument();
    // honestidad R5: la 3ª cifra es lo que RESTA del presupuesto (no una "desviación"
    // engañosa entre el parcial y el mes completo).
    expect(screen.getByText("Resta del presupuesto")).toBeInTheDocument();
  });

  it("dice que la gráfica proyecta el OBJETIVO del mes y qué pasa al cerrarlo", () => {
    render(<MesEnCursoCallout mesEnCurso={MEC} />);
    expect(screen.getByText(/la gráfica proyecta el/i)).toBeInTheDocument();
    expect(screen.getByText(/cuando lo cierres/i)).toBeInTheDocument();
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

describe("MesEnCursoCallout — el termómetro (P6)", () => {
  it("muestra las tres lecturas contra el objetivo del mes", () => {
    render(<MesEnCursoCallout mesEnCurso={CON_TERMOMETRO} />);
    expect(screen.getByText("Motos colocadas")).toBeInTheDocument();
    expect(screen.getByText("Ingreso recaudado")).toBeInTheDocument();
    expect(screen.getByText("Gasto ejecutado")).toBeInTheDocument();
  });

  it("las colocaciones se leen 'llevamos X de la meta'", () => {
    render(<MesEnCursoCallout mesEnCurso={CON_TERMOMETRO} />);
    expect(screen.getByText("35")).toBeInTheDocument();
    expect(screen.getByText(/de 60/)).toBeInTheDocument();
    expect(screen.getByText(/falta 25 para el objetivo/i)).toBeInTheDocument();
  });

  it("dice el día Y los días del mes: un parcial no se lee como desviación", () => {
    render(<MesEnCursoCallout mesEnCurso={CON_TERMOMETRO} />);
    expect(
      screen.getByText(/real al día 12 de 31 · objetivo del mes completo/i),
    ).toBeInTheDocument();
  });

  it("un dato sin cargar dice 'sin cargar', nunca cero", () => {
    render(
      <MesEnCursoCallout
        mesEnCurso={{
          ...CON_TERMOMETRO,
          colocaciones_reales: null,
          ingreso_real: null,
        }}
      />,
    );
    expect(screen.getAllByText("sin cargar").length).toBe(2);
  });

  it("avisa cuando el gasto se pasó del presupuesto", () => {
    render(
      <MesEnCursoCallout
        mesEnCurso={{
          ...CON_TERMOMETRO,
          ejecutado: "230000000.00",
          proyectado: "208000000.00",
        }}
      />,
    );
    expect(
      screen.getByText(/por encima del presupuesto en/i),
    ).toBeInTheDocument();
  });

  it("marca el objetivo cumplido cuando se alcanzó la meta de motos", () => {
    render(
      <MesEnCursoCallout
        mesEnCurso={{ ...CON_TERMOMETRO, colocaciones_reales: 62 }}
      />,
    );
    expect(screen.getByText(/objetivo cumplido/i)).toBeInTheDocument();
  });

  it("sin datos del termómetro cae al bloque de completitud de siempre", () => {
    render(<MesEnCursoCallout mesEnCurso={MEC} />);
    expect(screen.getByText(/completitud del mes/i)).toBeInTheDocument();
    expect(screen.queryByText("Motos colocadas")).toBeNull();
  });
});
