// CabinaMesPage (C2 §7.2 y §7.6): las 5 tarjetas según el estado del mes, y el
// cierre real (gate por capacidad, checklist de precondiciones, confirmación con
// Idempotency-Key — patrón C1).

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";
import type { Mes } from "@/lib/meses";
import CabinaMesPage from "@/pages/CabinaMesPage";

const mocks = vi.hoisted(() => ({
  listarMeses: vi.fn(),
  listarPresupuesto: vi.fn(),
  vistaControl: vi.fn(),
  cierreConciliacion: vi.fn(),
  confirmarCierre: vi.fn(),
  caps: { actual: [] as string[] },
}));

vi.mock("@/auth/AuthContext", () => ({
  useAuth: () => ({
    rol: "admin",
    puede: (cap: string) => mocks.caps.actual.includes(cap),
  }),
}));

vi.mock("@/lib/meses", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/meses")>();
  return { ...real, listarMeses: mocks.listarMeses };
});

vi.mock("@/lib/presupuesto", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/presupuesto")>();
  return { ...real, listarPresupuesto: mocks.listarPresupuesto };
});

vi.mock("@/lib/control", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/control")>();
  return { ...real, vistaControl: mocks.vistaControl };
});

vi.mock("@/lib/cierre", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/cierre")>();
  return {
    ...real,
    cierreConciliacion: mocks.cierreConciliacion,
    confirmarCierre: mocks.confirmarCierre,
  };
});

function mes(estado: Mes["estado"], mesIso = "2026-08-01", id = "m1"): Mes {
  return {
    id,
    mes: mesIso,
    estado,
    saldo_inicial_caja: "0.00",
    saldos_banco: [],
    ingresos_esperados_semana: null,
  };
}

const LINEA = {
  id: "l1",
  rubro_id: "r1",
  version: 1,
  monto_sugerido: "1000000.00",
  prom_3m: "900000.00",
  tendencia_mes: "0.00",
  crec_pct: "0",
  compromisos_programados: "0.00",
  monto_definido: "1200000.00",
  historia_incompleta: false,
  modo_calculo: "historico" as const,
  vigente: true,
};

const CONTROL = {
  mes: "2026-08",
  estado: "en_ejecucion",
  grupos: [
    {
      grupo: "operacion",
      subtotal: {
        definido: "1200000.00",
        ejecutado: "800000.00",
        disponible: "400000.00",
      },
      lineas: [
        {
          rubro_id: "r1",
          rubro: "Arriendos",
          definido: "1200000.00",
          ejecutado: "800000.00",
          disponible: "-100000.00",
          pct_ejecutado: "108",
          semaforo: "rojo" as const,
        },
      ],
    },
  ],
  total: {
    definido: "1200000.00",
    ejecutado: "800000.00",
    disponible: "400000.00",
  },
  caja_disponible: "0.00",
  sin_presupuesto: [],
};

const CONCILIACION = {
  mes: "2026-08",
  por_banco: [],
  sin_dato: [],
  consolidado_reportado: "5000000.00",
  caja_libro: "4990000.00",
  diferencia: "10000.00",
  umbral: "50000.00",
  dentro_de_umbral: true,
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/mes"]}>
        <CabinaMesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.caps.actual = [
    "dashboard:leer",
    "caja:reportar",
    "ciclo:cierre_operativo",
    "ciclo:confirmar_cierre",
  ];
  mocks.listarPresupuesto.mockResolvedValue({
    mes: "2026-08",
    lineas: [LINEA],
  });
  mocks.vistaControl.mockResolvedValue(CONTROL);
  mocks.cierreConciliacion.mockResolvedValue(CONCILIACION);
});

