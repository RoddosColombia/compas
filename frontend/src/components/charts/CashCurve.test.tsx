// CashCurve: curva de caja vs umbral (SVG). Comportamiento probado: dibuja un
// marcador de perforación por cada mes cuya caja queda por DEBAJO del umbral.

import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CashCurve } from "@/components/charts/CashCurve";
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

describe("CashCurve", () => {
  it("marca solo los meses bajo el umbral (perforación)", () => {
    const meses = [
      mes("2026-07", "200"), // por encima
      mes("2026-08", "50"), // debajo
      mes("2026-09", "30"), // debajo
      mes("2026-10", "150"), // por encima
    ];
    const { container } = render(<CashCurve meses={meses} umbral="100" />);
    expect(container.querySelectorAll("circle")).toHaveLength(2);
  });

  it("no dibuja nada con menos de dos meses", () => {
    const { container } = render(
      <CashCurve meses={[mes("2026-07", "100")]} umbral="100" />,
    );
    expect(container.querySelector("svg")).toBeNull();
  });

  // F1.1 §0.4 — rojo = crítico: la anotación del mínimo SOLO va en critico si
  // perfora el umbral; con la caja sana va en neutro (hallazgo QA visual prod).
  it("anotada: mínimo SANO (sobre el umbral) va en neutro, no en rojo", () => {
    const meses = [
      mes("2026-07", "600000000"),
      mes("2026-08", "536700000"), // el mínimo, MUY por encima del umbral
      mes("2026-09", "700000000"),
    ];
    const { container, getByText } = render(
      <CashCurve meses={meses} umbral="30000000" anotada hoyMes="2026-07" />,
    );
    const anotacion = getByText(/ago-26 ·/);
    expect(anotacion.getAttribute("class")).toContain("fill-ink");
    expect(anotacion.getAttribute("class")).not.toContain("fill-critico");
    // sin perforación no hay marcadores rojos de meses bajo el umbral
    for (const c of container.querySelectorAll("circle")) {
      if (c.getAttribute("r") === "4.5") {
        expect(c.getAttribute("class")).toContain("fill-ink");
      }
    }
  });

  it("anotada: mínimo que PERFORA el umbral sí va en critico", () => {
    const meses = [
      mes("2026-07", "100000000"),
      mes("2026-08", "-63900000"), // perfora
      mes("2026-09", "80000000"),
    ];
    const { getByText } = render(
      <CashCurve meses={meses} umbral="30000000" anotada hoyMes="2026-07" />,
    );
    expect(getByText(/ago-26 ·/).getAttribute("class")).toContain(
      "fill-critico",
    );
  });
});
