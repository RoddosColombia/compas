// MesStatusBar (C2 §7.1): con mes en ejecución muestra mes + estado + % consumido
// (montos string → % con decimal.js) + caja de hoy; sin mes muestra el paso
// pendiente con link. (No aparece en /login por arquitectura: la barra vive en
// AppShell y /login no monta el AppShell — asserted en App.test.tsx.)

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MesStatusBar } from "@/components/layout/MesStatusBar";
import type { Mes } from "@/lib/meses";

const mocks = vi.hoisted(() => ({
  listarMeses: vi.fn(),
  vistaControl: vi.fn(),
}));

vi.mock("@/lib/meses", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/meses")>();
  return { ...real, listarMeses: mocks.listarMeses };
});

vi.mock("@/lib/control", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/control")>();
  return { ...real, vistaControl: mocks.vistaControl };
});

function hoyLocal(): string {
  const d = new Date();
  const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}

function mes(estado: Mes["estado"], fechaReporte?: string): Mes {
  return {
    id: "m1",
    mes: "2026-08-01",
    estado,
    saldo_inicial_caja: "0.00",
    saldos_banco: fechaReporte
      ? [
          {
            banco: "global66",
            saldo: "1000000.00",
            fecha_reporte: fechaReporte,
          },
        ]
      : [],
    ingresos_esperados_semana: null,
  };
}

function renderBar() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <MesStatusBar />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.vistaControl.mockResolvedValue({
    mes: "2026-08",
    estado: "en_ejecucion",
    grupos: [],
    total: {
      definido: "1000000.00",
      ejecutado: "680000.00",
      disponible: "320000.00",
    },
    caja_disponible: "0.00",
    sin_presupuesto: [],
  });
});

describe("MesStatusBar", () => {
  it("con mes en ejecución: mes + estado + % consumido + caja de hoy ✓", async () => {
    mocks.listarMeses.mockResolvedValue({
      items: [mes("en_ejecucion", hoyLocal())],
    });
    renderBar();
    expect(await screen.findByText("Agosto 2026")).toBeInTheDocument();
    expect(screen.getByText("En ejecución")).toBeInTheDocument();
    // 680000/1000000 = 68 % (calculado con decimal.js sobre strings)
    expect(await screen.findByText(/68 %/)).toBeInTheDocument();
    expect(screen.getByText(/caja reportada hoy/)).toBeInTheDocument();
    // toda la barra enlaza a la Cabina
    expect(screen.getByRole("link", { name: /Agosto 2026/ })).toHaveAttribute(
      "href",
      "/mes",
    );
  });

  it("caja sin reportar hoy cuando el último reporte es viejo", async () => {
    mocks.listarMeses.mockResolvedValue({
      items: [mes("en_ejecucion", "2026-07-01")],
    });
    renderBar();
    expect(
      await screen.findByText(/caja sin reportar hoy/),
    ).toBeInTheDocument();
  });

  it("sin mes en ejecución: muestra el paso pendiente con link", async () => {
    mocks.listarMeses.mockResolvedValue({ items: [mes("propuesto")] });
    renderBar();
    expect(await screen.findByText("Sin mes en ejecución")).toBeInTheDocument();
    const link = screen.getByRole("link", {
      name: /Aprueba el presupuesto de 2026-08/,
    });
    expect(link).toHaveAttribute("href", "/meses/2026-08/presupuesto");
    expect(mocks.vistaControl).not.toHaveBeenCalled();
  });

  it("sin meses: invita a abrir el primero", async () => {
    mocks.listarMeses.mockResolvedValue({ items: [] });
    renderBar();
    expect(
      await screen.findByRole("link", { name: /Abre un mes/ }),
    ).toBeInTheDocument();
  });
});
