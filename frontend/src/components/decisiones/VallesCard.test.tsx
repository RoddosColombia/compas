// RF-F3 · P2 — VallesCard muestra el segmento (entrada/salida/duración) cuando el
// backend lo trae, y lo omite (fallback) cuando viene en null (sin umbral configurado).

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { VallesCard } from "@/components/decisiones/VallesCard";
import type { Valle } from "@/lib/decisiones";

const CAUSA_VACIA: Valle["causas"] = [];

function valle(overrides: Partial<Valle> = {}): Valle {
  return {
    mes: "2027-05",
    caja: "50000000.00",
    distancia_al_umbral: "20000000.00",
    meses_para_prepararse: 3,
    causas: CAUSA_VACIA,
    ...overrides,
  };
}

describe("VallesCard", () => {
  it("sin segmento (umbral no configurado), no muestra la línea ámbar", () => {
    render(<VallesCard valles={[valle()]} cargando={false} />);
    // solo el fondo
    expect(screen.queryByText(/Bajo atención de/)).toBeNull();
  });

  it("con segmento (entrada/salida/duración), muestra el rango con «Bajo atención de … a … · N meses»", () => {
    render(
      <VallesCard
        valles={[
          valle({
            entrada: "2027-03",
            salida: "2027-06",
            duracion: 3,
          }),
        ]}
        cargando={false}
      />,
    );
    // formatMesCorto usa abreviaturas es-CO tipo "mar 27"
    const linea = screen.getByText(/Bajo atención de/);
    expect(linea).toBeInTheDocument();
    expect(linea.textContent).toMatch(/3 meses/);
  });

  it("con segmento abierto (salida null), lo dice explícito", () => {
    render(
      <VallesCard
        valles={[
          valle({
            entrada: "2027-03",
            salida: null,
            duracion: 4,
          }),
        ]}
        cargando={false}
      />,
    );
    expect(screen.getByText(/aún no sale/)).toBeInTheDocument();
  });

  // RF-F3 · P3b — chips de cambio vs. última versión aprobada.

  it("marca «nuevo» cuando el mes está en mesesNuevos", () => {
    render(
      <VallesCard
        valles={[valle({ mes: "2027-05" })]}
        cargando={false}
        mesesNuevos={new Set(["2027-05"])}
      />,
    );
    expect(screen.getByText("nuevo")).toBeInTheDocument();
    expect(screen.queryByText("más profundo")).toBeNull();
  });

  it("marca «más profundo» cuando el mes está en mesesMasProfundos", () => {
    render(
      <VallesCard
        valles={[valle({ mes: "2027-05" })]}
        cargando={false}
        mesesMasProfundos={new Set(["2027-05"])}
      />,
    );
    expect(screen.getByText("más profundo")).toBeInTheDocument();
    expect(screen.queryByText("nuevo")).toBeNull();
  });

  it("si por bug llegan las dos, gana «nuevo» (disjuntos por diseño en backend)", () => {
    render(
      <VallesCard
        valles={[valle({ mes: "2027-05" })]}
        cargando={false}
        mesesNuevos={new Set(["2027-05"])}
        mesesMasProfundos={new Set(["2027-05"])}
      />,
    );
    expect(screen.getByText("nuevo")).toBeInTheDocument();
    expect(screen.queryByText("más profundo")).toBeNull();
  });

  it("sin sets, no pinta ningún chip (compat)", () => {
    render(<VallesCard valles={[valle()]} cargando={false} />);
    expect(screen.queryByText("nuevo")).toBeNull();
    expect(screen.queryByText("más profundo")).toBeNull();
  });

  // RF-F5 · Las 3 palancas del valle.

  it("con palancas activas muestra los chips de gasto e ingreso + link a FABS", () => {
    const v = valle({
      palancas: {
        recorte_gasto: {
          monto: "5000000.00",
          unidad: "COP/mes",
          alcanzable: true,
          referencia: "100000000.00",
          mensaje: "",
        },
        ingreso_extra: {
          monto: "8000000.00",
          unidad: "COP/mes",
          alcanzable: true,
          referencia: "100000000.00",
          mensaje: "",
        },
        unidades_extra: {
          monto: null,
          unidad: "motos/mes",
          alcanzable: false,
          disponible: false,
          ver_en: "cfo.escenario.motos_para_evitar_umbral",
          mes_referencia: "2027-05",
        },
      },
    });
    render(<VallesCard valles={[v]} cargando={false} />);
    expect(screen.getByText(/recortar/i)).toBeInTheDocument();
    expect(screen.getByText(/ingresar/i)).toBeInTheDocument();
    expect(screen.getByText(/motos extra: ver en FABS/i)).toBeInTheDocument();
  });

  it("con palancas de monto 0 no las pinta (no ensucia la lectura)", () => {
    const v = valle({
      palancas: {
        recorte_gasto: {
          monto: "0",
          unidad: "COP/mes",
          alcanzable: true,
          referencia: "30000000",
          mensaje: "Ya se cumple sin cambios.",
        },
        ingreso_extra: {
          monto: "0",
          unidad: "COP/mes",
          alcanzable: true,
          referencia: "30000000",
          mensaje: "Ya se cumple sin cambios.",
        },
        unidades_extra: {
          monto: null,
          unidad: "motos/mes",
          alcanzable: false,
          disponible: false,
          ver_en: "cfo.escenario.motos_para_evitar_umbral",
          mes_referencia: "2027-05",
        },
      },
    });
    render(<VallesCard valles={[v]} cargando={false} />);
    expect(screen.queryByText(/recortar/i)).toBeNull();
    expect(screen.queryByText(/ingresar/i)).toBeNull();
    // Tampoco el chip de FABS (si no hay palancas útiles, no aportamos ruido)
    expect(screen.queryByText(/motos extra/i)).toBeNull();
  });

  // RF-F7 · reparto por rubro bajo el chip de recorte.

  const _palancasConReparto = () => ({
    recorte_gasto: {
      monto: "20000000.00",
      unidad: "COP/mes" as const,
      alcanzable: true,
      referencia: "100000000.00",
      mensaje: "",
      recomendaciones_por_rubro: [
        {
          rubro_id: "r1",
          rubro_nombre: "Sueldos",
          monto_recortar: "15000000.00",
          gasto_actual: "30000000.00",
          pct_de_su_gasto: "0.5000",
        },
        {
          rubro_id: "r2",
          rubro_nombre: "Arriendo",
          monto_recortar: "5000000.00",
          gasto_actual: "10000000.00",
          pct_de_su_gasto: "0.5000",
        },
      ],
    },
    ingreso_extra: {
      monto: "0",
      unidad: "COP/mes" as const,
      alcanzable: true,
      referencia: "100000000.00",
      mensaje: "",
    },
    unidades_extra: {
      monto: null,
      unidad: "motos/mes" as const,
      alcanzable: false as const,
      disponible: false as const,
      ver_en: "cfo.escenario.motos_para_evitar_umbral",
      mes_referencia: "2027-05",
    },
  });

  it("expone el botón «ver reparto» y muestra la lista solo al abrir", () => {
    const v = valle({ palancas: _palancasConReparto() });
    render(<VallesCard valles={[v]} cargando={false} />);
    // Cerrado por defecto — la lista no aparece.
    expect(screen.queryByText("Sueldos")).toBeNull();
    const boton = screen.getByRole("button", { name: /ver reparto/i });
    fireEvent.click(boton);
    // Abierto: aparecen los rubros en orden por impacto (Sueldos primero).
    const items = screen.getAllByRole("listitem");
    const textos = items.map((li) => li.textContent ?? "").join(" | ");
    expect(textos).toMatch(/Sueldos.*Arriendo/s);
    // Percentaje del rubro visible.
    expect(screen.getAllByText(/50% del rubro/).length).toBeGreaterThanOrEqual(
      2,
    );
    // El botón cambia a «ocultar».
    expect(
      screen.getByRole("button", { name: /ocultar reparto/i }),
    ).toBeInTheDocument();
  });

  it("declara el faltante cuando el reparto no cubre el objetivo (regla del 50%)", () => {
    const palancas = _palancasConReparto();
    palancas.recorte_gasto.monto = "30000000.00"; // objetivo mayor a los 20M que suman los rubros
    const v = valle({ palancas });
    render(<VallesCard valles={[v]} cargando={false} />);
    fireEvent.click(screen.getByRole("button", { name: /ver reparto/i }));
    expect(screen.getByText(/Falta cubrir/i)).toBeInTheDocument();
    expect(screen.getByText(/otras palancas/i)).toBeInTheDocument();
  });

  it("no muestra «ver reparto» cuando la palanca no viene con recomendaciones", () => {
    const v = valle({
      palancas: {
        recorte_gasto: {
          monto: "5000000.00",
          unidad: "COP/mes",
          alcanzable: true,
          referencia: "100000000.00",
          mensaje: "",
          // sin `recomendaciones_por_rubro` — el reparto no está disponible.
        },
        ingreso_extra: {
          monto: "0",
          unidad: "COP/mes",
          alcanzable: true,
          referencia: "100000000.00",
          mensaje: "",
        },
        unidades_extra: {
          monto: null,
          unidad: "motos/mes",
          alcanzable: false,
          disponible: false,
          ver_en: "cfo.escenario.motos_para_evitar_umbral",
          mes_referencia: "2027-05",
        },
      },
    });
    render(<VallesCard valles={[v]} cargando={false} />);
    expect(screen.queryByRole("button", { name: /ver reparto/i })).toBeNull();
  });
});
