// FIX-UI-1: el lienzo de contenido es de ancho completo SOLO en /proyeccion (la foto
// del CEO a ~1918px sin scroll lateral); el resto del cockpit sigue centrado a max-w-6xl.
//
// Task 4 (fabs-chat-embebido) review: regla 9 exige que el botón/panel de FABS
// solo aparezcan con la capacidad cfo:consultar — ver el bloque de abajo.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppShell, anchoContenido } from "@/components/layout/AppShell";

describe("anchoContenido — ancho del lienzo por ruta (FIX-UI-1)", () => {
  it("/proyeccion → ancho completo (sin max-w)", () => {
    expect(anchoContenido("/proyeccion")).toBe("w-full");
  });

  it("subrutas de /proyeccion → ancho completo", () => {
    expect(anchoContenido("/proyeccion/algo")).toBe("w-full");
  });

  it("otras rutas → centrado a max-w-6xl", () => {
    expect(anchoContenido("/obligaciones")).toBe("mx-auto max-w-6xl");
    expect(anchoContenido("/inicio")).toBe("mx-auto max-w-6xl");
    expect(anchoContenido("/")).toBe("mx-auto max-w-6xl");
  });
});

const puedeMock = vi.fn();

vi.mock("@/auth/AuthContext", () => ({
  useAuth: () => ({ puede: puedeMock, rol: "financiero", cerrarSesion: vi.fn() }),
}));

// Sin backend en jsdom: listarMeses se mockea para que MesStatusBar resuelva
// rápido (sin mes en ejecución) en vez de dejar la query pendiente/errada.
vi.mock("@/lib/meses", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/meses")>();
  return { ...real, listarMeses: () => Promise.resolve({ items: [] }) };
});

function renderShell() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AppShell>
          <div>contenido</div>
        </AppShell>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AppShell — botón/panel de FABS gateados por cfo:consultar (regla 9)", () => {
  beforeEach(() => {
    puedeMock.mockReset();
  });

  it("sin la capacidad cfo:consultar: el botón 'Preguntá a FABS' NO aparece", () => {
    puedeMock.mockReturnValue(false);
    renderShell();
    expect(screen.queryByText("Preguntá a FABS")).toBeNull();
  });

  it("con la capacidad cfo:consultar: el botón 'Preguntá a FABS' aparece", () => {
    puedeMock.mockImplementation((cap: string) => cap === "cfo:consultar");
    renderShell();
    expect(screen.getByText("Preguntá a FABS")).toBeInTheDocument();
  });
});
