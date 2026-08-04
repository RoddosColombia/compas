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
  it("crear valida monto y mes ANTES de llamar al backend", async () => {
    mocks.listarMetas.mockResolvedValue({ items: [] });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /nueva meta/i }));
    const dialogo = await screen.findByRole("dialog");
    // monto inválido → no se llama
    fireEvent.change(within(dialogo).getByLabelText(/mes/i), {
      target: { value: "2026-09" },
    });
    fireEvent.change(within(dialogo).getByLabelText(/monto/i), {
      target: { value: "abc" },
    });
    fireEvent.click(within(dialogo).getByRole("button", { name: /guardar/i }));
    expect(mocks.crearMeta).not.toHaveBeenCalled();
    expect(within(dialogo).getByText(/número positivo/i)).toBeInTheDocument();
    // ahora válido → sí se llama con mes + valor
    mocks.crearMeta.mockResolvedValue(meta({ mes: "2026-09" }));
    fireEvent.change(within(dialogo).getByLabelText(/monto/i), {
      target: { value: "50000000" },
    });
    fireEvent.click(within(dialogo).getByRole("button", { name: /guardar/i }));
    expect(mocks.crearMeta).toHaveBeenCalledWith(
      expect.objectContaining({ mes: "2026-09", valor: "50000000" }),
    );
  });

  it("editar abre el formulario con el valor actual", async () => {
    mocks.listarMetas.mockResolvedValue({ items: [meta()] });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /editar/i }));
    const dialogo = await screen.findByRole("dialog");
    expect(within(dialogo).getByLabelText(/monto/i)).toHaveValue(
      "100000000.00",
    );
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
