// frontend/src/pages/PresupuestoMesPage.test.tsx
//
// Sprint C1 — criterios de terminado (§5 del plan):
//   1. Render por estado del mes (CTA generar / acotar habilitado / solo lectura).
//   2. Generar: "15" humano → crec_pct "0.15".
//   3. Acotar: PATCH con monto string; 409 muestra el mensaje del backend.
//   4. Aprobar: gate por capacidad; Idempotency-Key generada al abrir el diálogo
//      y REUSADA en el reintento; 409 muestra aviso.
//   5. Totales sin float (suma de montos string con money.ts).

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";
import type { Mes } from "@/lib/meses";
import type { LineaPresupuesto } from "@/lib/presupuesto";
import type { Rubro } from "@/lib/rubros";
import PresupuestoMesPage from "@/pages/PresupuestoMesPage";

const mocks = vi.hoisted(() => ({
  listarMeses: vi.fn(),
  listarRubros: vi.fn(),
  generarSugerido: vi.fn(),
  listarPresupuesto: vi.fn(),
  acotarLinea: vi.fn(),
  aprobarPresupuesto: vi.fn(),
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

vi.mock("@/lib/rubros", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/rubros")>();
  return { ...real, listarRubros: mocks.listarRubros };
});

vi.mock("@/lib/presupuesto", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/presupuesto")>();
  return {
    ...real,
    generarSugerido: mocks.generarSugerido,
    listarPresupuesto: mocks.listarPresupuesto,
    acotarLinea: mocks.acotarLinea,
    aprobarPresupuesto: mocks.aprobarPresupuesto,
  };
});

function mes(estado: Mes["estado"]): Mes {
  return {
    id: "m1",
    mes: "2026-08-01",
    estado,
    saldo_inicial_caja: "0.00",
    saldos_banco: [],
    ingresos_esperados_semana: null,
  };
}

const RUBROS: Rubro[] = [
  {
    id: "r1",
    grupo: "operacion",
    nombre: "Arriendos",
    tipo_flujo: "egreso",
    codigo: "2070",
    tipo: "fijo",
    orden: 1,
    activo: true,
    es_sistema: false,
  },
  {
    id: "r2",
    grupo: "nomina",
    nombre: "Salarios",
    tipo_flujo: "egreso",
    codigo: "3010",
    tipo: "fijo",
    orden: 1,
    activo: true,
    es_sistema: false,
  },
];

function linea(overrides: Partial<LineaPresupuesto>): LineaPresupuesto {
  return {
    id: "l1",
    rubro_id: "r1",
    version: 1,
    monto_sugerido: "1000000.00",
    prom_3m: "900000.00",
    tendencia_mes: "50000.00",
    crec_pct: "0.15",
    compromisos_programados: "0.00",
    monto_definido: null,
    historia_incompleta: false,
    modo_calculo: "historico",
    vigente: true,
    ...overrides,
  };
}

const LINEAS = [
  linea({ id: "l1", rubro_id: "r1", monto_sugerido: "1000000.00" }),
  linea({
    id: "l2",
    rubro_id: "r2",
    monto_sugerido: "2000000.00",
    monto_definido: "1500000.00",
    historia_incompleta: true,
  }),
];

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/meses/2026-08/presupuesto"]}>
        <Routes>
          <Route
            path="/meses/:mes/presupuesto"
            element={<PresupuestoMesPage />}
          />
          <Route path="/control" element={<p>Vista Control</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.caps.actual = [
    "dashboard:leer",
    "ciclo:abrir",
    "presupuesto:acotar",
    "ciclo:aprobar",
  ];
  mocks.listarMeses.mockResolvedValue({ items: [mes("sugerido")] });
  mocks.listarRubros.mockResolvedValue(RUBROS);
  mocks.listarPresupuesto.mockResolvedValue({ mes: "2026-08", lineas: LINEAS });
});

describe("PresupuestoMesPage — render por estado (§5.1)", () => {
  it("sugerido sin líneas: muestra el CTA de generar", async () => {
    mocks.listarPresupuesto.mockResolvedValue({ mes: "2026-08", lineas: [] });
    renderPage();
    expect(
      await screen.findByRole("button", {
        name: "Generar presupuesto sugerido",
      }),
    ).toBeInTheDocument();
    // la fórmula queda explicada en una línea
    expect(
      screen.getByText(/promedio de los últimos 3 meses/),
    ).toBeInTheDocument();
  });

  it("sugerido con líneas: acotar habilitado + badge de historia incompleta", async () => {
    renderPage();
    expect(
      await screen.findByLabelText("Definido Arriendos"),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Definido Salarios")).toBeInTheDocument();
    expect(screen.getByText("historia incompleta")).toBeInTheDocument();
    // agrupado por grupo de rubro
    expect(screen.getByText("Operación")).toBeInTheDocument();
    expect(screen.getByText("Nómina")).toBeInTheDocument();
  });

  it("en_ejecucion: solo lectura con enlace a Control", async () => {
    mocks.listarMeses.mockResolvedValue({ items: [mes("en_ejecucion")] });
    renderPage();
    expect(await screen.findByText(/solo lectura/)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Ver el control del mes/ }),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Definido Arriendos")).toBeNull();
    expect(
      screen.queryByRole("button", { name: "Aprobar presupuesto" }),
    ).toBeNull();
  });

  it("cerrado: aviso de inmutable, sin edición", async () => {
    mocks.listarMeses.mockResolvedValue({ items: [mes("cerrado")] });
    renderPage();
    // el aviso Y el stepper hablan de inmutabilidad → al menos una mención
    expect((await screen.findAllByText(/inmutable/)).length).toBeGreaterThan(0);
    expect(screen.queryByLabelText("Definido Arriendos")).toBeNull();
  });
});

