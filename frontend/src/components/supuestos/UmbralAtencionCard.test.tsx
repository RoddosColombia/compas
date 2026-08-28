// RF-F3 · P1 — UmbralAtencionCard: muestra crítico + atención vigente y guarda una
// nueva vigencia; los invalida en cascada (proyeccion/valles).

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { UmbralAtencionCard } from "@/components/supuestos/UmbralAtencionCard";

const mocks = vi.hoisted(() => ({
  obtenerUmbralAtencion: vi.fn(),
  escribirUmbralAtencion: vi.fn(),
}));

vi.mock("@/lib/configuracion", () => ({
  obtenerUmbralAtencion: mocks.obtenerUmbralAtencion,
  escribirUmbralAtencion: mocks.escribirUmbralAtencion,
}));

function renderCard(puedeGestionar = true) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return {
    qc,
    ...render(
      <QueryClientProvider client={qc}>
        <UmbralAtencionCard puedeGestionar={puedeGestionar} />
      </QueryClientProvider>,
    ),
  };
}

describe("UmbralAtencionCard", () => {
  it("muestra crítico y atención vigente", async () => {
    mocks.obtenerUmbralAtencion.mockResolvedValue({
      critico: "30000000",
      atencion: "90000000",
    });
    renderCard();
    expect(await screen.findByText(/Crítico \(mínimo\)/i)).toBeInTheDocument();
    expect(await screen.findByText(/Atención vigente/i)).toBeInTheDocument();
    // formatCOP produce "$ 30.000.000,00"
    expect(screen.getByText(/30\.000\.000/)).toBeInTheDocument();
    expect(screen.getByText(/90\.000\.000/)).toBeInTheDocument();
  });

  it("sin permiso no muestra el editor", async () => {
    mocks.obtenerUmbralAtencion.mockResolvedValue({
      critico: "30000000",
      atencion: "90000000",
    });
    renderCard(false);
    await screen.findByText(/Atención vigente/i);
    expect(screen.queryByRole("button", { name: /Guardar/i })).toBeNull();
  });

  it("con cambio, guarda y llama al backend con el nuevo valor", async () => {
    mocks.obtenerUmbralAtencion.mockResolvedValue({
      critico: "30000000",
      atencion: "90000000",
    });
    mocks.escribirUmbralAtencion.mockResolvedValue({
      critico: "30000000",
      atencion: "250000000",
      vigente_desde: "2026-08-28",
    });
    renderCard();
    const input = (await screen.findByLabelText(
      /Nuevo umbral de atención/i,
    )) as HTMLInputElement;
    // ya viene con el vigente pre-cargado
    expect(input.value).toBe("90000000");
    fireEvent.change(input, { target: { value: "250000000" } });
    fireEvent.click(screen.getByRole("button", { name: /Guardar/i }));
    await waitFor(() =>
      expect(mocks.escribirUmbralAtencion).toHaveBeenCalledWith("250000000"),
    );
  });
});
