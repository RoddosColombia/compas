// frontend/src/pages/CajaPage.test.tsx
//
// C4 pantalla de caja: muestra los saldos por banco del mes en ejecución, el
// formulario de reporte solo con caja:reportar (regla 9), y es solo-lectura sin la
// capacidad. El "¿cuadra?" y los cálculos vienen del backend.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Mes } from "@/lib/meses";
import CajaPage from "@/pages/CajaPage";

const editarMock = vi.hoisted(() => vi.fn());

const MESES: { items: Mes[] } = {
  items: [
    {
      id: "m1",
      mes: "2026-07-01",
      estado: "en_ejecucion",
      saldo_inicial_caja: "0.00",
      saldos_banco: [
        { banco: "global66", saldo: "1000000.00", fecha_reporte: "2026-07-15" },
      ],
      ingresos_esperados_semana: null,
    },
    {
      id: "m0",
      mes: "2026-06-01",
      estado: "cerrado",
      saldo_inicial_caja: "0.00",
      saldos_banco: [],
      ingresos_esperados_semana: null,
    },
  ],
};

const puedeMock = vi.fn();

vi.mock("@/auth/AuthContext", () => ({
  useAuth: () => ({ puede: puedeMock, rol: "financiero" }),
}));

vi.mock("@/lib/meses", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/meses")>();
  return { ...real, listarMeses: () => Promise.resolve(MESES) };
});

vi.mock("@/lib/caja", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/caja")>();
  return { ...real, editarSaldoInicial: editarMock };
});

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <CajaPage />
    </QueryClientProvider>,
  );
}

describe("CajaPage", () => {
  it("muestra los saldos del mes en ejecución y el formulario con caja:reportar", async () => {
    puedeMock.mockImplementation(() => true);
    renderPage();
    // saldo reportado del mes en ejecución (formato COP es-CO)
    expect(await screen.findByText("$ 1.000.000,00")).toBeInTheDocument();
    // "Global66" sale en la fila de saldos Y como <option> del formulario
    expect(screen.getAllByText("Global66").length).toBeGreaterThan(0);
    // formulario de reporte visible con la capacidad
    expect(screen.getByText("Reportar saldo")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Reportar" }),
    ).toBeInTheDocument();
  });

  it("sin caja:reportar es solo-lectura (regla 9)", async () => {
    puedeMock.mockImplementation(() => false);
    renderPage();
    // los saldos se ven (dashboard), pero el formulario de reporte no
    expect(await screen.findByText("Global66")).toBeInTheDocument();
    expect(screen.queryByText("Reportar saldo")).toBeNull();
    expect(screen.queryByRole("button", { name: "Reportar" })).toBeNull();
  });
});

describe("CajaPage — FIX-F: editar saldo inicial (ciclo:config)", () => {
  beforeEach(() => editarMock.mockReset());

  it("admin abre el diálogo y guarda con mes/saldo/motivo", async () => {
    puedeMock.mockImplementation(() => true);
    editarMock.mockResolvedValue({
      mes: "2026-07-01",
      estado: "en_ejecucion",
      saldo_inicial_caja: "5000000.00",
    });
    renderPage();
    fireEvent.click(
      await screen.findByRole("button", { name: "Editar saldo inicial" }),
    );
    const dialogo = await screen.findByRole("dialog", {
      name: "Editar saldo inicial",
    });
    fireEvent.change(within(dialogo).getByLabelText(/nuevo saldo/i), {
      target: { value: "5000000" },
    });
    fireEvent.change(within(dialogo).getByLabelText("Motivo"), {
      target: { value: "corrección de apertura" },
    });
    fireEvent.click(within(dialogo).getByRole("button", { name: "Guardar" }));
    expect(await screen.findByText(/actualizado a/i)).toBeInTheDocument();
    expect(editarMock).toHaveBeenCalledWith(
      "2026-07",
      "5000000",
      "corrección de apertura",
    );
  });

  it("valida saldo y motivo antes de llamar al backend", async () => {
    puedeMock.mockImplementation(() => true);
    renderPage();
    fireEvent.click(
      await screen.findByRole("button", { name: "Editar saldo inicial" }),
    );
    const dialogo = await screen.findByRole("dialog", {
      name: "Editar saldo inicial",
    });
    // saldo válido pero motivo vacío → no se llama
    fireEvent.change(within(dialogo).getByLabelText(/nuevo saldo/i), {
      target: { value: "5000000" },
    });
    fireEvent.click(within(dialogo).getByRole("button", { name: "Guardar" }));
    expect(editarMock).not.toHaveBeenCalled();
    expect(
      within(dialogo).getByText(/motivo es obligatorio/i),
    ).toBeInTheDocument();
  });

  it("sin ciclo:config no muestra el botón (regla 9)", async () => {
    puedeMock.mockImplementation((cap: string) => cap !== "ciclo:config");
    renderPage();
    // caja:reportar sigue activo → el form de reporte carga (ancla única)
    expect(await screen.findByText("Reportar saldo")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Editar saldo inicial" }),
    ).toBeNull();
  });
});
