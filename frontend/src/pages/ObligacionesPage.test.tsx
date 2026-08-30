// ObligacionesPage (D2 §7): lista de obligaciones (Auteco primero) con saldo pendiente
// y facturas; registrar factura (con validación antes de llamar), registrar pago con
// origen (roddos | tercero), anular. CRUD gated por proyeccion:gestionar (regla 9).
// Montos string (regla 1).

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { FacturaObligacion, Obligacion } from "@/lib/obligaciones";
import ObligacionesPage from "@/pages/ObligacionesPage";

const mocks = vi.hoisted(() => ({
  listarObligaciones: vi.fn(),
  listarFacturas: vi.fn(),
  registrarFactura: vi.fn(),
  registrarPago: vi.fn(),
  anularFactura: vi.fn(),
  anularPago: vi.fn(),
  simularNegociacion: vi.fn(),
  caps: { actual: [] as string[] },
}));

vi.mock("@/auth/AuthContext", () => ({
  useAuth: () => ({
    rol: "financiero",
    puede: (cap: string) => mocks.caps.actual.includes(cap),
  }),
}));

vi.mock("@/lib/obligaciones", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/obligaciones")>();
  return {
    ...real,
    listarObligaciones: mocks.listarObligaciones,
    listarFacturas: mocks.listarFacturas,
    registrarFactura: mocks.registrarFactura,
    registrarPago: mocks.registrarPago,
    anularFactura: mocks.anularFactura,
    anularPago: mocks.anularPago,
    simularNegociacion: mocks.simularNegociacion,
  };
});

function obligacion(over: Partial<Obligacion> = {}): Obligacion {
  return {
    id: "o1",
    nombre: "Inventario Auteco",
    acreedor: "Auteco",
    naturaleza: "facturacion",
    activo: true,
    es_sistema: true,
    actualizado_at: "2026-08-04T00:00:00",
    saldo_pendiente: "180000000.00",
    plazo_base_dias: 150,
    plazo_max_dias: 150,
    tasa_excedente_mensual: "0",
    ...over,
  };
}

function factura(over: Partial<FacturaObligacion> = {}): FacturaObligacion {
  return {
    id: "f1",
    obligacion_id: "o1",
    numero: "E670165520",
    fecha_factura: "2026-05-29",
    valor: "180000000.00",
    plazo_elegido_dias: 150,
    nota: "22 Raider",
    activo: true,
    estado: "pendiente",
    pagada_desde: null,
    pagada_at: null,
    pagada_valor: null,
    pagada_nota: null,
    ...over,
  };
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/obligaciones"]}>
        <ObligacionesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.caps.actual = ["dashboard:leer", "proyeccion:gestionar"];
});

describe("ObligacionesPage — lista + saldo + facturas", () => {
  it("muestra la obligación, su saldo pendiente y la factura con mes de pago", async () => {
    mocks.listarObligaciones.mockResolvedValue({
      items: [obligacion({ saldo_pendiente: "500000000.00" })],
    });
    mocks.listarFacturas.mockResolvedValue({ items: [factura()] });
    renderPage();
    expect(await screen.findByText("Obligaciones")).toBeInTheDocument();
    const card = within(await screen.findByTestId("obligacion-o1"));
    // saldo pendiente formateado (distinto del valor de la factura)
    expect(card.getByText(/500\.000\.000/)).toBeInTheDocument();
    // factura: numero + mes de pago derivado (may + 5 = oct)
    expect(await card.findByText("E670165520")).toBeInTheDocument();
    expect(card.getByText("2026-10")).toBeInTheDocument();
    expect(card.getByText("Pendiente")).toBeInTheDocument();
  });
});

describe("ObligacionesPage — registrar factura", () => {
  it("valida el valor ANTES de llamar al backend, luego llama con los campos", async () => {
    mocks.listarObligaciones.mockResolvedValue({ items: [obligacion()] });
    mocks.listarFacturas.mockResolvedValue({ items: [] });
    renderPage();
    fireEvent.click(
      await screen.findByRole("button", { name: /registrar factura/i }),
    );
    const dialogo = await screen.findByRole("dialog", {
      name: /registrar factura/i,
    });
    fireEvent.change(within(dialogo).getByLabelText(/fecha/i), {
      target: { value: "2026-05-29" },
    });
    // valor inválido → no llama
    fireEvent.change(within(dialogo).getByLabelText(/valor/i), {
      target: { value: "abc" },
    });
    fireEvent.click(within(dialogo).getByRole("button", { name: /guardar/i }));
    expect(mocks.registrarFactura).not.toHaveBeenCalled();
    expect(within(dialogo).getByText(/número positivo/i)).toBeInTheDocument();
    // válido → llama con numero/fecha/valor/plazo
    mocks.registrarFactura.mockResolvedValue(factura());
    fireEvent.change(within(dialogo).getByLabelText(/número/i), {
      target: { value: "E670165520" },
    });
    fireEvent.change(within(dialogo).getByLabelText(/valor/i), {
      target: { value: "149030808" },
    });
    fireEvent.click(within(dialogo).getByRole("button", { name: /guardar/i }));
    expect(mocks.registrarFactura).toHaveBeenCalledWith(
      "o1",
      expect.objectContaining({
        numero: "E670165520",
        fecha_factura: "2026-05-29",
        valor: "149030808",
        plazo_elegido_dias: 150,
      }),
    );
  });
});

