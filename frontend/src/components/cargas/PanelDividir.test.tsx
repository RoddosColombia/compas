// components/cargas/PanelDividir.test.tsx — PTS6-B/D-UI
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PanelDividir } from "@/components/cargas/PanelDividir";
import type { TransaccionMovimiento } from "@/lib/cargas";
import type { Rubro } from "@/lib/rubros";

const mocks = vi.hoisted(() => ({
  listarTransaccionesMes: vi.fn(),
  dividirTransaccion: vi.fn(),
  deshacerDivision: vi.fn(),
  listarRubros: vi.fn(),
}));

vi.mock("@/lib/cargas", async (orig) => ({
  ...(await orig<typeof import("@/lib/cargas")>()),
  listarTransaccionesMes: mocks.listarTransaccionesMes,
  dividirTransaccion: mocks.dividirTransaccion,
  deshacerDivision: mocks.deshacerDivision,
}));
vi.mock("@/lib/rubros", async (orig) => ({
  ...(await orig<typeof import("@/lib/rubros")>()),
  listarRubros: mocks.listarRubros,
}));

function tx(over: Partial<TransaccionMovimiento> = {}): TransaccionMovimiento {
  return {
    id: "t1",
    fecha: "2026-08-04",
    descripcion: "Envío a Luis Miguel",
    valor: "20123787.47",
    tipo_flujo: "egreso",
    rubro_id: "r-prestamos",
    banco: "global66",
    id_banco: "38009969|1",
    revierte_id: null,
    anulada: false,
    es_reverso: false,
    dividida: false,
    partes: null,
    ...over,
  };
}

function rubro(over: Partial<Rubro>): Rubro {
  return {
    id: "r-x",
    grupo: "deudas_obligaciones",
    nombre: "X",
    tipo_flujo: "egreso",
    codigo: null,
    activo: true,
    ...over,
  } as Rubro;
}

const RUBROS: Rubro[] = [
  rubro({ id: "r-prestamos", nombre: "Préstamos", codigo: "4010" }),
  rubro({ id: "r-garantia", nombre: "Garantía cupo", codigo: "4030" }),
  rubro({
    id: "r-ingreso",
    nombre: "Recaudo",
    tipo_flujo: "ingreso",
    codigo: "0110",
  }),
];

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <PanelDividir gestor={true} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.listarRubros.mockResolvedValue(RUBROS);
});

describe("PanelDividir", () => {
  it("lista la transacción con su rubro y ofrece Dividir", async () => {
    mocks.listarTransaccionesMes.mockResolvedValue({ items: [tx()] });
    renderPanel();
    expect(await screen.findByText("Envío a Luis Miguel")).toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: /dividir/i }),
    ).toBeInTheDocument();
  });

  it("valida que las partes sumen exacto ANTES de llamar al backend, y divide", async () => {
    mocks.listarTransaccionesMes.mockResolvedValue({ items: [tx()] });
    renderPanel();
    fireEvent.click(await screen.findByRole("button", { name: /^dividir$/i }));
    const dialogo = await screen.findByRole("dialog");

    // parte 1: Garantía cupo 14.000.000 ; parte 2: Préstamos 6.000.000 (NO cuadra)
    fireEvent.change(within(dialogo).getByLabelText("Rubro parte 1"), {
      target: { value: "r-garantia" },
    });
    fireEvent.change(within(dialogo).getByLabelText("Monto parte 1"), {
      target: { value: "14000000" },
    });
    fireEvent.change(within(dialogo).getByLabelText("Rubro parte 2"), {
      target: { value: "r-prestamos" },
    });
    fireEvent.change(within(dialogo).getByLabelText("Monto parte 2"), {
      target: { value: "6000000" },
    });
    // botón deshabilitado mientras no cuadra
    expect(
      within(dialogo).getByRole("button", { name: /^dividir$/i }),
    ).toBeDisabled();

    // ahora cuadra: 14.000.000 + 6.123.787,47 = 20.123.787,47
    fireEvent.change(within(dialogo).getByLabelText("Monto parte 2"), {
      target: { value: "6123787.47" },
    });
    const btn = within(dialogo).getByRole("button", { name: /^dividir$/i });
    expect(btn).toBeEnabled();
    mocks.dividirTransaccion.mockResolvedValue(tx({ dividida: true }));
    fireEvent.click(btn);
    expect(mocks.dividirTransaccion).toHaveBeenCalledWith("t1", [
      { rubro_id: "r-garantia", valor: "14000000" },
      { rubro_id: "r-prestamos", valor: "6123787.47" },
    ]);
  });

  it("el selector de rubros solo ofrece los del mismo tipo_flujo (egreso)", async () => {
    mocks.listarTransaccionesMes.mockResolvedValue({ items: [tx()] });
    renderPanel();
    fireEvent.click(await screen.findByRole("button", { name: /^dividir$/i }));
    const dialogo = await screen.findByRole("dialog");
    const select = within(dialogo).getByLabelText("Rubro parte 2");
    // Recaudo (ingreso) NO debe estar entre las opciones
    expect(
      within(select).queryByRole("option", { name: /Recaudo/ }),
    ).toBeNull();
    expect(
      within(select).getByRole("option", { name: /Garantía cupo/ }),
    ).toBeInTheDocument();
  });

  it("una transacción dividida muestra sus partes y ofrece Deshacer", async () => {
    mocks.listarTransaccionesMes.mockResolvedValue({
      items: [
        tx({
          dividida: true,
          rubro_id: "r-garantia",
          partes: [
            { rubro_id: "r-garantia", valor: "14000000.00" },
            { rubro_id: "r-prestamos", valor: "6123787.47" },
          ],
        }),
      ],
    });
    renderPanel();
    expect(await screen.findByText(/Dividida en 2/)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /deshacer división/i }),
    ).toBeInTheDocument();
  });
});
