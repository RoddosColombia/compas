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
    aval: "0.00",
    mora: "0.00",
    recuperacion: "0.00",
    default: "0.00",
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
      "Mínimo de caja",
      "Meses con facturas ya registradas",
    ]) {
      expect(screen.getByText(l)).toBeInTheDocument();
    }
  });

  it("anota el mes de menor caja, el próximo Auteco y la perforación (V1.2 A4)", () => {
    renderChart();
    // menor caja: 2027-01 tiene 10M (< 40M de 2026-10)
    expect(screen.getByText(/menor caja/)).toBeInTheDocument();
    // próximo compromiso Auteco: 2027-01 (lote+fondeo 185,76M)
    expect(screen.getByText(/Compromiso Auteco/)).toBeInTheDocument();
    // ambos meses caen bajo el umbral (125M) → hay perforación anotada
    expect(screen.getByText(/baja del mínimo de caja/)).toBeInTheDocument();
  });

  it("hover: ingreso discriminado (recaudo semanal vs cuota inicial) — ítem 1", () => {
    const { container } = renderChart();
    const zonas = container.querySelectorAll('rect[fill="transparent"]');
    fireEvent.mouseEnter(zonas[0]);
    expect(screen.getByText("Recaudo semanal")).toBeInTheDocument();
    expect(screen.getByText("Cuota inicial")).toBeInTheDocument();
  });

  it("hover sobre un mes proyectado: sin Auteco (paramétrico 0)", () => {
    const { container } = renderChart();
    const zonas = container.querySelectorAll('rect[fill="transparent"]');
    // 2026-10 no tiene Auteco → no aparece su línea; sí la de moto nueva (costo)
    fireEvent.mouseEnter(zonas[0]);
    expect(screen.getByText("Flujo")).toBeInTheDocument();
    // el hover NO trae la sub-línea "Auteco · …" (la anotación del gráfico sí dice
    // "Compromiso Auteco", por eso se filtra por el separador del desglose)
    expect(screen.queryByText(/Auteco ·/)).toBeNull();
    expect(screen.getByText("Moto nueva")).toBeInTheDocument();
  });

  it("hover sobre el mes reconciliado: costo discriminado, Auteco real — ítem 2", () => {
    const { container } = renderChart();
    const zonas = container.querySelectorAll('rect[fill="transparent"]');
    fireEvent.mouseEnter(zonas[1]);
    const linea = screen.getByText(/Auteco ·/);
    expect(linea.textContent).toMatch(/real/);
    expect(linea.textContent).not.toMatch(/proyectado/);
    expect(screen.getByText("Moto nueva")).toBeInTheDocument();
  });

  // E1·P6 — la línea de caja se parte: sólida (real/en curso) → punteada (proyección).
  it("sin anclaje dibuja una sola línea de caja (candado, como hoy)", () => {
    const { container } = renderChart();
    expect(container.querySelectorAll("polyline[data-caja]").length).toBe(1);
  });

  it("con meses anclados parte la línea en sólida + punteada", () => {
    const { container } = render(
      <ComposicionCaja
        meses={MESES}
        umbral="125000000.00"
        ventanaReconciliada={null}
        mesesAnclados={{ "2026-10": "cerrado" }}
      />,
    );
    // sólida (anclado hasta 2026-10) + punteada (2027-01 proyección) = 2 tramos
    expect(container.querySelectorAll("polyline[data-caja]").length).toBe(2);
  });

  it("marca con un punto de alerta el mes cerrado_sospechoso", () => {
    const { container } = render(
      <ComposicionCaja
        meses={MESES}
        umbral="125000000.00"
        ventanaReconciliada={null}
        mesesAnclados={{ "2026-10": "cerrado_sospechoso" }}
      />,
    );
    expect(container.querySelector("circle[data-sospechoso]")).not.toBeNull();
  });
});
