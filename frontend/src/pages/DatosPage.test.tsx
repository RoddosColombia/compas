// Supuestos (DatosPage reescrita en C3) — criterios §6:
//   1. El borrador NUNCA toca el vigente (descartar restaura; nada viaja).
//   2. Unidades humanas en superficie ("5" %, "125.000.000") ↔ canónicas al API.
//   3. Validación en 3 niveles (error bloquea; advertencia exige confirmación).
//   4. Panel de impacto: preview llamado con el set canónico; fallo → aviso.
//   6. CR-002: componentes visibles/editables; "Costo moto nueva" no existe más.
//   8. Guardar: diff en el diálogo + nota en el PUT.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Parametros } from "@/lib/parametros";
import type { MesProyeccion, Proyeccion } from "@/lib/proyeccion";
import DatosPage from "@/pages/DatosPage";

function mesProy(mes: string, caja: string): MesProyeccion {
  return {
    mes,
    motos: 50,
    cartera: 100,
    recaudo_credito: "0.00",
    cuotas_iniciales: "0.00",
    ingreso_bruto: "0.00",
    neto: "0.00",
    provision: "0.00",
    gastos_fijos: "0.00",
    gps: "0.00",
    costo_nueva: "0.00",
    adelanto: "0.00",
    pago_inventario: "0.00",
    fondeo: "0.00",
    int_deuda: "0.00",
    iva: "0.00",
    egresos: "0.00",
    flujo: "0.00",
    caja,
    estado: "ok",
  };
}

function proy(piso: string, extras: Partial<Proyeccion> = {}): Proyeccion {
  return {
    escenario: "base",
    caja_minima: "30000000.00",
    fondo_provision: [],
    piso_caja: piso,
    mes_mas_ajustado: "2027-05",
    meses_bajo_minimo: 0,
    caja_final: "500000000.00",
    capital_requerido: "0.00",
    runway_meses: null,
    ventana_reconciliada: null,
    interes_obligaciones: {},
    meses: [mesProy("2026-07", "100000000.00"), mesProy("2026-08", piso)],
    ...extras,
  };
}

const VIGENTE: Parametros = {
  id: "p1",
  vigente_desde: "2026-07-23",
  modificado_por: "u1",
  caja_inicial: "24000000",
  caja_minima: "80000000",
  crec_pct_mensual: "0.02",
  adelanto_auteco: "0",
  tasa_auteco: "0.016",
  gastos_fijos: "125000000",
  gps_moto: "33201",
  costo_moto_nueva: "692005",
  deuda: "28527080",
  tasa_deuda: "0.011",
  pct_mora: "0.03",
  pct_recuperacion: "0.4",
  pct_default: "0.03",
  pct_provision: "0.02",
  motos_base: 85,
  horizonte_meses: 144,
  plazo_auteco_dias: 150,
  base_auteco_dias: 90,
  mes_inicio_deuda: 2,
  meses_deuda: 14,
  componentes_alistamiento: [
    { nombre: "Matrícula (trámite)", valor: "227800", activo: true, orden: 1 },
    { nombre: "Instalación GPS", valor: "83000", activo: true, orden: 2 },
    { nombre: "SOAT", valor: "363300", activo: true, orden: 3 },
    { nombre: "Colchón/otros", valor: "17905", activo: true, orden: 4 },
  ],
  rampa_unidades: {},
  // SUP-1: sin segundo tramo de crecimiento (comportamiento histórico)
  crec_pct_mensual_2: null,
  crec_mes_corte: null,
  // SUP-2: variables editables (defaults = el comportamiento de siempre)
  meses_rezago_recuperacion: 1,
  pct_prefondeo_iva: "1",
  pct_aval_recaudo: "0",
  pct_mora_pesimista: null,
  pct_recuperacion_pesimista: null,
  pct_mora_optimista: null,
  pct_recuperacion_optimista: null,
};

const MODELO = {
  id: "m1",
  nombre: "Raider",
  costo_auteco: "5000000",
  precio_venta_con_iva: "8000000",
  cuota_inicial: "1000000",
  cuota_semanal: "164900",
  plazo_semanas: 78,
  matricula: "500000",
  participacion_mix: "1",
  plan2_plazo_semanas: null,
  plan2_cuota_semanal: null,
  peso_plan1: "1",
  activo: true,
  es_sistema: false,
};

const mocks = vi.hoisted(() => ({
  obtenerParametros: vi.fn(),
  guardarParametros: vi.fn(),
  previewProyeccion: vi.fn(),
  obtenerSensibilidad: vi.fn(),
  obtenerProyeccion: vi.fn(),
  listarModelos: vi.fn(),
}));

vi.mock("@/auth/AuthContext", () => ({
  useAuth: () => ({ rol: "financiero", puede: () => true }),
}));

