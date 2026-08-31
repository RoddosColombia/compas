// G-AXE · COMPAS 2.0 Fundacional §5 · gate de accesibilidad
//
// Valida la vista de Proyecciones contra axe-core. Un cambio que introduce un
// issue bloqueante de accesibilidad (WCAG 2 A/AA) FALLA en CI antes de mergear.
//
// Enfoque: renderiza ProyeccionPage con la config que ya usa
// ProyeccionPage.test.tsx (mock del auth + mocks de librerías de datos), corre
// `axe` y valida cero violaciones. Reusa el mismo escenario de mock que ese
// test para no divergir en fixtures.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import axe from "axe-core";
import { describe, expect, it, vi } from "vitest";

import type { MesProyeccion, Proyeccion } from "@/lib/proyeccion";
import ProyeccionPage from "@/pages/ProyeccionPage";

// ─────────────────────────── fixture mínima ───────────────────────────

function mesProy(i: number, extras: Partial<MesProyeccion> = {}): MesProyeccion {
  const y = 2026 + Math.floor((6 + i) / 12);
  const m = ((6 + i) % 12) + 1;
  return {
    mes: `${y}-${String(m).padStart(2, "0")}`,
    motos: 50 + i,
    cartera: 120,
    recaudo_credito: "30000000.00",
    cuotas_iniciales: "5000000.00",
    ingreso_bruto: "35000000.00",
    neto: "34000000.00",
    provision: "-700000.00",
    gastos_fijos: "-125000000.00",
    gps: "-4000000.00",
    costo_nueva: "-3000000.00",
    adelanto: "0.00",
    pago_inventario: "0.00",
    fondeo: "0.00",
    int_deuda: "-300000.00",
    iva: "0.00",
    aval: "0.00",
    mora: "0.00",
    recuperacion: "0.00",
    default: "0.00",
    egresos: "-132300000.00",
    flujo: "-98300000.00",
    caja: "200000000.00",
    estado: "ok",
    ...extras,
  };
}

const MESES = Array.from({ length: 60 }, (_, i) =>
  i === 3 ? mesProy(i, { caja: "40000000.00", estado: "critico" }) : mesProy(i),
);

const PROY: Proyeccion = {
  escenario: "base",
  caja_minima: "125000000.00",
  fondo_provision: [],
  piso_caja: "40000000.00",
  mes_mas_ajustado: "2026-10",
  meses_bajo_minimo: 1,
  caja_final: "200000000.00",
  capital_requerido: "85000000.00",
  runway_meses: null,
  ventana_reconciliada: null,
  interes_obligaciones: {},
  meses: MESES,
};

const mocks = vi.hoisted(() => ({
  obtenerProyeccion: vi.fn(),
  obtenerProyeccionAgregada: vi.fn(),
  obtenerProyeccionConUnidadesExtra: vi.fn(),
  resolverUnidadesParaUmbral: vi.fn(),
}));

vi.mock("@/lib/proyeccion", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/proyeccion")>();
  return {
    ...real,
    obtenerProyeccion: mocks.obtenerProyeccion,
    obtenerProyeccionAgregada: mocks.obtenerProyeccionAgregada,
    obtenerProyeccionConUnidadesExtra: mocks.obtenerProyeccionConUnidadesExtra,
    resolverUnidadesParaUmbral: mocks.resolverUnidadesParaUmbral,
  };
});

vi.mock("@/auth/AuthContext", () => ({
  useAuth: () => ({ puede: () => true }),
}));

vi.mock("@/lib/decisiones", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/decisiones")>();
  return {
    ...real,
    obtenerValles: vi.fn().mockResolvedValue({
      escenario: "base",
      caja_minima: "125000000.00",
      valles: [],
    }),
    resolver: vi.fn().mockResolvedValue({
      objetivo: "techo_gasto",
      techo_mensual: "5000000.00",
      valle_limitante_mes: "2027-05",
      piso_resultante: "10000000.00",
      meta: "0.00",
      colchon: "0.00",
      hay_holgura: true,
    }),
  };
});

function renderPage() {
  mocks.obtenerProyeccion.mockResolvedValue(PROY);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ProyeccionPage />
    </QueryClientProvider>,
  );
}

// ─────────────────────────── el gate ───────────────────────────

describe("G-AXE · accesibilidad de la vista de Proyecciones", () => {
  it("ProyeccionPage no tiene violaciones bloqueantes de WCAG 2 A/AA", async () => {
    const { container, findByText } = renderPage();
    // Esperamos que los datos rendericen antes de correr axe (evita evaluar
    // durante el estado "cargando" — el DOM real es el que importa).
    await findByText("Piso de caja");

    // axe-core aplica sus reglas activas por defecto (WCAG 2 A/AA + best
    // practices ligeras). `disableOtherRules: false` = todas las por defecto.
    const results = await axe.run(container as HTMLElement, {
      resultTypes: ["violations"],
    });
    // Filtramos a impact severo — el gate SOLO bloquea `serious` y `critical`.
    // Los `moderate` y `minor` van al ROADMAP como fast-follow (no ruido en CI).
    const bloqueantes = results.violations.filter(
      (v) => v.impact === "serious" || v.impact === "critical",
    );
    if (bloqueantes.length > 0) {
      const detalle = bloqueantes
        .map((v) => `  · [${v.impact}] ${v.id}: ${v.help}`)
        .join("\n");
      throw new Error(
        `axe-core encontró ${bloqueantes.length} violación(es) ` +
          `serious/critical:\n${detalle}\n\nSaneo: ver ${bloqueantes[0].helpUrl}`,
      );
    }
    expect(bloqueantes).toHaveLength(0);
  });
});
