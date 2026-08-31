// FabsPanel — carga el scrollback al montar y pinta las burbujas; enviar una
// pregunta la pinta optimista y luego la respuesta con el pie de evidencia.
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { FabsPanel } from "@/components/fabs/FabsPanel";

const mocks = vi.hoisted(() => ({
  historialFabs: vi.fn(),
  preguntarFabs: vi.fn(),
}));

vi.mock("@/lib/fabs", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/fabs")>();
  return { ...real, historialFabs: mocks.historialFabs, preguntarFabs: mocks.preguntarFabs };
});

describe("FabsPanel", () => {
  it("carga el historial al montar y pinta las burbujas", async () => {
    mocks.historialFabs.mockResolvedValue([
      { rol: "user", texto: "hola", canal: "telegram", ts: null },
      { rol: "assistant", texto: "$5.000.000 hoy", canal: "telegram", ts: null },
    ]);
    render(<FabsPanel onCerrar={() => {}} />);
    expect(await screen.findByText("hola")).toBeInTheDocument();
    expect(screen.getByText("$5.000.000 hoy")).toBeInTheDocument();
  });

  it("enviar pinta la pregunta y luego la respuesta con evidencia", async () => {
    mocks.historialFabs.mockResolvedValue([]);
    mocks.preguntarFabs.mockResolvedValue({
      texto: "La caja es $5.000.000",
      abstuvo: false,
      cifras: [{ valor: "5.000.000", unidad: "COP", evidencia: { fuente: "caja.py", ref: "2026-08" } }],
    });
    render(<FabsPanel onCerrar={() => {}} />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "cuánta caja?" } });
    fireEvent.submit(screen.getByRole("textbox").closest("form")!);
    expect(await screen.findByText("cuánta caja?")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("La caja es $5.000.000")).toBeInTheDocument());
    expect(screen.getByText(/caja\.py/)).toBeInTheDocument(); // pie de evidencia
  });
});
