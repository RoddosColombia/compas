// RF-F4 — TechoVentanaCard: muestra bandera roja cuando perfora atención,
// cifra grande cuando hay holgura, "sin margen" cuando no.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TechoVentanaCard } from "@/components/proyeccion/TechoVentanaCard";
import type { TechoVentanaResultado } from "@/lib/decisiones";

function techo(o: Partial<TechoVentanaResultado> = {}): TechoVentanaResultado {
  return {
    objetivo: "techo_gasto_ventana",
    techo_mensual: "12500000.00",
    valle_limitante_mes: "2027-05",
    piso_resultante: "100000000.00",
    referencia: "100000000.00",
    ventana: 9,
    hay_holgura: true,
    perfora_atencion: false,
    ...o,
  };
}

describe("TechoVentanaCard", () => {
  it("con holgura muestra la cifra y el mes limitante", () => {
    render(<TechoVentanaCard techo={techo()} cargando={false} />);
    expect(screen.getByText(/próximos 9 meses/i)).toBeInTheDocument();
    // formatCOP produce "$ 12.500.000,00"
    expect(screen.getByText(/12\.500\.000/)).toBeInTheDocument();
    expect(screen.queryByText(/perfora el umbral/i)).toBeNull();
  });

  it("perfora atención → bandera roja con el mensaje", () => {
    render(
      <TechoVentanaCard
        techo={techo({ perfora_atencion: true, hay_holgura: false })}
        cargando={false}
      />,
    );
    expect(
      screen.getByText(/perfora el umbral de atención/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Sin margen/i)).toBeNull(); // ese texto no cuando perfora
  });

  it("sin holgura pero sin perforación dice 'Sin margen'", () => {
    render(
      <TechoVentanaCard
        techo={techo({ hay_holgura: false, perfora_atencion: false })}
        cargando={false}
      />,
    );
    expect(screen.getByText(/Sin margen/i)).toBeInTheDocument();
  });

  it("mientras carga y sin datos, pinta cargando", () => {
    const { container } = render(
      <TechoVentanaCard techo={undefined} cargando={true} />,
    );
    // Cargando variante="card" renderiza algo; solo verifico que no crash
    expect(container.firstChild).not.toBeNull();
  });
});
