// SaldoDisponibleBar — el saldo disponible en vivo, siempre visible.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { SaldoDisponibleBar } from "@/components/layout/SaldoDisponibleBar";
import type { SaldoDisponible } from "@/lib/caja";

const mocks = vi.hoisted(() => ({ obtenerSaldoDisponible: vi.fn() }));

vi.mock("@/lib/caja", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/caja")>();
  return { ...real, obtenerSaldoDisponible: mocks.obtenerSaldoDisponible };
});

function renderBar() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <SaldoDisponibleBar />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const BASE: SaldoDisponible = {
  disponible: true,
  mes: "2026-08",
  corte: "2026-08-27",
  saldo_en_banco: "691613865.20",
  transito_wava: "0.00",
  total: "691613865.20",
  por_banco: [
    {
      banco: "global66",
      saldo: "691613865.20",
      reportado: "665715578.00",
      ultimo_movimiento: "2026-08-24",
      dias_sin_registrar: 3,
    },
  ],
  sin_dato: [],
  frescura: { ultimo_movimiento: "2026-08-24", dias: 3, estado: "atrasado" },
};

describe("SaldoDisponibleBar", () => {
  it("muestra el total disponible como número grande", async () => {
    mocks.obtenerSaldoDisponible.mockResolvedValue(BASE);
    renderBar();
    expect(await screen.findByText("Disponible")).toBeInTheDocument();
    expect(
      screen.getByText((t) => t.replace(/\s/g, " ") === "$ 691.613.865,20"),
    ).toBeInTheDocument();
  });

  it("cuando va atrasado, lo dice en ámbar con los días", async () => {
    mocks.obtenerSaldoDisponible.mockResolvedValue(BASE);
    renderBar();
    const fresc = await screen.findByText(/sin registrar hace 3 días/i);
    expect(fresc).toBeInTheDocument();
    expect(fresc.className).toContain("text-atencion");
  });

  it("al día lo dice en verde", async () => {
    mocks.obtenerSaldoDisponible.mockResolvedValue({
      ...BASE,
      frescura: { ultimo_movimiento: "2026-08-27", dias: 0, estado: "al_dia" },
    });
    renderBar();
    const fresc = await screen.findByText(/al día/i);
    expect(fresc.className).toContain("text-positivo");
  });

  it("desglosa por banco y suma Wava cuando hay tránsito", async () => {
    mocks.obtenerSaldoDisponible.mockResolvedValue({
      ...BASE,
      transito_wava: "12000000.00",
      total: "703613865.20",
    });
    renderBar();
    expect(await screen.findByText(/Global66/)).toBeInTheDocument();
    expect(screen.getByText(/Wava/)).toBeInTheDocument();
  });

  it("avisa cuando falta reportar un banco (regla 7)", async () => {
    mocks.obtenerSaldoDisponible.mockResolvedValue({
      ...BASE,
      sin_dato: ["bbva"],
    });
    renderBar();
    expect(await screen.findByText(/falta reportar BBVA/i)).toBeInTheDocument();
  });

  it("sin mes en ejecución no se pinta (la guía la da MesStatusBar)", async () => {
    mocks.obtenerSaldoDisponible.mockResolvedValue({
      disponible: false,
      motivo: "sin_mes_en_ejecucion",
    });
    const { container } = renderBar();
    // deja que la query resuelva
    await Promise.resolve();
    expect(container.querySelector("a")).toBeNull();
  });
});
