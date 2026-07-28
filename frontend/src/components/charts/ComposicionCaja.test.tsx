// components/charts/ComposicionCaja.test.tsx
//
// V1 §2 — el gráfico compuesto: leyenda con los tres buckets + caja + umbral, y
// hover por mes con el desglose y la porción Auteco (real/proyectado).

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ComposicionCaja } from "@/components/charts/ComposicionCaja";
import type { MesProyeccion } from "@/lib/proyeccion";

function mes(over: Partial<MesProyeccion>): MesProyeccion {
  return {
    mes: "2026-10",
    motos: 50,
    cartera: 120,
    recaudo_credito: "30000000.00",
    cuotas_iniciales: "4000000.00",
    ingreso_bruto: "34000000.00",
    neto: "34000000.00",
    provision: "0.00",
    gastos_fijos: "-125000000.00",
    gps: "-4000000.00",
    costo_nueva: "-3000000.00",
    adelanto: "0.00",
    pago_inventario: "0.00",
    fondeo: "0.00",
    int_deuda: "-300000.00",
    iva: "0.00",
    egresos: "-132300000.00",
    flujo: "-98300000.00",
    caja: "40000000.00",
    estado: "critico",
    ...over,
  };
}

const MESES = [
  mes({ mes: "2026-10" }),
  mes({
    mes: "2027-01",
    pago_inventario: "-180000000.00",
    fondeo: "-5760000.00",
    flujo: "-284060000.00",
    caja: "10000000.00",
  }),
];

function renderChart() {
  return render(
    <ComposicionCaja
      meses={MESES}
      umbral="125000000.00"
      ventanaReconciliada={["2027-01", "2027-01"]}
    />,
  );
}

describe("ComposicionCaja — V1 §2", () => {
  it("muestra la leyenda con los tres buckets, la caja y el umbral", () => {
    renderChart();
    for (const l of [
      "Ingreso",
      "Costo",
      "Gasto",
      "Caja acumulada",
      "Umbral",
      "Ventana con facturas reales",
    ]) {
      expect(screen.getByText(l)).toBeInTheDocument();
    }
  });

  it("hover sobre un mes proyectado: Auteco marcado 'proyectado'", () => {
    const { container } = renderChart();
    const zonas = container.querySelectorAll('rect[fill="transparent"]');
    // 2026-10 no tiene Auteco (paramétrico 0) → no aparece la línea de Auteco
    fireEvent.mouseEnter(zonas[0]);
    expect(screen.getByText("Flujo")).toBeInTheDocument();
    expect(screen.queryByText(/de los cuales Auteco/)).toBeNull();
  });

  it("hover sobre el mes reconciliado: Auteco real con su monto", () => {
    const { container } = renderChart();
    const zonas = container.querySelectorAll('rect[fill="transparent"]');
    fireEvent.mouseEnter(zonas[1]);
    const linea = screen.getByText(/de los cuales Auteco/);
    expect(linea.textContent).toMatch(/real/);
    expect(linea.textContent).not.toMatch(/proyectado/);
  });
});
