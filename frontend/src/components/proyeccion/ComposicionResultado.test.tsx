// components/proyeccion/ComposicionResultado.test.tsx
//
// SUP-5 — la gráfica tiene que explicarse: qué supone esta curva (los porcentajes
// EFECTIVOS del escenario en pantalla) y qué producen esos supuestos en la ventana
// (motos, cartera, mora, recuperación, incumplimiento).

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ComposicionResultado } from "@/components/proyeccion/ComposicionResultado";
import type { MesProyeccion, SupuestosProyeccion } from "@/lib/proyeccion";

function mes(over: Partial<MesProyeccion>): MesProyeccion {
  return {
    mes: "2026-10",
    motos: 77,
    cartera: 214,
    recaudo_credito: "180000000.00",
    cuotas_iniciales: "20000000.00",
    ingreso_bruto: "200000000.00",
    neto: "190000000.00",
    provision: "0.00",
    gastos_fijos: "-208000000.00",
    gps: "-7000000.00",
    costo_nueva: "-53000000.00",
    adelanto: "0.00",
    pago_inventario: "0.00",
    fondeo: "0.00",
    int_deuda: "-2900000.00",
    iva: "0.00",
    aval: "-1800000.00",
    mora: "-10000000.00",
    recuperacion: "5000000.00",
    default: "-5000000.00",
    egresos: "-270900000.00",
    flujo: "-80900000.00",
    caja: "500000000.00",
    estado: "ok",
    ...over,
  };
}

const SUPUESTOS: SupuestosProyeccion = {
  pct_mora: "0.05",
  pct_recuperacion: "0.65",
  pct_default: "0.04", // distinto de la mora a propósito: cada chip su cifra
  pct_provision: "0.02",
  meses_rezago_recuperacion: 1,
  pct_aval_recaudo: "0.01",
  pct_prefondeo_iva: "1",
  motos_base: 70,
  crec_pct_mensual: "0.10",
  crec_pct_mensual_2: null,
  crec_mes_corte: null,
  rampa_unidades: {},
};

describe("ComposicionResultado — SUP-5", () => {
  it("muestra los supuestos EFECTIVOS de la curva en pantalla", () => {
    render(<ComposicionResultado supuestos={SUPUESTOS} meses={[mes({})]} />);
    expect(screen.getByText("5 %")).toBeInTheDocument(); // mora
    expect(screen.getByText("65 %")).toBeInTheDocument(); // recuperación
    expect(screen.getByText("4 %")).toBeInTheDocument(); // incumplimiento
    expect(screen.getByText("70 motos/mes")).toBeInTheDocument();
    expect(screen.getByText(/crece 10 %/)).toBeInTheDocument();
  });

  it("dice CUÁNDO vuelve la mora cuando hay rezago", () => {
    render(<ComposicionResultado supuestos={SUPUESTOS} meses={[mes({})]} />);
    expect(screen.getByText(/1 mes\(es\) después/)).toBeInTheDocument();
  });

  it("declara el segundo tramo de crecimiento cuando existe", () => {
    render(
      <ComposicionResultado
        supuestos={{
          ...SUPUESTOS,
          crec_pct_mensual_2: "0.03",
          crec_mes_corte: 18,
        }}
        meses={[mes({})]}
      />,
    );
    expect(screen.getByText("3 %")).toBeInTheDocument();
    expect(screen.getByText(/desde el mes 19/)).toBeInTheDocument();
  });

  it("suma las motos colocadas y toma la cartera del último mes de la ventana", () => {
    render(
      <ComposicionResultado
        supuestos={SUPUESTOS}
        meses={[
          mes({ mes: "2026-10", motos: 77, cartera: 214 }),
          mes({ mes: "2026-11", motos: 85, cartera: 288 }),
        ]}
      />,
    );
    expect(screen.getByText("162")).toBeInTheDocument(); // 77 + 85
    expect(screen.getByText("288 créditos")).toBeInTheDocument(); // NO 214+288
    expect(
      screen.getByText(/Lo que produce en estos 2 meses/),
    ).toBeInTheDocument();
  });

  it("totaliza mora, recuperación e incumplimiento de la ventana", () => {
    render(
      <ComposicionResultado
        supuestos={SUPUESTOS}
        meses={[mes({ mes: "2026-10" }), mes({ mes: "2026-11" })]}
      />,
    );
    expect(screen.getByText("-$ 20.000.000")).toBeInTheDocument(); // mora ×2
    expect(screen.getByText("$ 10.000.000")).toBeInTheDocument(); // recuperación ×2
    expect(screen.getByText("-$ 10.000.000")).toBeInTheDocument(); // default ×2
  });

  it("cierra explicando cuánto se queda la cartera en el camino", () => {
    // fuga = neto − bruto = −10M por mes; con un mes: 10M
    render(<ComposicionResultado supuestos={SUPUESTOS} meses={[mes({})]} />);
    const cierre = screen.getByText(/la cartera\s+se queda/);
    // Intl mete espacios finos: se normalizan igual que en el resto de la suite.
    const texto = (cierre.textContent ?? "").replace(/\s/g, " ");
    expect(texto).toContain("$ 10.000.000");
    expect(texto).toContain("$ 190.000.000");
  });

  it("no revienta si el backend no manda supuestos (preview)", () => {
    render(<ComposicionResultado supuestos={undefined} meses={[mes({})]} />);
    expect(screen.getByText("Qué compone este resultado")).toBeInTheDocument();
    expect(screen.queryByText(/Lo que esta curva supone/)).toBeNull();
  });

  it("no monta una segunda tabla en la página (tope §10.3 se mide en tbody tr)", () => {
    const { container } = render(
      <ComposicionResultado
        supuestos={SUPUESTOS}
        meses={Array.from({ length: 18 }, (_, i) => mes({ mes: `2026-${i}` }))}
      />,
    );
    expect(container.querySelectorAll("tbody tr")).toHaveLength(0);
  });
});
