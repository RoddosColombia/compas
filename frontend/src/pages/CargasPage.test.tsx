// CargasPage — panel "Movimientos manuales del mes" (FIX-G2): lista los manuales con
// estado (Activa / Anulada / Contra-asiento), botón Anular solo en activas gated por
// cargas:gestionar, diálogo con motivo obligatorio. El original anulado y su reverso
// quedan ambos visibles enlazados. Montos string (regla 1).

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { TransaccionMovimiento } from "@/lib/cargas";
import CargasPage from "@/pages/CargasPage";

const mocks = vi.hoisted(() => ({
  listarCargas: vi.fn(),
  listarManuales: vi.fn(),
  anular: vi.fn(),
  caps: { actual: [] as string[] },
}));

vi.mock("@/auth/AuthContext", () => ({
  useAuth: () => ({
    rol: "financiero",
    puede: (cap: string) => mocks.caps.actual.includes(cap),
  }),
}));

vi.mock("@/lib/cargas", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/cargas")>();
  return {
    ...real,
    listarCargas: mocks.listarCargas,
    listarTransaccionesManuales: mocks.listarManuales,
    anularTransaccion: mocks.anular,
  };
});

function mov(over: Partial<TransaccionMovimiento> = {}): TransaccionMovimiento {
  return {
    id: "t1",
    fecha: "2026-08-10",
    descripcion: "EGRESO EFECTIVO CAJA",
    valor: "50000.00",
    tipo_flujo: "egreso",
    rubro_id: "r1",
    banco: "manual",
    id_banco: "MAN-abc",
    revierte_id: null,
    anulada: false,
    es_reverso: false,
    ...over,
  };
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/cargas"]}>
        <CargasPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-08-15T12:00:00"));
  mocks.caps.actual = ["dashboard:leer", "cargas:gestionar"];
  mocks.listarCargas.mockResolvedValue({ items: [] });
});

afterEach(() => {
  vi.useRealTimers();
});

describe("CargasPage — panel de movimientos manuales (FIX-G2)", () => {
  it("lista el original anulado y su reverso, enlazados", async () => {
    mocks.listarManuales.mockResolvedValue({
      items: [
        mov({ id: "t1", anulada: true }),
        mov({
          id: "t2",
          descripcion: "Anulación de «EGRESO EFECTIVO CAJA»: error",
          tipo_flujo: "ingreso",
          revierte_id: "t1",
          es_reverso: true,
        }),
      ],
    });
    renderPage();
    const f1 = within(await screen.findByTestId("mov-t1"));
    expect(f1.getByText("Anulada")).toBeInTheDocument();
    const f2 = within(await screen.findByTestId("mov-t2"));
    expect(f2.getByText("Reverso")).toBeInTheDocument();
    // el reverso enlaza al original (nº de fila)
    expect(f2.getByText(/reversa de #1/)).toBeInTheDocument();
    // no se ofrece anular ni el anulado ni el reverso
    expect(screen.queryByRole("button", { name: /^anular$/i })).toBeNull();
  });

  it("anular una activa exige motivo y llama al backend con él", async () => {
    mocks.listarManuales.mockResolvedValue({ items: [mov({ id: "t1" })] });
    mocks.anular.mockResolvedValue(mov({ id: "t2", es_reverso: true }));
    renderPage();
    const fila = within(await screen.findByTestId("mov-t1"));
    fireEvent.click(fila.getByRole("button", { name: /anular/i }));
    const dialogo = await screen.findByText(/se registra un/i);
    const scope = within(dialogo.closest("div") as HTMLElement);
    // sin motivo → no llama
    fireEvent.click(scope.getByRole("button", { name: /^anular$/i }));
    expect(mocks.anular).not.toHaveBeenCalled();
    expect(scope.getByText(/motivo.*obligatorio/i)).toBeInTheDocument();
    // con motivo → llama con (id, motivo)
    fireEvent.change(scope.getByLabelText(/motivo/i), {
      target: { value: "digitación errada" },
    });
    fireEvent.click(scope.getByRole("button", { name: /^anular$/i }));
    expect(mocks.anular).toHaveBeenCalledWith("t1", "digitación errada");
  });

  it("oculta el botón Anular a roles sin cargas:gestionar", async () => {
    mocks.caps.actual = ["dashboard:leer"];
    mocks.listarManuales.mockResolvedValue({ items: [mov({ id: "t1" })] });
    renderPage();
    expect(await screen.findByTestId("mov-t1")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /anular/i })).toBeNull();
  });
});
