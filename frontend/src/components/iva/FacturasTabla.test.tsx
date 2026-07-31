// Tabla de facturas (§4) — 3 estados de deducible, 3 ausencias distinguibles,
// filtros en cliente, y lote de deducibilidad con RESUMEN REAL (nunca "éxito" si
// hubo errores). Cero aritmética de dinero: los montos vienen del backend.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { FacturasTabla } from "@/components/iva/FacturasTabla";
import type { FacturaRow } from "@/lib/facturas";
import * as facturasLib from "@/lib/facturas";

function row(over: Partial<FacturaRow>): FacturaRow {
  return {
    id: "x",
    tipo: "compra",
    origen: "auteco",
    numero: "FC-1",
    tercero_nombre: "Auteco S.A.S.",
    tercero_nit: "860024781",
    tipo_contribuyente: "persona_juridica",
    fecha: "2026-05-28",
    base_gravable: null,
    total_bruto: "1000000.00",
    tarifa_iva: null,
    iva_valor: "190000.00",
    total: "1190000.00",
    deducible: false,
    deducible_decidido: false,
    activo: true,
    periodo: "2026-C2",
    ...over,
  };
}

function renderTabla(facturas: FacturaRow[], onCambio = vi.fn()) {
  const qc = new QueryClient();
  render(
    <QueryClientProvider client={qc}>
      <FacturasTabla facturas={facturas} onCambio={onCambio} />
    </QueryClientProvider>,
  );
  return { onCambio };
}

describe("FacturasTabla", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("distingue los 3 estados de deducible (Sí / No / Sin decidir)", () => {
    renderTabla([
      row({ id: "1", numero: "SI", deducible: true, deducible_decidido: true }),
      row({
        id: "2",
        numero: "NO",
        deducible: false,
        deducible_decidido: true,
      }),
      row({
        id: "3",
        numero: "PEND",
        deducible: false,
        deducible_decidido: false,
      }),
    ]);
    const si = screen.getByText("SI").closest("tr") as HTMLElement;
    const no = screen.getByText("NO").closest("tr") as HTMLElement;
    const pend = screen.getByText("PEND").closest("tr") as HTMLElement;
    expect(within(si).getByText("Sí")).toBeInTheDocument();
    expect(within(no).getByText("No")).toBeInTheDocument();
    expect(within(pend).getByText("Sin decidir")).toBeInTheDocument();
  });

  it("distingue las 3 ausencias: — (no existe), Reservado (PII), $ 0,00 (cero real)", () => {
    renderTabla([
      row({ id: "1", numero: "SINBRUTO", total_bruto: null }), // —
      row({
        id: "2",
        numero: "PII",
        tercero_nombre: null,
        tercero_nit: null,
        tipo_contribuyente: "persona_natural",
      }), // Reservado
      row({ id: "3", numero: "CERO", iva_valor: "0.00" }), // $ 0,00 real
    ]);
    const sinBruto = screen.getByText("SINBRUTO").closest("tr") as HTMLElement;
    const pii = screen.getByText("PII").closest("tr") as HTMLElement;
    const cero = screen.getByText("CERO").closest("tr") as HTMLElement;
    expect(within(sinBruto).getByText("—")).toBeInTheDocument();
    expect(within(pii).getByText("Reservado")).toBeInTheDocument();
    // el cero real NO se muestra como — ni Reservado
    expect(within(cero).queryByText("—")).not.toBeInTheDocument();
    expect(within(cero).queryByText("Reservado")).not.toBeInTheDocument();
  });

  it("filtra por tipo en el cliente (oculta emitidas)", () => {
    renderTabla([
      row({ id: "1", numero: "COMPRA-1", tipo: "compra" }),
      row({ id: "2", numero: "VENTA-1", tipo: "venta", origen: "moto" }),
    ]);
    expect(screen.getByText("VENTA-1")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Tipo"), {
      target: { value: "compra" },
    });
    expect(screen.queryByText("VENTA-1")).not.toBeInTheDocument();
    expect(screen.getByText("COMPRA-1")).toBeInTheDocument();
  });

  it("lote: marca deducibles y refresca la liquidación completa", async () => {
    const spy = vi
      .spyOn(facturasLib, "marcarDeducibilidadLote")
      .mockResolvedValue({
        resultados: [{ id: "1", estado: "actualizada" }],
        resumen: { actualizadas: 1, sin_cambio: 0, errores: 0 },
      });
    const { onCambio } = renderTabla([
      row({ id: "1", numero: "C-1", deducible_decidido: false }),
    ]);
    // seleccionar la compra
    fireEvent.click(screen.getByRole("checkbox", { name: /C-1/ }));
    fireEvent.click(
      screen.getByRole("button", { name: /marcar como deducibles/i }),
    );
    // confirmación
    fireEvent.click(screen.getByRole("button", { name: /^confirmar/i }));
    await screen.findByText(/1 marcada/i);
    expect(spy).toHaveBeenCalledWith(["1"], true);
    expect(onCambio).toHaveBeenCalled();
  });

  it("lote: con errores muestra el resumen REAL, no éxito", async () => {
    vi.spyOn(facturasLib, "marcarDeducibilidadLote").mockResolvedValue({
      resultados: [
        { id: "1", estado: "actualizada" },
        { id: "2", estado: "error", motivo: "la factura no existe" },
      ],
      resumen: { actualizadas: 1, sin_cambio: 0, errores: 1 },
    });
    renderTabla([
      row({ id: "1", numero: "C-1", deducible_decidido: false }),
      row({
        id: "2",
        numero: "C-2",
        deducible_decidido: false,
        tercero_nit: "900",
      }),
    ]);
    fireEvent.click(
      screen.getByRole("checkbox", { name: /seleccionar todas/i }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: /marcar como deducibles/i }),
    );
    fireEvent.click(screen.getByRole("button", { name: /^confirmar/i }));
    // resumen honesto: cuenta marcadas Y errores, con el motivo
    expect(await screen.findByText(/1 marcada/i)).toBeInTheDocument();
    expect(screen.getByText(/1 con error/i)).toBeInTheDocument();
    expect(screen.getByText(/la factura no existe/i)).toBeInTheDocument();
  });
});
