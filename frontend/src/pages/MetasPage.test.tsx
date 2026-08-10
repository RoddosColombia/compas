// MetasPage (UI metas de ingreso): bloque del mes actual (meta · real · % · barra),
// acumulado del año (tabla por mes + totales) y CRUD gated por proyeccion:gestionar.
// El % lo calcula el backend; montos string (regla 1). El "mes actual" es el mes
// calendario (tiempo fijado en los tests).

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Meta } from "@/lib/metas";
import MetasPage from "@/pages/MetasPage";

const mocks = vi.hoisted(() => ({
  listarMetas: vi.fn(),
  crearMeta: vi.fn(),
  editarMeta: vi.fn(),
  eliminarMeta: vi.fn(),
  caps: { actual: [] as string[] },
}));

vi.mock("@/auth/AuthContext", () => ({
  useAuth: () => ({
    rol: "financiero",
    puede: (cap: string) => mocks.caps.actual.includes(cap),
  }),
}));

vi.mock("@/lib/metas", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/metas")>();
  return {
    ...real,
    listarMetas: mocks.listarMetas,
    crearMeta: mocks.crearMeta,
    editarMeta: mocks.editarMeta,
    eliminarMeta: mocks.eliminarMeta,
  };
});

function meta(over: Partial<Meta> = {}): Meta {
  return {
    id: "g1",
    mes: "2026-08",
    valor: "100000000.00",
    lineas: [],
    real_ejecutado: "25000000.00",
    pct_cumplimiento: "25.0",
    real_inicial: null,
    real_semanal: null,
    activo: true,
    ...over,
  };
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/metas"]}>
        <MetasPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers({ toFake: ["Date"] }); // solo Date: no romper el polling de findBy
  vi.setSystemTime(new Date("2026-08-10T12:00:00"));
  mocks.caps.actual = ["dashboard:leer", "proyeccion:gestionar"];
});

afterEach(() => {
  vi.useRealTimers();
});

describe("MetasPage — bloque del mes actual", () => {
  it("con meta: muestra meta, real, % y barra de progreso", async () => {
    mocks.listarMetas.mockResolvedValue({ items: [meta()] });
    renderPage();
    expect(await screen.findByText("Metas de ingreso")).toBeInTheDocument();
    const bloque = within(await screen.findByTestId("mes-actual"));
    // meta y real formateados
    expect(bloque.getByText(/100\.000\.000/)).toBeInTheDocument();
    expect(bloque.getByText(/25\.000\.000/)).toBeInTheDocument();
    // % de cumplimiento + barra
    expect(bloque.getByText(/25(,0)?\s*%/)).toBeInTheDocument();
    const barra = bloque.getByRole("progressbar");
    expect(barra).toHaveAttribute("aria-valuenow", "25");
  });

  it("sin meta del mes en curso: estado honesto, nunca un $0 falso", async () => {
    mocks.listarMetas.mockResolvedValue({ items: [] });
    renderPage();
    expect(await screen.findByText(/sin meta definida/i)).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).toBeNull();
  });
});

describe("MetasPage — acumulado del año", () => {
  it("suma bien meta y real de todos los meses", async () => {
    mocks.listarMetas.mockResolvedValue({
      items: [
        meta({
          id: "j",
          mes: "2026-07",
          valor: "10000000.00",
          real_ejecutado: "8000000.00",
          pct_cumplimiento: "80.0",
        }),
        meta({
          id: "a",
          mes: "2026-08",
          valor: "20000000.00",
          real_ejecutado: "5000000.00",
          pct_cumplimiento: "25.0",
        }),
      ],
    });
    renderPage();
    const totales = await screen.findByTestId("acumulado-totales");
    // Σ meta = 30.000.000 · Σ real = 13.000.000
    expect(within(totales).getByText(/30\.000\.000/)).toBeInTheDocument();
    expect(within(totales).getByText(/13\.000\.000/)).toBeInTheDocument();
  });
});