describe("ObligacionesPage — registrar pago con origen", () => {
  it("llama con pagada_desde=tercero cuando se elige tercero", async () => {
    mocks.listarObligaciones.mockResolvedValue({ items: [obligacion()] });
    mocks.listarFacturas.mockResolvedValue({ items: [factura()] });
    mocks.registrarPago.mockResolvedValue(
      factura({ estado: "pagada", pagada_desde: "tercero" }),
    );
    renderPage();
    fireEvent.click(
      await screen.findByRole("button", { name: /registrar pago/i }),
    );
    const dialogo = await screen.findByRole("dialog", {
      name: /registrar pago/i,
    });
    fireEvent.change(within(dialogo).getByLabelText(/fecha del pago/i), {
      target: { value: "2026-09-10" },
    });
    fireEvent.click(within(dialogo).getByLabelText(/tercero/i));
    fireEvent.click(within(dialogo).getByRole("button", { name: /guardar/i }));
    expect(mocks.registrarPago).toHaveBeenCalledWith(
      "o1",
      "f1",
      expect.objectContaining({ pagada_desde: "tercero" }),
    );
  });

  it("una factura pagada por tercero muestra el origen y ofrece anular pago", async () => {
    mocks.listarObligaciones.mockResolvedValue({
      items: [obligacion({ saldo_pendiente: "0.00" })],
    });
    mocks.listarFacturas.mockResolvedValue({
      items: [
        factura({
          estado: "pagada",
          pagada_desde: "tercero",
          pagada_at: "2026-09-10",
        }),
      ],
    });
    renderPage();
    const card = within(await screen.findByTestId("obligacion-o1"));
    expect(await card.findByText(/pagada · tercero/i)).toBeInTheDocument();
    expect(
      card.getByRole("button", { name: /anular pago/i }),
    ).toBeInTheDocument();
  });
});

describe("ObligacionesPage — RBAC", () => {
  it("oculta las mutaciones a roles sin proyeccion:gestionar", async () => {
    mocks.caps.actual = ["dashboard:leer"];
    mocks.listarObligaciones.mockResolvedValue({ items: [obligacion()] });
    mocks.listarFacturas.mockResolvedValue({ items: [factura()] });
    renderPage();
    expect(await screen.findByText("Obligaciones")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /registrar factura/i }),
    ).toBeNull();
    expect(
      screen.queryByRole("button", { name: /registrar pago/i }),
    ).toBeNull();
  });
});

describe("ObligacionesPage — RF-F8 «Simular negociación»", () => {
  it("no muestra el botón si la obligación no tiene rango de plazo (plazo_max == plazo_base)", async () => {
    // Auteco por defecto tiene 150/150 → sin rango, no hay nada que negociar.
    mocks.listarObligaciones.mockResolvedValue({ items: [obligacion()] });
    mocks.listarFacturas.mockResolvedValue({ items: [factura()] });
    renderPage();
    expect(await screen.findByText("Obligaciones")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /simular negociación/i }),
    ).toBeNull();
  });

  it("muestra el botón cuando plazo_max > plazo_base, abre diálogo y llama simularNegociacion con el delta", async () => {
    mocks.listarObligaciones.mockResolvedValue({
      items: [
        obligacion({ plazo_base_dias: 90, plazo_max_dias: 180 }),
      ],
    });
    mocks.listarFacturas.mockResolvedValue({
      items: [
        factura({ plazo_elegido_dias: 90, fecha_factura: "2026-09-01" }),
      ],
    });
    mocks.simularNegociacion.mockResolvedValue({
      piso_actual: "30000000.00",
      piso_negociado: "55000000.00",
      delta_piso: "25000000.00",
      mes_pago_actual: "2026-12",
      mes_pago_negociado: "2027-03",
      valles_actuales: [],
      valles_negociados: [],
    });
    renderPage();
    const boton = await screen.findByRole("button", {
      name: /simular negociación/i,
    });
    fireEvent.click(boton);
    const dialogo = await screen.findByRole("dialog", {
      name: /simular negociación/i,
    });
    // El input de plazo trae el actual (90). Lo cambio a 180 y disparo.
    const inputPlazo = within(dialogo).getByLabelText(/plazo nuevo/i);
    fireEvent.change(inputPlazo, { target: { value: "180" } });
    fireEvent.click(within(dialogo).getByRole("button", { name: /simular/i }));
    // El servicio recibe SOLO el plazo (la fecha no cambió).
    await waitFor(() =>
      expect(mocks.simularNegociacion).toHaveBeenCalledWith("o1", "f1", {
        plazo_elegido_dias_nuevo: 180,
        fecha_factura_nueva: undefined,
      }),
    );
    // El resultado se pinta: piso actual → negociado + delta positivo.
    expect(await within(dialogo).findByText(/piso negociado/i)).toBeInTheDocument();
    expect(
      within(dialogo).getByText(/negociar mejora el piso/i),
    ).toBeInTheDocument();
  });

  it("bloquea el submit si NADA cambió (mismo plazo y misma fecha)", async () => {
    mocks.listarObligaciones.mockResolvedValue({
      items: [obligacion({ plazo_base_dias: 90, plazo_max_dias: 180 })],
    });
    mocks.listarFacturas.mockResolvedValue({
      items: [factura({ plazo_elegido_dias: 90, fecha_factura: "2026-09-01" })],
    });
    renderPage();
    fireEvent.click(
      await screen.findByRole("button", { name: /simular negociación/i }),
    );
    const dialogo = await screen.findByRole("dialog", {
      name: /simular negociación/i,
    });
    // Sin cambiar nada, click simular → error visible, no se llama al backend.
    fireEvent.click(within(dialogo).getByRole("button", { name: /simular/i }));
    expect(
      await within(dialogo).findByText(/cambia el plazo o la fecha/i),
    ).toBeInTheDocument();
    expect(mocks.simularNegociacion).not.toHaveBeenCalled();
  });
});
