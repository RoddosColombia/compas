// frontend/src/pages/ProyeccionPage.test.tsx
//
// F1.1 §2 — Proyecciones al estándar: juicio a horizonte largo (60 m) con
// ventana de 18 m por defecto, 4 KpiTileV2 (Runway "Sin límite" cuando null),
// ChartCard con conclusión dinámica, tabla-ventana expandible sin centavos con
// el mes crítico resaltado/anclado, y FiltroBarra de horizonte con "Limpiar".

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { MesProyeccion, Proyeccion } from "@/lib/proyeccion";
import ProyeccionPage from "@/pages/ProyeccionPage";

function mesProy(
  i: number,
  extras: Partial<MesProyeccion> = {},
): MesProyeccion {
  const y = 2026 + Math.floor((6 + i) / 12);
  const m = ((6 + i) % 12) + 1;
  return {
    mes: `${y}-${String(m).padStart(2, "0")}`,
    motos: 50 + i,
    cartera: 120,
    recaudo_credito: "30000000.00",
    cuotas_iniciales: "5000000.00",
    ingreso_bruto: "35000000.00",
    neto: "34000000.00",
    provision: "-700000.00",
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
    caja: "200000000.00",
    estado: "ok",
    ...extras,
  };
}

// 60 meses (lo que trae la query de juicio); el crítico es el mes 3 (2026-10).
const MESES = Array.from({ length: 60 }, (_, i) =>
  i === 3 ? mesProy(i, { caja: "40000000.00", estado: "critico" }) : mesProy(i),
);

const PROY: Proyeccion = {
  escenario: "base",
  caja_minima: "125000000.00",
  fondo_provision: [],
  piso_caja: "40000000.00",
  mes_mas_ajustado: "2026-10",
  meses_bajo_minimo: 1,
  caja_final: "200000000.00",
  capital_requerido: "85000000.00",
  runway_meses: null,
  ventana_reconciliada: null,
  interes_obligaciones: {},
  meses: MESES,
};

const mocks = vi.hoisted(() => ({ obtenerProyeccion: vi.fn() }));

vi.mock("@/lib/proyeccion", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/proyeccion")>();
  return { ...real, obtenerProyeccion: mocks.obtenerProyeccion };
});

function renderPage() {
  mocks.obtenerProyeccion.mockResolvedValue(PROY);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ProyeccionPage />
    </QueryClientProvider>,
  );
}

describe("ProyeccionPage — F1.1 §2", () => {
  it("el juicio pide horizonte largo aunque la ventana sea 18 m", async () => {
    renderPage();
    await screen.findByText("Piso de caja");
    expect(mocks.obtenerProyeccion).toHaveBeenCalledWith({
      escenario: "base",
      horizonteMeses: 60,
    });
  });

  it("muestra los 4 KPIs con juicio — Runway null es 'Sin límite'", async () => {
    renderPage();
    expect(await screen.findByText("Piso de caja")).toBeInTheDocument();
    expect(screen.getByText("1 de 60")).toBeInTheDocument();
    expect(screen.getByText("Capital requerido")).toBeInTheDocument();
    expect(screen.getByText("Sin límite")).toBeInTheDocument();
    expect(
      screen.getByText("la caja crece al ritmo actual"),
    ).toBeInTheDocument();
    // ya no hay tile de Caja final: vive en el pie del gráfico
    expect(screen.queryByText("Caja final")).toBeNull();
    expect(screen.getByText(/Caja final a 60 meses/)).toBeInTheDocument();
  });

  it("la conclusión del gráfico nombra el mes crítico y lo ancla en la tabla", async () => {
    renderPage();
    expect(
      await screen.findByRole("heading", {
        name: /La caja toca su punto más bajo en oct-26/,
      }),
    ).toBeInTheDocument();
    // botón accesible (no <a>): expande y desplaza a la fila del mes crítico
    const ancla = screen.getByRole("button", { name: /Ver el mes crítico/ });
    expect(ancla).toBeInTheDocument();
    expect(document.getElementById("mes-critico")).not.toBeNull();
  });

  it("crítico fuera de la ventana: 'Ver el mes crítico' expande la tabla", async () => {
    // el mes crítico cae en el índice 30 (2029-01), fuera de la ventana de 18 m
    Element.prototype.scrollIntoView = vi.fn(); // jsdom no lo implementa
    const meses = Array.from({ length: 60 }, (_, i) =>
      i === 30
        ? mesProy(i, { caja: "40000000.00", estado: "critico" })
        : mesProy(i),
    );
    mocks.obtenerProyeccion.mockResolvedValue({
      ...PROY,
      mes_mas_ajustado: meses[30].mes,
      meses,
    });
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={qc}>
        <ProyeccionPage />
      </QueryClientProvider>,
    );
    await screen.findByText("Piso de caja");
    // ventana por defecto: 18 filas y el mes crítico aún NO está en el DOM
    expect(document.querySelectorAll("tbody tr")).toHaveLength(18);
    expect(document.getElementById("mes-critico")).toBeNull();
    // clic en el botón → la tabla se expande y el mes crítico aparece
    fireEvent.click(screen.getByRole("button", { name: /Ver el mes crítico/ }));
    expect(document.querySelectorAll("tbody tr")).toHaveLength(60);
    expect(document.getElementById("mes-critico")).not.toBeNull();
  });

  it("la tabla es ventana (18 filas), sin centavos, y se expande a los 60", async () => {
    renderPage();
    await screen.findByText("Piso de caja");
    expect(document.querySelectorAll("tbody tr")).toHaveLength(18);
    // sin centavos en la tabla (política F1 §3). La columna Ingreso = neto (34M).
    expect(screen.queryByText(/\$\s?34\.000\.000,00/)).toBeNull();
    expect(
      screen.getAllByText((t) => t.replace(/\s/g, " ") === "$ 34.000.000")
        .length,
    ).toBeGreaterThan(0);
    // estado con símbolo (color nunca solo)
    expect(screen.getAllByText(/✓ OK/).length).toBeGreaterThan(0);
    fireEvent.click(
      screen.getByRole("button", { name: "Ver los 60 meses completos" }),
    );
    expect(document.querySelectorAll("tbody tr")).toHaveLength(60);
  });

  it("FiltroBarra: cambiar el horizonte muestra 'Limpiar' y restaura el default", async () => {
    renderPage();
    await screen.findByText("Piso de caja");
    expect(screen.queryByRole("button", { name: "Limpiar" })).toBeNull();
    fireEvent.change(screen.getByLabelText(/Horizonte/), {
      target: { value: "180" },
    });
    const limpiar = await screen.findByRole("button", { name: "Limpiar" });
    fireEvent.click(limpiar);
    expect(screen.queryByRole("button", { name: "Limpiar" })).toBeNull();
    expect(screen.getByLabelText(/Horizonte/)).toHaveValue("18");
  });

  it("muestra el KPI Compromiso Auteco (este mes + el próximo)", async () => {
    renderPage();
    expect(await screen.findByText("Compromiso Auteco")).toBeInTheDocument();
    // sin facturas registradas → proyección; los dos primeros meses de la ventana
    expect(
      screen.getByText(/Lote \+ fondeo de jul-26 y ago-26 · proyección/),
    ).toBeInTheDocument();
  });

  it("ofrece los tres escenarios", async () => {
    renderPage();
    await screen.findByText("Piso de caja");
    for (const e of ["Pesimista", "Base", "Optimista"]) {
      expect(screen.getByRole("button", { name: e })).toBeInTheDocument();
    }
  });
});
