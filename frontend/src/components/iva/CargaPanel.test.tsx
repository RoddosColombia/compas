// CargaPanel — C2': el mismo panel de carga acepta el Excel de «documentos
// recibidos» del portal DIAN (masivo, un archivo → cientos de filas) junto a
// los PDF. El resultado por fila pinta el MOTIVO del backend (sin jerga).

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CargaPanel } from "@/components/iva/CargaPanel";

const mocks = vi.hoisted(() => ({
  cargarFacturas: vi.fn(),
  cargarFacturasExcel: vi.fn(),
}));

vi.mock("@/lib/facturas", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/facturas")>();
  return {
    ...real,
    cargarFacturas: mocks.cargarFacturas,
    cargarFacturasExcel: mocks.cargarFacturasExcel,
  };
});

beforeEach(() => {
  vi.clearAllMocks();
});

function renderPanel() {
  return render(
    <CargaPanel
      onCerrar={() => {}}
      onCargado={() => {}}
      onRevisar={() => {}}
    />,
  );
}

describe("CargaPanel — C2' import Excel DIAN", () => {
  it("la zona de carga anuncia el Excel de documentos recibidos", () => {
    renderPanel();
    expect(
      screen.getByText(/Excel de «documentos recibidos»/),
    ).toBeInTheDocument();
  });

  it("un .xlsx va al endpoint masivo y pinta los motivos por fila", async () => {
    mocks.cargarFacturasExcel.mockResolvedValue({
      resultados: [
        {
          archivo: "fila 2 · FE1001",
          estado: "creada",
          motivo: null,
          factura_id: "f1",
          datos_extraidos: null,
        },
        {
          archivo: "fila 3 · FE1002",
          estado: "rechazada_tipo_no_soportado",
          motivo:
            "es una factura EMITIDA por RODDOS; este importador es solo de recibidas (gasto).",
          factura_id: null,
          datos_extraidos: null,
        },
      ],
      resumen: { creadas: 1, rechazadas_tipo_no_soportado: 1 },
    });
    const { container } = renderPanel();
    const input = container.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    const excel = new File(["x"], "FACTURACION DIAN.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    fireEvent.change(input, { target: { files: [excel] } });

    await waitFor(() =>
      expect(mocks.cargarFacturasExcel).toHaveBeenCalledTimes(1),
    );
    expect(mocks.cargarFacturas).not.toHaveBeenCalled();
    expect(await screen.findByText("1 factura cargada")).toBeInTheDocument();
    // el motivo del BACKEND manda (no el texto fijo de los PDF)
    expect(screen.getByText(/EMITIDA por RODDOS/)).toBeInTheDocument();
  });

  it("un .pdf sigue yendo al endpoint por documento", async () => {
    mocks.cargarFacturas.mockResolvedValue({
      resultados: [
        {
          archivo: "factura.pdf",
          estado: "creada",
          motivo: null,
          factura_id: "f1",
          datos_extraidos: null,
        },
      ],
      resumen: { creadas: 1 },
    });
    const { container } = renderPanel();
    const input = container.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    fireEvent.change(input, {
      target: {
        files: [new File(["x"], "factura.pdf", { type: "application/pdf" })],
      },
    });
    await waitFor(() => expect(mocks.cargarFacturas).toHaveBeenCalledTimes(1));
    expect(mocks.cargarFacturasExcel).not.toHaveBeenCalled();
  });
});