describe("MetasPage — CRUD (proyeccion:gestionar)", () => {
  it("PTS6-E: crea con 2 líneas; el total es la suma y valida antes del backend", async () => {
    mocks.listarMetas.mockResolvedValue({ items: [] });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /nueva meta/i }));
    const dialogo = await screen.findByRole("dialog");
    fireEvent.change(within(dialogo).getByLabelText(/mes/i), {
      target: { value: "2026-09" },
    });
    // una línea inválida → no se llama
    fireEvent.change(within(dialogo).getByLabelText("Cuota inicial"), {
      target: { value: "abc" },
    });
    fireEvent.change(within(dialogo).getByLabelText("Cuotas semanales"), {
      target: { value: "200000000" },
    });
    fireEvent.click(within(dialogo).getByRole("button", { name: /guardar/i }));
    expect(mocks.crearMeta).not.toHaveBeenCalled();
    expect(within(dialogo).getByText(/números válidos/i)).toBeInTheDocument();
    // ahora ambas válidas → total = 60M + 200M = 260M; se envía con lineas
    mocks.crearMeta.mockResolvedValue(meta({ mes: "2026-09" }));
    fireEvent.change(within(dialogo).getByLabelText("Cuota inicial"), {
      target: { value: "60000000" },
    });
    // el total se muestra en vivo
    expect(within(dialogo).getByTestId("meta-total").textContent).toMatch(
      /260\.000\.000/,
    );
    fireEvent.click(within(dialogo).getByRole("button", { name: /guardar/i }));
    expect(mocks.crearMeta).toHaveBeenCalledWith(
      expect.objectContaining({
        mes: "2026-09",
        valor: "260000000",
        lineas: [
          { nombre: "Cuota inicial", valor: "60000000" },
          { nombre: "Cuotas semanales", valor: "200000000" },
        ],
      }),
    );
  });

  it("editar precarga las 2 líneas de la meta", async () => {
    mocks.listarMetas.mockResolvedValue({
      items: [
        meta({
          lineas: [
            { nombre: "Cuota inicial", valor: "40000000.00" },
            { nombre: "Cuotas semanales", valor: "60000000.00" },
          ],
        }),
      ],
    });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /editar/i }));
    const dialogo = await screen.findByRole("dialog");
    expect(within(dialogo).getByLabelText("Cuota inicial")).toHaveValue(
      "40000000.00",
    );
    expect(within(dialogo).getByLabelText("Cuotas semanales")).toHaveValue(
      "60000000.00",
    );
  });

  it("PTS6-E: el bloque del mes muestra el desglose inicial vs semanal (meta y real)", async () => {
    mocks.listarMetas.mockResolvedValue({
      items: [
        meta({
          lineas: [
            { nombre: "Cuota inicial", valor: "60000000.00" },
            { nombre: "Cuotas semanales", valor: "200000000.00" },
          ],
          real_inicial: "12000000.00",
          real_semanal: "58000000.00",
        }),
      ],
    });
    renderPage();
    const bloque = within(await screen.findByTestId("mes-actual"));
    expect(bloque.getByText(/Desglose/i)).toBeInTheDocument();
    expect(bloque.getByText(/60\.000\.000/)).toBeInTheDocument(); // meta inicial
    expect(bloque.getByText(/12\.000\.000/)).toBeInTheDocument(); // real inicial
    expect(bloque.getByText(/58\.000\.000/)).toBeInTheDocument(); // real semanal
  });

  it("oculta el CRUD a roles sin proyeccion:gestionar", async () => {
    mocks.caps.actual = ["dashboard:leer"];
    mocks.listarMetas.mockResolvedValue({ items: [meta()] });
    renderPage();
    expect(await screen.findByText("Metas de ingreso")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /nueva meta/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /editar/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /eliminar/i })).toBeNull();
  });
});