vi.mock("@/lib/parametros", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/parametros")>();
  return {
    ...real,
    obtenerParametros: mocks.obtenerParametros,
    guardarParametros: mocks.guardarParametros,
    previewProyeccion: mocks.previewProyeccion,
    obtenerSensibilidad: mocks.obtenerSensibilidad,
  };
});

vi.mock("@/lib/proyeccion", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/proyeccion")>();
  return { ...real, obtenerProyeccion: mocks.obtenerProyeccion };
});

vi.mock("@/lib/modelosMoto", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/modelosMoto")>();
  return { ...real, listarModelos: mocks.listarModelos };
});

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <DatosPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.obtenerParametros.mockResolvedValue(VIGENTE);
  mocks.listarModelos.mockResolvedValue([MODELO]);
  mocks.obtenerProyeccion.mockResolvedValue(proy("77800000.00"));
  mocks.previewProyeccion.mockResolvedValue(
    proy("41200000.00", {
      mes_mas_ajustado: "2027-07",
      meses_bajo_minimo: 1,
      capital_requerido: "8800000.00",
    }),
  );
  mocks.obtenerSensibilidad.mockResolvedValue({
    escenario: "base",
    horizonte_meses: 60,
    piso_base: "77800000.00",
    variables: [
      {
        variable: "gastos_fijos",
        etiqueta: "Gastos fijos",
        variacion: "±10 %",
        piso_base: "77800000.00",
        piso_mas: "23800000.00",
        piso_menos: "131800000.00",
      },
    ],
  });
});

async function esperarEditor() {
  return await screen.findByDisplayValue("125.000.000"); // gastos fijos humano
}

describe("Supuestos — unidades humanas (§6.2)", () => {
  it("porcentajes como % y montos con separador es-CO", async () => {
    renderPage();
    await esperarEditor();
    // crec 0.02 → "2" (%); tasa 0.016 → "1.6"
    expect(screen.getByLabelText(/Crecimiento/)).toHaveValue("2");
    expect(screen.getByDisplayValue("1.6")).toBeInTheDocument();
    // equivalente anual visible
    expect(screen.getByText(/≈ \+26\.8 % anual/)).toBeInTheDocument();
  });
});

