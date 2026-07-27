// Inicio — PILOTO del sistema F1 (§7): titular de juicio que reconcilia el
// mensaje, 4 KpiTiles v2 (sin Runway — baja a Proyecciones en F1.1), gráfico
// protagonista con ejes/umbral etiquetado/mínimo anotado, y realidad vs.
// proyección con estado vacío accionable.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Mes } from "@/lib/meses";
import type { MesProyeccion, Proyeccion } from "@/lib/proyeccion";
import InicioPage from "@/pages/InicioPage";

function mesProy(overrides: Partial<MesProyeccion>): MesProyeccion {
  return {
    mes: "2026-07",
    motos: 50,
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
    caja: "40000000.00",
    estado: "critico",
    ...overrides,
  };
}

const PROY: Proyeccion = {
  escenario: "base",
  caja_minima: "125000000.00",
  fondo_provision: [],
  piso_caja: "40000000.00",
  mes_mas_ajustado: "2026-09",
  meses_bajo_minimo: 2,
  caja_final: "200000000.00",
  capital_requerido: "85000000.00",
  runway_meses: null,
  meses: [
    mesProy({ mes: "2026-07", caja: "40000000.00", estado: "critico" }),
    mesProy({ mes: "2026-08", caja: "200000000.00", estado: "ok" }),
  ],
};

const COMPARA = {
  escenario: "base",
  ancla_modo: "cerrado",
  ancla: { mes: "2026-06", caja_real: "15000000.00" },
  actuals: [{ mes: "2026-06", caja_real: "15000000.00" }],
  forecast: [
    { mes: "2026-06", caja: "15000000.00" },
    { mes: "2026-07", caja: "18000000.00" },
  ],
};

const MES_ACTIVO: Mes = {
  id: "m1",
  mes: "2026-07-01",
  estado: "en_ejecucion",
  saldo_inicial_caja: "0.00",
  saldos_banco: [
    { banco: "global66", saldo: "500000000.00", fecha_reporte: "2026-07-20" },
    {
      banco: "bancolombia",
      saldo: "204700000.00",
      fecha_reporte: "2026-07-19",
    },
  ],
  ingresos_esperados_semana: null,
};

const mocks = vi.hoisted(() => ({
  obtenerProyeccion: vi.fn(),
  obtenerComparacion: vi.fn(),
  listarMeses: vi.fn(),
}));

vi.mock("@/lib/proyeccion", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/proyeccion")>();
  return {
    ...real,
    obtenerProyeccion: mocks.obtenerProyeccion,
    obtenerComparacion: mocks.obtenerComparacion,
  };
});

vi.mock("@/lib/meses", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/meses")>();
  return { ...real, listarMeses: mocks.listarMeses };
});

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <InicioPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.obtenerProyeccion.mockResolvedValue(PROY);
  mocks.obtenerComparacion.mockResolvedValue(COMPARA);
  mocks.listarMeses.mockResolvedValue({ items: [MES_ACTIVO] });
});

describe("InicioPage — piloto F1 (§7)", () => {
  it("pide el horizonte de 18 meses (default F1)", async () => {
    renderPage();
    await screen.findByText("Piso de caja");
    expect(mocks.obtenerProyeccion).toHaveBeenCalledWith({
      escenario: "base",
      horizonteMeses: 18,
    });
  });

  it("muestra el titular de juicio que reconcilia el mensaje", async () => {
    renderPage();
    // crece (caja_final 200M > primer mes 40M) PERO perfora en sep-26
    expect(
      await screen.findByText(
        /La caja crece, pero perfora el mínimo en sep-26/,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/Capital para cubrirlo/)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Ver el mes crítico/ }),
    ).toBeInTheDocument();
  });

  it("muestra los 4 KPIs del piloto — el Runway ya no está", async () => {
    renderPage();
    expect(await screen.findByText("Piso de caja")).toBeInTheDocument();
    expect(screen.getByText("Meses bajo el mínimo")).toBeInTheDocument();
    expect(screen.getByText("2 de 2")).toBeInTheDocument(); // n de horizonte
    expect(screen.getByText("Capital requerido")).toBeInTheDocument();
    expect(screen.getByText("Caja hoy")).toBeInTheDocument();
    expect(screen.queryByText("Runway")).toBeNull();
  });

  it("la caja hoy suma los bancos del mes operando y enlaza a la Cabina", async () => {
    renderPage();
    // 500M + 204,7M = $ 704,7 M (suma Decimal, presentación compacta)
    expect(await screen.findByText("$ 704,7 M")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Caja hoy/ })).toHaveAttribute(
      "href",
      "/mes",
    );
  });

  it("el gráfico protagonista lleva conclusión, ejes y umbral etiquetado", async () => {
    renderPage();
    expect(
      await screen.findByRole("heading", {
        name: /La caja toca su punto más bajo en sep-26/,
      }),
    ).toBeInTheDocument();
    // umbral etiquetado sobre el trazo (no leyenda)
    expect(screen.getByText(/— Umbral \$ 125 M/)).toBeInTheDocument();
    // eje X con meses mmm-aa
    expect(screen.getByText("jul-26")).toBeInTheDocument();
    // anotación del mínimo (mes · cifra)
    expect(screen.getByText(/jul-26 · \$ 40 M/)).toBeInTheDocument();
  });

  it("realidad vs. proyección se conserva como soporte", async () => {
    renderPage();
    expect(
      screen.getByRole("heading", { name: "Realidad vs. proyección" }),
    ).toBeInTheDocument();
    expect(await screen.findByText(/Último real/)).toBeInTheDocument();
  });

  it("sin ancla, el vacío es accionable hacia el ciclo (EstadoVacio)", async () => {
    mocks.obtenerComparacion.mockResolvedValue({
      ...COMPARA,
      ancla: null,
      actuals: [],
      forecast: [],
    });
    renderPage();
    expect(
      await screen.findByRole("link", { name: /Ir al ciclo del mes/ }),
    ).toBeInTheDocument();
  });
});