describe("CabinaMesPage — tarjetas por estado (§7.2)", () => {
  it("mes sugerido sin líneas: CTA de presupuesto, caja y cierre deshabilitados", async () => {
    mocks.listarMeses.mockResolvedValue({ items: [mes("sugerido")] });
    mocks.listarPresupuesto.mockResolvedValue({ mes: "2026-08", lineas: [] });
    renderPage();
    expect(await screen.findByText("Mes y ciclo")).toBeInTheDocument();
    expect(
      await screen.findByRole("link", { name: "Generar sugerido →" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/El reporte de caja se habilita/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/El cierre se habilita cuando el mes esté en ejecución/),
    ).toBeInTheDocument();
    expect(screen.queryByText("Qué exige atención")).toBeNull();
  });

  it("mes en ejecución: caja + atención + cierre con checklist", async () => {
    mocks.listarMeses.mockResolvedValue({
      items: [mes("en_ejecucion"), mes("sugerido", "2026-09-01", "m2")],
    });
    renderPage();
    // caja del día (formulario con caja:reportar)
    expect(await screen.findByText("Reportar saldo")).toBeInTheDocument();
    // atención priorizada (top 5)
    expect(await screen.findByText("Qué exige atención")).toBeInTheDocument();
    expect(screen.getByText(/«Arriendos» se pasó/)).toBeInTheDocument();
    // cierre: precondición de mes siguiente abierta ✓ y botones con capacidad
    expect(screen.getByText(/Mes siguiente abierto/)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Verificar conciliación" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Cerrar mes" }),
    ).toBeInTheDocument();
    // mini barra definido vs ejecutado
    expect(screen.getByText(/67 %/)).toBeInTheDocument();
  });

  it("mes cerrado: resumen inmutable", async () => {
    mocks.listarMeses.mockResolvedValue({ items: [mes("cerrado")] });
    renderPage();
    expect(
      await screen.findByText(/está cerrado: el histórico es inmutable/),
    ).toBeInTheDocument();
  });

  it("sin capacidades de cierre no hay botones (regla 9)", async () => {
    mocks.caps.actual = ["dashboard:leer"];
    mocks.listarMeses.mockResolvedValue({
      items: [mes("en_ejecucion"), mes("sugerido", "2026-09-01", "m2")],
    });
    renderPage();
    expect(await screen.findByText("Cierre")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Verificar conciliación" }),
    ).toBeNull();
    expect(screen.queryByRole("button", { name: "Cerrar mes" })).toBeNull();
  });
});

describe("CabinaMesPage — cierre real (§7.6)", () => {
  it("verificar conciliación muestra diferencia y umbral", async () => {
    mocks.listarMeses.mockResolvedValue({
      items: [mes("en_ejecucion"), mes("sugerido", "2026-09-01", "m2")],
    });
    renderPage();
    fireEvent.click(
      await screen.findByRole("button", { name: "Verificar conciliación" }),
    );
    expect(
      await screen.findByText(/Diferencia \$ 10\.000,00/),
    ).toBeInTheDocument();
    expect(mocks.cierreConciliacion).toHaveBeenCalledWith("2026-08");
  });

  it("cerrar mes: diálogo + Idempotency-Key; el reintento reusa la key", async () => {
    mocks.confirmarCierre
      .mockRejectedValueOnce(new ApiError(409, "concurrencia; reintentar"))
      .mockResolvedValue({
        mes: "2026-08",
        estado: "cerrado",
        diferencia: "10000.00",
        ajuste_tx_id: "t1",
        saldo_inicial_siguiente: "5000000.00",
      });
    mocks.listarMeses.mockResolvedValue({
      items: [mes("en_ejecucion"), mes("sugerido", "2026-09-01", "m2")],
    });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Cerrar mes" }));
    const dialogo = await screen.findByRole("dialog", { name: "Cerrar mes" });
    expect(dialogo).toHaveTextContent("2026-08");

    const confirmar = screen
      .getAllByRole("button", { name: "Cerrar mes" })
      .find((b) => dialogo.contains(b)) as HTMLElement;
    fireEvent.click(confirmar);
    expect(await screen.findByText(/reintentar/)).toBeInTheDocument();

    fireEvent.click(confirmar);
    expect(await screen.findByText(/Mes 2026-08 cerrado/)).toBeInTheDocument();
    expect(mocks.confirmarCierre).toHaveBeenCalledTimes(2);
    const [primera, segunda] = mocks.confirmarCierre.mock.calls;
    expect(primera[0]).toBe("2026-08");
    expect(segunda[1]).toBe(primera[1]);
  });

  it("sin mes siguiente abierto, 'Cerrar mes' está deshabilitado (precondición ✗)", async () => {
    mocks.listarMeses.mockResolvedValue({ items: [mes("en_ejecucion")] });
    renderPage();
    const boton = await screen.findByRole("button", { name: "Cerrar mes" });
    expect(boton).toBeDisabled();
    expect(screen.getByText("✗")).toBeInTheDocument();
  });
});
