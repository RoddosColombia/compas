// Pieza 1 (ENTREGA 3) — el techo de gasto en Proyecciones: la respuesta directa a
// "¿cuánto puedo gastar al mes sin perforar el umbral?" (cifra grande + frase de
// lectura). Usa el solver que ya existe (compute-only). Honesto cuando no hay margen:
// dice "Sin margen", NUNCA muestra $0.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TechoGastoCard } from "@/components/proyeccion/TechoGastoCard";
import type { TechoResultado } from "@/lib/decisiones";

function techo(over: Partial<TechoResultado>): TechoResultado {
  return {
    objetivo: "techo_gasto",
    techo_mensual: "5000000.00",
    valle_limitante_mes: "2027-05",
    piso_resultante: "10000000.00",
    meta: "0.00",
    colchon: "0.00",
    hay_holgura: true,
    ...over,
  };
}

describe("TechoGastoCard", () => {
  it("con holgura: cifra grande + frase de lectura con el horizonte y el mes que limita", () => {
    render(
      <TechoGastoCard
        techo={techo({})}
        cargando={false}
        horizonteJuicio={60}
      />,
    );
    expect(
      screen.getByText(/¿Cuánto puedo gastar al mes/i),
    ).toBeInTheDocument();
    // la cifra grande (formatCOP)
    expect(screen.getByText(/\$\s*5\.000\.000/)).toBeInTheDocument();
    // frase de lectura: horizonte + mes que limita
    expect(screen.getByText(/60 meses/)).toBeInTheDocument();
    expect(screen.getByText(/may-27/)).toBeInTheDocument();
  });

  it("sin holgura: lo dice HONESTO, sin mostrar $0", () => {
    render(
      <TechoGastoCard
        techo={techo({ hay_holgura: false, techo_mensual: "0.00" })}
        cargando={false}
        horizonteJuicio={60}
      />,
    );
    expect(screen.getByText(/Sin margen/i)).toBeInTheDocument();
    expect(screen.queryByText(/\$\s*0\b/)).toBeNull();
  });

  it("sin dato y sin cargar: no renderiza nada", () => {
    const { container } = render(
      <TechoGastoCard
        techo={undefined}
        cargando={false}
        horizonteJuicio={60}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
