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

  it("discrimina ingreso y costo en COLUMNAS a la vista (V1.2 B + PTS6-D)", () => {
    renderTabla();
    for (const h of [
      "Cuota inicial",
      "Cuotas semanales",
      "Ajuste mora/default",
      "Alistamiento",
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

  it("PTS6-D: Cuota inicial + Cuotas semanales + Ajuste == Ingreso (con mora)", () => {
    // fila con mora: bruto 189.171.000 (145.640.000 + 43.531.000), neto 180.090.792
    // → ajuste = 180.090.792 − 189.171.000 = −9.080.208 (el caso real de agosto).
    const conMora = mes({
      mes: "2026-08",
      cuotas_iniciales: "145640000.00",
      recaudo_credito: "43531000.00",
      ingreso_bruto: "189171000.00",
      neto: "180090792.00",
      estado: "ok",
    });
    render(
      <TablaEgreso
        filas={[conMora]}
        mesCritico=""
        perforada={false}
        ventanaReconciliada={null}
      />,
    );
    // el ajuste se muestra (negativo) y la fila reconcilia a la vista:
    // 145.640.000 + 43.531.000 + (−9.080.208) = 180.090.792 = Ingreso
    expect(
      screen.getAllByText((t) => t.replace(/\s/g, " ") === "-$ 9.080.208")
        .length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText((t) => t.replace(/\s/g, " ") === "$ 180.090.792")
        .length,
    ).toBeGreaterThan(0);
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
    expect(
      screen.queryByText("Costo de financiar el plazo (interés)"),
    ).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /oct-26/ }));
    expect(
      screen.getByText("Costo de financiar el plazo (interés)"),
    ).toBeInTheDocument();
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

  it("candado: sin ciclo (sin meses anclados) NO pinta marca de origen", () => {
    render(
      <TablaEgreso
        filas={[PROYECTADO, RECONCILIADO]}
        mesCritico="2026-10"
        perforada={true}
        ventanaReconciliada={null}
      />,
    );
    // sin mesesAnclados la tabla queda como hoy: ninguna etiqueta de origen
    expect(screen.queryByText("Proyección")).not.toBeInTheDocument();
    expect(screen.queryByText("Real")).not.toBeInTheDocument();
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

  // ── SUP-5 — la tabla explica la CARTERA (sin columna nueva) ──

  it("muestra las motos colocadas y los créditos activos bajo el mes", () => {
    renderTabla();
    // "cuántas motos vendidas mes a mes" a la vista, sin abrir el desglose
    expect(screen.getAllByText("50 motos · 120 en cartera")).toHaveLength(2);
  });

  it("el desglose abre «Ajuste mora/default» en sus tres variables y cuadran", () => {
    // el caso real de agosto: ajuste = −9.080.208 = mora + recuperación + default
    const conMora = mes({
      mes: "2026-08",
      cuotas_iniciales: "145640000.00",
      recaudo_credito: "43531000.00",
      ingreso_bruto: "189171000.00",
      neto: "180090792.00",
      mora: "-13000000.00",
      recuperacion: "6000000.00",
      default: "-2080208.00",
    });
    render(
      <TablaEgreso
        filas={[conMora]}
        mesCritico=""
        perforada={false}
        ventanaReconciliada={null}
      />,
    );
    expect(screen.queryByText(/Mora · no llega en su mes/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /ago-26/ }));
    expect(screen.getByText(/Mora · no llega en su mes/)).toBeInTheDocument();
    expect(
      screen.getByText(/Recuperación · mora que sí vuelve/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Incumplimiento · pérdida definitiva/),
    ).toBeInTheDocument();
    for (const v of ["-$ 13.000.000", "$ 6.000.000", "-$ 2.080.208"]) {
      expect(
        screen.getAllByText((t) => t.replace(/\s/g, " ") === v).length,
      ).toBeGreaterThan(0);
    }
    // −13.000.000 + 6.000.000 − 2.080.208 = −9.080.208 == el ajuste de la columna
    expect(
      screen.getAllByText((t) => t.replace(/\s/g, " ") === "-$ 9.080.208")
        .length,
    ).toBeGreaterThan(0);
  });

  it("el desglose marca la provisión como P&G, no caja", () => {
    renderTabla();
    fireEvent.click(screen.getByRole("button", { name: /oct-26/ }));
    expect(
      screen.getByText(/Provisión de cartera \(P&G, no caja\)/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Fondo de aval reservado/)).toBeInTheDocument();
  });

  // ── ítems 0 y 4 de Kimi etapa75 ──

  it("ítem 0: el aval entra al bucket Gasto y la fila reconcilia al peso", () => {
    // la costura de etapa73 §10: el motor sumaba el aval al flujo pero esta capa lo
    // omitía — Gasto quedaba corto por exactamente el aval y nada reconciliaba.
    const conAval = mes({
      mes: "2026-11",
      aval: "-546241.68",
      egresos: "-132846241.68",
      flujo: "-98846241.68",
    });
    render(
      <TablaEgreso
        filas={[conAval]}
        mesCritico=""
        perforada={false}
        ventanaReconciliada={null}
      />,
    );
    // Gasto = 125M + 4M + 0,3M + 0,546241.68 = 129.846.242 (sin centavos en tabla)
    expect(
      screen.getAllByText((t) => t.replace(/\s/g, " ") === "$ 129.846.242")
        .length,
    ).toBeGreaterThan(0);
    // y el aval aparece como línea del GRUPO Gasto en el desglose
    fireEvent.click(screen.getByRole("button", { name: /nov-26/ }));
    expect(screen.getByText(/Fondo de aval reservado/)).toBeInTheDocument();
  });

  it("ítem 4: la columna se llama «Caja al cerrar» — la convención, declarada", () => {
    renderTabla();
    expect(
      screen.getByRole("columnheader", { name: "Caja al cerrar" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Caja" })).toBeNull();
  });

  it("ítem 4: el desglose dice con qué INICIA y con qué CIERRA el mes", () => {
    renderTabla();
    fireEvent.click(screen.getByRole("button", { name: /oct-26/ }));
    expect(screen.getByText("Inicia con")).toBeInTheDocument();
    expect(screen.getByText("Cierra en")).toBeInTheDocument();
    // inicia = cierra − flujo = 40M − (−98,3M) = 138,3M (el candado leído al revés)
    expect(
      screen.getAllByText((t) => t.replace(/\s/g, " ") === "$ 138.300.000")
        .length,
    ).toBeGreaterThan(0);
  });
});
