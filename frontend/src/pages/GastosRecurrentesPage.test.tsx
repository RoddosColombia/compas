// frontend/src/pages/GastosRecurrentesPage.test.tsx
//
// Plantilla de gastos recurrentes: la tabla muestra cada gasto con su grupo/rubro y
// el equivalente mensual, el resumen suma por grupo, y los botones de mutación solo
// aparecen con rubros:gestionar (regla 9).

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { GastosRespuesta } from "@/lib/gastosRecurrentes";
import type { Rubro } from "@/lib/rubros";
import GastosRecurrentesPage from "@/pages/GastosRecurrentesPage";

const RESPUESTA: GastosRespuesta = {
  items: [
    {
      id: "g1",
      rubro_id: "r1",
      rubro_nombre: "Arriendos",
      rubro_grupo: "operacion",
      rubro_codigo: "2010",
      descripcion: "Arriendo oficina",
      monto: "3614953.00",
      frecuencia: "mensual",
      monto_mensual: "3614953.00",
      dia_pago: 5,
      hasta: null,
      notas: "Contrato a 1 año",
      activo: true,
      orden: 1,
    },
  ],
  resumen: { total: "3614953.00", por_grupo: { operacion: "3614953.00" } },
};

const RUBROS: Rubro[] = [
  {
    id: "r1",
    grupo: "operacion",
    nombre: "Arriendos",
    tipo_flujo: "egreso",
    codigo: "2010",
    tipo: "fijo",
    orden: 1,
    activo: true,
    es_sistema: false,
  },
];

const puedeMock = vi.fn();

vi.mock("@/auth/AuthContext", () => ({
  useAuth: () => ({ puede: puedeMock, rol: "financiero" }),
}));

vi.mock("@/lib/gastosRecurrentes", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/gastosRecurrentes")>();
  return { ...real, listarGastos: () => Promise.resolve(RESPUESTA) };
});

vi.mock("@/lib/rubros", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/rubros")>();
  return { ...real, listarRubros: () => Promise.resolve(RUBROS) };
});

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <GastosRecurrentesPage />
    </QueryClientProvider>,
  );
}

describe("GastosRecurrentesPage", () => {
  it("muestra el gasto, su grupo y el equivalente mensual", async () => {
    puedeMock.mockReturnValue(false);
    renderPage();
    expect(await screen.findByText("Arriendo oficina")).toBeInTheDocument();
    // el total mensual del resumen y el monto mensual usan el formato es-CO
    expect(screen.getAllByText(/3\.614\.953/).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Operación").length).toBeGreaterThan(0);
  });

  it("oculta las acciones sin rubros:gestionar (regla 9)", async () => {
    puedeMock.mockReturnValue(false);
    renderPage();
    await screen.findByText("Arriendo oficina");
    expect(screen.queryByText("Agregar gasto")).not.toBeInTheDocument();
    expect(screen.queryByText("Editar")).not.toBeInTheDocument();
  });

  it("muestra las acciones con rubros:gestionar", async () => {
    puedeMock.mockReturnValue(true);
    renderPage();
    await screen.findByText("Arriendo oficina");
    await waitFor(() =>
      expect(screen.getByText("Agregar gasto")).toBeInTheDocument(),
    );
    expect(screen.getByText("Editar")).toBeInTheDocument();
  });
});
