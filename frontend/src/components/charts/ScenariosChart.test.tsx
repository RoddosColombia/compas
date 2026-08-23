// ScenariosChart — F1.1 §3: banda de rango (pesimista↔optimista) + línea base,
// umbral etiquetado y etiqueta directa por trazo con el piso del escenario.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  ScenariosChart,
  type SerieEscenario,
} from "@/components/charts/ScenariosChart";
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
    aval: "0",
    mora: "0",
    recuperacion: "0",
    default: "0",
    egresos: "0",
    flujo: "0",
    caja,
    estado: "ok",
  };
}

function serie(
  label: string,
  tono: SerieEscenario["tono"],
  cajas: [string, string],
  piso: string,
): SerieEscenario {
  return {
    label,
    tono,
    meses: [mes("2026-07", cajas[0]), mes("2026-08", cajas[1])],
    piso,
  };
}

describe("ScenariosChart (banda §3)", () => {
  it("dibuja la banda + 3 trazos + umbral etiquetado + etiquetas con el piso", () => {
    const { container } = render(
      <ScenariosChart
        umbral="100000000"
        pesimista={serie(
          "Pesimista",
          "atencion",
          ["90000000", "60000000"],
          "-226000000",
        )}
        base={serie("Base", "cyan", ["120000000", "140000000"], "-63900000")}
        optimista={serie(
          "Optimista",
          "positivo",
          ["150000000", "200000000"],
          "17000000",
        )}
      />,
    );
    expect(container.querySelectorAll("polygon")).toHaveLength(1); // la banda
    expect(container.querySelectorAll("polyline")).toHaveLength(3);
    expect(screen.getByText(/— Mínimo de caja \$ 100 M/)).toBeInTheDocument();
    // las tres cifras que SON la pantalla
    expect(screen.getByText(/Pesimista · piso -\$ 226 M/)).toBeInTheDocument();
    expect(screen.getByText(/Base · piso -\$ 63,9 M/)).toBeInTheDocument();
    expect(screen.getByText(/Optimista · piso \$ 17 M/)).toBeInTheDocument();
  });

  it("no dibuja nada con menos de dos meses", () => {
    const corto = {
      label: "x",
      tono: "cyan" as const,
      meses: [mes("2026-07", "1")],
      piso: "0",
    };
    const { container } = render(
      <ScenariosChart
        umbral="100"
        pesimista={corto}
        base={corto}
        optimista={corto}
      />,
    );
    expect(container.querySelector("svg")).toBeNull();
  });
});
