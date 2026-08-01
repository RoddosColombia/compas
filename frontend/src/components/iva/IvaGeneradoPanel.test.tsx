// Pieza 2 (ENTREGA 3) — panel "Registrar IVA generado del mes". El CEO registra, el
// mes vencido, mes + valor del IVA; el backend arma la venta VENTAS-YYYY-MM. Cero
// aritmética de dinero en el front: el valor viaja como string canónico.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { IvaGeneradoPanel } from "@/components/iva/IvaGeneradoPanel";
import { registrarIvaGenerado } from "@/lib/facturas";

vi.mock("@/lib/facturas", () => ({
  registrarIvaGenerado: vi.fn(),
}));

const mockRegistrar = vi.mocked(registrarIvaGenerado);

function renderPanel() {
  const onCerrar = vi.fn();
  const onRegistrado = vi.fn();
  render(<IvaGeneradoPanel onCerrar={onCerrar} onRegistrado={onRegistrado} />);
  return { onCerrar, onRegistrado };
}

describe("IvaGeneradoPanel", () => {
  beforeEach(() => {
    mockRegistrar.mockReset();
  });

  it("no registra hasta que haya mes y un valor válido", () => {
    renderPanel();
    const boton = screen.getByRole("button", { name: /^Registrar$/ });
    expect(boton).toBeDisabled();
  });

  it("registra con el valor CANÓNICO (sin separadores) y avisa al padre", async () => {
    mockRegistrar.mockResolvedValue({} as never);
    const { onRegistrado } = renderPanel();

    fireEvent.change(screen.getByLabelText(/Mes/i), {
      target: { value: "2026-07" },
    });
    fireEvent.change(screen.getByLabelText(/Valor del IVA/i), {
      target: { value: "8.000.000" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^Registrar$/ }));

    await waitFor(() =>
      expect(mockRegistrar).toHaveBeenCalledWith("2026-07", "8000000"),
    );
    await waitFor(() => expect(onRegistrado).toHaveBeenCalled());
  });

  it("muestra el error del backend y NO avisa al padre si falla (p. ej. duplicado)", async () => {
    mockRegistrar.mockRejectedValue(new Error("ya existe la factura"));
    const { onRegistrado } = renderPanel();

    fireEvent.change(screen.getByLabelText(/Mes/i), {
      target: { value: "2026-07" },
    });
    fireEvent.change(screen.getByLabelText(/Valor del IVA/i), {
      target: { value: "8000000" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^Registrar$/ }));

    await waitFor(() =>
      expect(screen.getByText(/ya existe la factura/i)).toBeInTheDocument(),
    );
    expect(onRegistrado).not.toHaveBeenCalled();
  });
});
