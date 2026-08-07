// components/proyeccion/TablaEgreso.test.tsx
//
// V1 §3 — la tabla muestra los tres totales por mes, expande el desglose al clic,
// marca el lote Auteco real/proyectado según la ventana reconciliada, y cierra con
// una fila de totales.

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TablaEgreso } from "@/components/proyeccion/TablaEgreso";
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

const PROYECTADO = mes({ mes: "2026-10" });
const RECONCILIADO = mes({
  mes: "2027-01",
  pago_inventario: "-180000000.00",
  fondeo: "-5760000.00",
  flujo: "-284060000.00",
  caja: "10000000.00",
});

function renderTabla() {
  return render(
    <TablaEgreso
      filas={[PROYECTADO, RECONCILIADO]}
      mesCritico="2026-10"
      perforada={true}
      ventanaReconciliada={["2027-01", "2027-01"]}
    />,
  );
}

describe("TablaEgreso — V1 §3", () => {
  it("encabeza con los tres buckets Ingreso · Costo · Gasto", () => {
    renderTabla();
    for (const h of ["Ingreso", "Costo", "Gasto"]) {
      expect(screen.getByRole("columnheader", { name: h })).toBeInTheDocument();
    }
  });

  it("discrimina ingreso y costo en COLUMNAS a la vista (V1.2 B)", () => {
    renderTabla();
    for (const h of [
      "Cuota inicial",
      "Cuotas semanales",
      "Activación",
      "Auteco",
    ]) {
      expect(screen.getByRole("columnheader", { name: h })).toBeInTheDocument();
    }
    // valores a la vista SIN expandir: recaudo semanal 30M y Auteco del reconciliado
    expect(
      screen.getAllByText((t) => t.replace(/\s/g, " ") === "$ 30.000.000")
        .length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText((t) => t.replace(/\s/g, " ") === "$ 185.760.000")
        .length,
    ).toBeGreaterThan(0);
    // "Motos" se quitó por ancho (se priorizan las columnas discriminadas)
    expect(screen.queryByRole("columnheader", { name: "Motos" })).toBeNull();
  });

  it("cierra con una fila de totales (Σ ingreso de la ventana)", () => {
    renderTabla();
    expect(screen.getByText("Totales")).toBeInTheDocument();
    // Σ ingreso = 34M + 34M = 68M
    expect(
      screen.getAllByText((t) => t.replace(/\s/g, " ") === "$ 68.000.000")
        .length,
    ).toBeGreaterThan(0);
  });

  it("expande el desglose: solo lo NO promovido (Auteco lote/fondeo + gasto)", () => {
    renderTabla();
    // ingreso ya está en columnas → NO se repite en el expandible
    expect(screen.queryByText("Fondeo del plazo (interés)")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /oct-26/ }));
    expect(screen.getByText("Fondeo del plazo (interés)")).toBeInTheDocument();
    expect(screen.getByText("Gastos fijos")).toBeInTheDocument();
    // 2026-10 no está en la ventana reconciliada → proyectado
    expect(screen.getByText(/Lote · proyectado/)).toBeInTheDocument();
  });

  it("marca el lote Auteco REAL dentro de la ventana reconciliada", () => {
    renderTabla();
    fireEvent.click(screen.getByRole("button", { name: /ene-27/ }));
    expect(screen.getByText(/Lote · real/)).toBeInTheDocument();
  });

  // E1·P6 — marca de ORIGEN en la 1ª columna (sin columna nueva) + aviso sin_mapear.
  it("muestra la marca de origen de cada mes bajo el nombre", () => {
    render(
      <TablaEgreso
        filas={[PROYECTADO, RECONCILIADO]}
        mesCritico="2026-10"
        perforada={true}
        ventanaReconciliada={["2027-01", "2027-01"]}
        mesesAnclados={{ "2027-01": "cerrado" }}
      />,
    );
    expect(screen.getByText("Real")).toBeInTheDocument(); // 2027-01 = cerrado
    // 2026-10 sin marca → "Proyección"
    expect(screen.getAllByText("Proyección").length).toBeGreaterThan(0);
  });

  it("muestra el aviso de sin_mapear solo si hay rubros", () => {
    const { rerender } = render(
      <TablaEgreso
        filas={[PROYECTADO]}
        mesCritico="2026-10"
        perforada={true}
        ventanaReconciliada={null}
        sinMapear={["Ajuste raro 4040"]}
      />,
    );
    expect(screen.getByText(/sin clasificar/i)).toBeInTheDocument();
    expect(screen.getByText(/Ajuste raro 4040/)).toBeInTheDocument();
    rerender(
      <TablaEgreso
        filas={[PROYECTADO]}
        mesCritico="2026-10"
        perforada={true}
        ventanaReconciliada={null}
        sinMapear={[]}
      />,
    );
    expect(screen.queryByText(/sin clasificar/i)).not.toBeInTheDocument();
  });
});