describe("PresupuestoMesPage — generar sugerido (§5.2)", () => {
  it("'15' humano viaja como crec_pct '0.15'", async () => {
    // 1ª lectura: sin líneas (CTA); tras generar, el refetch trae las líneas.
    mocks.listarPresupuesto
      .mockReset()
      .mockResolvedValueOnce({ mes: "2026-08", lineas: [] })
      .mockResolvedValue({ mes: "2026-08", lineas: LINEAS });
    mocks.generarSugerido.mockResolvedValue({ mes: "2026-08", lineas: LINEAS });
    renderPage();
    const pct = await screen.findByLabelText(/% crecimiento/);
    fireEvent.change(pct, { target: { value: "15" } });
    fireEvent.click(
      screen.getByRole("button", { name: "Generar presupuesto sugerido" }),
    );
    expect(await screen.findByText("Operación")).toBeInTheDocument();
    expect(mocks.generarSugerido).toHaveBeenCalledWith("2026-08", "0.15");
  });
});

describe("PresupuestoMesPage — acotar (§5.3)", () => {
  it("guarda el monto como string y refresca del backend", async () => {
    mocks.acotarLinea.mockResolvedValue(
      linea({ rubro_id: "r1", monto_definido: "1200000" }),
    );
    renderPage();
    const input = await screen.findByLabelText("Definido Arriendos");
    fireEvent.change(input, { target: { value: "1200000" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));
    expect(await screen.findByLabelText("Definido Arriendos")).toBeVisible();
    expect(mocks.acotarLinea).toHaveBeenCalledWith(
      "2026-08",
      "r1",
      "1200000",
      undefined,
    );
  });

  it("un 409 del backend se muestra en lenguaje llano", async () => {
    mocks.acotarLinea.mockRejectedValue(
      new ApiError(409, "el mes está cerrado y es inmutable (regla 4)"),
    );
    renderPage();
    const input = await screen.findByLabelText("Definido Arriendos");
    fireEvent.change(input, { target: { value: "1200000" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));
    expect(
      await screen.findByText("el mes está cerrado y es inmutable (regla 4)"),
    ).toBeInTheDocument();
  });
});

describe("PresupuestoMesPage — aprobar (§5.4)", () => {
  it("sin ciclo:aprobar el botón no existe", async () => {
    mocks.caps.actual = ["dashboard:leer", "presupuesto:acotar"];
    renderPage();
    expect(await screen.findByLabelText("Definido Arriendos")).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "Aprobar presupuesto" }),
    ).toBeNull();
  });

  it("aprueba con Idempotency-Key y el reintento del diálogo REUSA la key", async () => {
    mocks.aprobarPresupuesto
      .mockRejectedValueOnce(
        new ApiError(409, "petición con esta Idempotency-Key en curso"),
      )
      .mockResolvedValue({ mes: "2026-08", estado: "en_ejecucion", lineas: 2 });
    renderPage();
    fireEvent.click(
      await screen.findByRole("button", { name: "Aprobar presupuesto" }),
    );
    // diálogo con el resumen
    const dialogo = await screen.findByRole("dialog", {
      name: "Aprobar presupuesto",
    });
    expect(dialogo).toHaveTextContent("Líneas de presupuesto");
    expect(dialogo).toHaveTextContent("2");

    // 1er intento → 409 "en curso" muestra aviso, no re-dispara solo
    fireEvent.click(screen.getByRole("button", { name: "Aprobar" }));
    expect(
      await screen.findByText(/Idempotency-Key en curso/),
    ).toBeInTheDocument();
    expect(mocks.aprobarPresupuesto).toHaveBeenCalledTimes(1);

    // reintento del MISMO diálogo → misma key (replay seguro §1.12)
    fireEvent.click(screen.getByRole("button", { name: "Aprobar" }));
    expect(await screen.findByText("Vista Control")).toBeInTheDocument();
    expect(mocks.aprobarPresupuesto).toHaveBeenCalledTimes(2);
    const [primera, segunda] = mocks.aprobarPresupuesto.mock.calls;
    expect(primera[0]).toBe("2026-08");
    expect(primera[1]).toMatch(/[0-9a-f-]{36}/);
    expect(segunda[1]).toBe(primera[1]);
  });

  it("cada apertura del diálogo genera una key NUEVA", async () => {
    mocks.aprobarPresupuesto.mockRejectedValue(
      new ApiError(500, "error interno"),
    );
    renderPage();
    fireEvent.click(
      await screen.findByRole("button", { name: "Aprobar presupuesto" }),
    );
    fireEvent.click(await screen.findByRole("button", { name: "Aprobar" }));
    expect(await screen.findByText("error interno")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));

    fireEvent.click(
      screen.getByRole("button", { name: "Aprobar presupuesto" }),
    );
    fireEvent.click(await screen.findByRole("button", { name: "Aprobar" }));
    expect(await screen.findByText("error interno")).toBeInTheDocument();
    const [primera, segunda] = mocks.aprobarPresupuesto.mock.calls;
    expect(segunda[1]).not.toBe(primera[1]);
  });
});

describe("PresupuestoMesPage — totales (§5.5)", () => {
  it("suma sugerido/definido con montos string (definido null → sugerido)", async () => {
    renderPage();
    // sugerido: 1.000.000 + 2.000.000 = 3.000.000
    // definido: 1.000.000 (null → sugerido) + 1.500.000 = 2.500.000
    // diferencia: -500.000
    expect(await screen.findByText("Total sugerido")).toBeInTheDocument();
    expect(screen.getByText("$ 3.000.000,00")).toBeInTheDocument();
    expect(screen.getByText("$ 2.500.000,00")).toBeInTheDocument();
    expect(screen.getByText("-$ 500.000,00")).toBeInTheDocument();
  });
});
