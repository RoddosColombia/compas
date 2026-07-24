// Datos — captura: supuestos del motor (parámetros) + catálogo de modelos de moto.
// Comportamiento probado: lista los modelos; con proyeccion:gestionar muestra los
// controles de captura (guardar supuestos, agregar modelo); sin el permiso, no.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { ModeloMoto } from "@/lib/modelosMoto";
import type { Parametros } from "@/lib/parametros";
import DatosPage from "@/pages/DatosPage";

const MODELO: ModeloMoto = {
  id: "m1",
  nombre: "Raider",
  costo_auteco: "5000000",
  precio_venta_con_iva: "8000000",
  cuota_inicial: "1000000",
  cuota_semanal: "164900",
  plazo_semanas: 78,
  matricula: "500000",
  participacion_mix: "1",
  orden: 0,
  activo: true,
  es_sistema: false,
};

const PARAMS = {
  id: "p1",
  vigente_desde: "2026-07-01",
  caja_inicial: "24000000",
  caja_minima: "125000000",
  crec_pct_mensual: "0.01",
  adelanto_auteco: "970000",
  tasa_auteco: "0.016",
  gastos_fijos: "125000000",
  gps_moto: "33201",
  costo_moto_nueva: "692005",
  deuda: "28527080",
  tasa_deuda: "0.011",
  pct_mora: "0.03",
  pct_recuperacion: "0.40",
  pct_default: "0.03",
  pct_provision: "0.02",
  motos_base: 50,
  horizonte_meses: 60,
  plazo_auteco_dias: 150,
  base_auteco_dias: 90,
  mes_inicio_deuda: 2,
  meses_deuda: 14,
  modificado_por: "u1",
} satisfies Parametros;

vi.mock("@/lib/modelosMoto", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/modelosMoto")>();
  return { ...real, listarModelos: () => Promise.resolve([MODELO]) };
});
vi.mock("@/lib/parametros", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/parametros")>();
  return { ...real, obtenerParametros: () => Promise.resolve(PARAMS) };
});

let puedeGestionar = true;
vi.mock("@/auth/AuthContext", () => ({
  useAuth: () => ({
    puede: (c: string) =>
      c === "proyeccion:gestionar" ? puedeGestionar : true,
  }),
}));

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

describe("DatosPage", () => {
  it("lista los modelos de moto", async () => {
    puedeGestionar = true;
    renderPage();
    expect(await screen.findByText("Raider")).toBeInTheDocument();
    expect(screen.getByText("Modelos de moto")).toBeInTheDocument();
  });

  it("con proyeccion:gestionar ofrece capturar (guardar supuestos, agregar modelo)", async () => {
    puedeGestionar = true;
    renderPage();
    await screen.findByText("Raider");
    expect(
      screen.getByRole("button", { name: /guardar supuestos/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /agregar modelo/i }),
    ).toBeInTheDocument();
  });

  it("sin el permiso no muestra los controles de captura", async () => {
    puedeGestionar = false;
    renderPage();
    await screen.findByText("Raider");
    expect(
      screen.queryByRole("button", { name: /guardar supuestos/i }),
    ).not.toBeInTheDocument();
  });
});
