// ReporteCajaCard.test.tsx — RF-IVA-TES · Task 5 ("la cerca"): la tarjeta
// pinta el disponible EN VIVO (bruto) y, cuando hay reserva de IVA, la línea
// "de eso, $X apartado para IVA → disponible real $Y" (GET /caja/disponible,
// Task 4). Con reserva_iva="0" la línea se OCULTA. Nunca Number()/parseFloat()
// sobre los montos — se pintan con formatCOP (decimal.js-light + Intl es-CO).

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ReporteCajaCard } from "@/components/caja/ReporteCajaCard";
import type { DisponibleTesoreria } from "@/lib/caja";
import type { Mes } from "@/lib/meses";

const mocks = vi.hoisted(() => ({
  obtenerDisponible: vi.fn(),
  puede: vi.fn(() => false),
}));

vi.mock("@/auth/AuthContext", () => ({
  useAuth: () => ({ puede: mocks.puede }),
}));

vi.mock("@/lib/caja", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/caja")>();
  return { ...real, obtenerDisponible: mocks.obtenerDisponible };
});

const MES: Mes = {
  id: "m1",
  mes: "2026-08-01",
  estado: "en_ejecucion",
  saldo_inicial_caja: "0.00",
  saldos_banco: [],
  ingresos_esperados_semana: null,
};

function disponible(over: Partial<DisponibleTesoreria> = {}): DisponibleTesoreria {
  return {
    bruto: "15000000.00",
    reserva_iva: "3000000.00",
    neto: "12000000.00",
    fecha_corte: null,
    sin_dato: [],
    ...over,
  };
}

function renderCard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ReporteCajaCard mes={MES} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ReporteCajaCard — disponible en vivo (Task 5)", () => {
  it("pinta el bruto y la línea de neto-de-IVA cuando hay reserva", async () => {
    mocks.obtenerDisponible.mockResolvedValue(disponible());
    renderCard();

    expect(await screen.findByText("$ 15.000.000,00")).toBeInTheDocument();
    expect(
      await screen.findByText(/de eso, \$ 3\.000\.000,00 apartado para IVA/),
    ).toBeInTheDocument();
    expect(screen.getByText("$ 12.000.000,00")).toBeInTheDocument();
  });

  it("oculta la línea de IVA cuando reserva_iva es 0 (sin fondo)", async () => {
    mocks.obtenerDisponible.mockResolvedValue(
      disponible({ reserva_iva: "0", neto: "15000000.00" }),
    );
    renderCard();

    expect(await screen.findByText("$ 15.000.000,00")).toBeInTheDocument();
    expect(screen.queryByText(/apartado para IVA/)).toBeNull();
  });

  it("oculta la línea de IVA cuando reserva_iva es 0.00", async () => {
    mocks.obtenerDisponible.mockResolvedValue(
      disponible({ reserva_iva: "0.00", neto: "15000000.00" }),
    );
    renderCard();

    expect(await screen.findByText("$ 15.000.000,00")).toBeInTheDocument();
    expect(screen.queryByText(/apartado para IVA/)).toBeNull();
  });

  it("no rompe la tarjeta si el fetch del disponible falla", async () => {
    mocks.obtenerDisponible.mockRejectedValue(new Error("network"));
    renderCard();

    // El resto de la tarjeta (tabla de bancos) sigue montando sin el bloque.
    expect(await screen.findByText("Bancolombia")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByText(/Disponible hoy/)).toBeNull();
    });
  });
});