describe("Supuestos — el borrador no toca el vigente (§6.1)", () => {
  it("editar + descartar restaura y NUNCA llama al guardado", async () => {
    renderPage();
    const gastos = await esperarEditor();
    fireEvent.change(gastos, { target: { value: "200.000.000" } });
    expect(
      await screen.findByText(/Borrador con 1 cambio/),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Descartar" }));
    expect(await screen.findByDisplayValue("125.000.000")).toBeInTheDocument();
    expect(screen.queryByText(/Borrador con/)).toBeNull();
    expect(mocks.guardarParametros).not.toHaveBeenCalled();
  });
});

describe("Supuestos — validación en 3 niveles (§6.3)", () => {
  it("error bloquea: monto vacío marca el campo", async () => {
    renderPage();
    const gastos = await esperarEditor();
    fireEvent.change(gastos, { target: { value: "" } });
    expect(await screen.findByText("obligatorio")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Guardar supuestos" }),
    ).toBeNull();
  });

  it("advertencia: crecimiento > 3 %/mes muestra el anual y exige confirmación", async () => {
    renderPage();
    await esperarEditor();
    const crec = screen.getByLabelText(/Crecimiento/);
    fireEvent.change(crec, { target: { value: "5" } });
    expect(
      await screen.findByText(/5 % mensual = \+79\.6 % anual compuesto/),
    ).toBeInTheDocument();
    // abrir el diálogo: confirmar queda bloqueado hasta marcar el checkbox
    fireEvent.click(
      await screen.findByRole("button", { name: "Guardar supuestos" }),
    );
    const dialogo = await screen.findByRole("dialog", {
      name: "Guardar supuestos",
    });
    const confirmar = screen
      .getAllByRole("button", { name: "Guardar supuestos" })
      .find((b) => dialogo.contains(b)) as HTMLElement;
    expect(confirmar).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox", { name: /confirmo/i }));
    expect(confirmar).not.toBeDisabled();
  });

  it("nota informativa: adelanto Auteco en $ 0 declara la decisión del CEO", async () => {
    renderPage();
    await esperarEditor();
    expect(
      screen.getByText(/Adelanto Auteco: \$ 0 — decisión CEO 2026-07-26/),
    ).toBeInTheDocument();
  });
});

describe("Supuestos — panel de impacto (§6.4)", () => {
  it("un cambio válido llama al preview con el set CANÓNICO y pinta los deltas", async () => {
    renderPage();
    const gastos = await esperarEditor();
    fireEvent.change(gastos, { target: { value: "200.000.000" } });
    await waitFor(() => expect(mocks.previewProyeccion).toHaveBeenCalled(), {
      timeout: 3000,
    });
    const [params] = mocks.previewProyeccion.mock.calls[0];
    expect(params.gastos_fijos).toBe("200000000"); // canónico, sin separador
    expect(params.crec_pct_mensual).toBe("0.02"); // fracción, no "2"
    expect(params.costo_moto_nueva).toBe("692005"); // Σ componentes activos
    // deltas: 41,2 M vs 77,8 M → ▼ -$ 36,6 M
    expect(await screen.findByText(/▼ -\$ 36,6 M/)).toBeInTheDocument();
    expect(screen.getByText("Con tus cambios")).toBeInTheDocument();
  });

  it("si el preview falla: aviso, nunca cifras viejas sin marcar", async () => {
    mocks.previewProyeccion.mockRejectedValue(new Error("boom"));
    renderPage();
    const gastos = await esperarEditor();
    fireEvent.change(gastos, { target: { value: "200.000.000" } });
    expect(
      await screen.findByText(/No se pudo calcular el impacto/, undefined, {
        timeout: 3000,
      }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/▼ -\$ 36,6 M/)).toBeNull();
  });
});

describe("Supuestos — CR-002 (§6.6)", () => {
  it("los componentes se ven y el nombre viejo no existe más", async () => {
    renderPage();
    await esperarEditor();
    expect(
      screen.getByText(/Costos de alistamiento por moto vendida/),
    ).toBeInTheDocument();
    expect(screen.getByDisplayValue("Matrícula (trámite)")).toBeInTheDocument();
    expect(screen.getByDisplayValue("SOAT")).toBeInTheDocument();
    expect(screen.queryByText("Costo moto nueva")).toBeNull();
    // CR-002: la matrícula salió del formulario de modelos (era placebo)
    expect(screen.queryByText("Matrícula", { exact: true })).toBeNull();
  });

  it("desactivar un componente recalcula la Σ que viaja al preview", async () => {
    renderPage();
    await esperarEditor();
    fireEvent.click(screen.getAllByRole("checkbox")[3]); // Colchón/otros
    await waitFor(() => expect(mocks.previewProyeccion).toHaveBeenCalled(), {
      timeout: 3000,
    });
    const [params] = mocks.previewProyeccion.mock.calls[0];
    expect(params.costo_moto_nueva).toBe("674100"); // 692005 − 17905
    expect(
      params.componentes_alistamiento.find(
        (c: { nombre: string }) => c.nombre === "Colchón/otros",
      ).activo,
    ).toBe(false);
  });
});

describe("Supuestos — FIX-L: rampa de unidades por mes", () => {
  it("agregar un mes de rampa lo manda al preview con rampa_unidades", async () => {
    renderPage();
    await esperarEditor();
    fireEvent.click(screen.getByRole("button", { name: "Agregar mes" }));
    fireEvent.change(screen.getByLabelText("Mes rampa 1"), {
      target: { value: "2026-08" },
    });
    fireEvent.change(screen.getByLabelText("Unidades rampa 1"), {
      target: { value: "75" },
    });
    await waitFor(
      () => {
        const call = mocks.previewProyeccion.mock.calls.at(-1);
        expect(call?.[0].rampa_unidades).toEqual({ "2026-08": 75 });
      },
      { timeout: 3000 },
    );
  });
});

describe("Supuestos — guardar con diff y nota (§6.8)", () => {
  it("el diálogo muestra antes → después y la nota viaja en el PUT", async () => {
    mocks.guardarParametros.mockResolvedValue(VIGENTE);
    renderPage();
    const gastos = await esperarEditor();
    fireEvent.change(gastos, { target: { value: "200.000.000" } });
    fireEvent.click(
      await screen.findByRole("button", { name: "Guardar supuestos" }),
    );
    const dialogo = await screen.findByRole("dialog", {
      name: "Guardar supuestos",
    });
    expect(dialogo).toHaveTextContent("Gastos fijos / mes:");
    expect(dialogo.textContent?.replace(/\s/g, " ")).toContain(
      "$ 200.000.000,00",
    );
    // +60 % vs. vigente dispara la advertencia de ±50 % → confirmar explícito
    fireEvent.click(screen.getByRole("checkbox", { name: /confirmo/i }));
    fireEvent.change(screen.getByPlaceholderText(/por decisión de junta/), {
      target: { value: "ajuste de nómina" },
    });
    const confirmar = screen
      .getAllByRole("button", { name: "Guardar supuestos" })
      .find((b) => dialogo.contains(b)) as HTMLElement;
    fireEvent.click(confirmar);
    await waitFor(() => expect(mocks.guardarParametros).toHaveBeenCalled());
    const [input] = mocks.guardarParametros.mock.calls[0];
    expect(input.gastos_fijos).toBe("200000000");
    expect(input.nota).toBe("ajuste de nómina");
    expect(input.vigente_desde).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});

describe("Supuestos — tornado presente (§6.7)", () => {
  it("renderiza el panel de sensibilidad", async () => {
    renderPage();
    await esperarEditor();
    expect(
      await screen.findByText("¿Qué mueve mi mínimo de caja?"),
    ).toBeInTheDocument();
  });
});
