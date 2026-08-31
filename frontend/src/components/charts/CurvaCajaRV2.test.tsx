// CurvaCajaRV2 — RV-V2 Fundacional §3, rebanada 1. Cada test = un AC.

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CurvaCajaRV2 } from "@/components/charts/CurvaCajaRV2";
import type { MarcaOrigen, MesProyeccion, Proyeccion } from "@/lib/proyeccion";

function mes(m: string, caja: string, extras: Partial<MesProyeccion> = {}): MesProyeccion {
  return {
    mes: m,
    motos: 0,
    cartera: 0,
    recaudo_credito: "0",
    cuotas_iniciales: "0",
    ingreso_bruto: "0",
    neto: "0",
    provision: "0",
    gastos_fijos: "0",
    gps: "0",
    costo_nueva: "0",
    adelanto: "0",
    pago_inventario: "0",
    fondeo: "0",
    int_deuda: "0",
    iva: "0",
    aval: "0",
    mora: "0",
    recuperacion: "0",
    default: "0",
    egresos: "0",
    flujo: "0",
    caja,
    estado: "ok",
    ...extras,
  };
}

// Proyección de 6 meses con:
//   · 2026-07 (caja $200M) — anclado (real)
//   · 2026-08 ($180M) — sobre el umbral de atención ($100M), NO valle
//   · 2026-09 ($90M), 2026-10 ($60M) — bajo el umbral ($100M): racha de 2 meses
//     (perforan el atención pero solo oct baja del crítico $50M)
//   · 2026-11 ($150M), 2026-12 ($200M) — recuperación
//
// El "valle" es la racha 2026-09 → 2026-10 (2 meses).
function proyeccion(overrides: Partial<Proyeccion> = {}): Proyeccion {
  const anclado: Record<string, MarcaOrigen> = {
    "2026-07": "cerrado",
  };
  return {
    escenario: "base",
    caja_minima: "50000000",
    caja_atencion: "100000000",
    fondo_provision: [],
    piso_caja: "60000000",
    mes_mas_ajustado: "2026-10",
    meses_bajo_minimo: 0,
    caja_final: "200000000",
    capital_requerido: "0",
    runway_meses: null,
    ventana_reconciliada: null,
    interes_obligaciones: {},
    meses_anclados: anclado,
    meses: [
      mes("2026-07", "200000000", { ingreso_bruto: "30000000", egresos: "-20000000", flujo: "10000000" }),
      mes("2026-08", "180000000"),
      mes("2026-09", "90000000"),
      mes("2026-10", "60000000"),
      mes("2026-11", "150000000"),
      mes("2026-12", "200000000"),
    ],
    ...overrides,
  };
}

// ─────────────────────────── AC ───────────────────────────

describe("CurvaCajaRV2 · AC #1 real sólido, proyectado punteado, ancla marcada", () => {
  it("dibuja UN path real (sin dasharray) y UN path proyectado (con dasharray)", () => {
    const { container } = render(<CurvaCajaRV2 data={proyeccion()} />);
    const real = container.querySelector('[data-testid="curva-real"]');
    const proy = container.querySelector('[data-testid="curva-proyectada"]');
    expect(real).toBeInTheDocument();
    expect(proy).toBeInTheDocument();
    expect(real?.getAttribute("stroke-dasharray")).toBeNull();
    // Recharts/attributes en camelCase → getAttribute pasa a kebab.
    expect(proy?.getAttribute("stroke-dasharray")).toBe("6 4");
  });

  it("marca el ancla (círculo con anillo) y escribe «último real» con el monto", () => {
    const { container } = render(<CurvaCajaRV2 data={proyeccion()} />);
    const ancla = container.querySelector('[data-testid="ancla"]');
    expect(ancla).toBeInTheDocument();
    // Monto del ancla es la caja del 2026-07 ($200M, formatCOPCompact).
    const monto = container.querySelector('[data-testid="ancla-monto"]');
    expect(monto?.textContent ?? "").toMatch(/200/);
    // La palabra «último real» está presente.
    expect(container.textContent).toContain("último real");
  });

  it("sin ancla (ningún mes anclado) no dibuja path real ni marca de ancla", () => {
    const p = proyeccion({ meses_anclados: {} });
    const { container } = render(<CurvaCajaRV2 data={p} />);
    expect(container.querySelector('[data-testid="curva-real"]')).toBeNull();
    expect(container.querySelector('[data-testid="ancla"]')).toBeNull();
    // Sigue habiendo proyección para todo el rango.
    expect(container.querySelector('[data-testid="curva-proyectada"]')).toBeInTheDocument();
  });
});

describe("CurvaCajaRV2 · AC #2 umbrales dibujados + valle sombreado + duración", () => {
  it("dibuja los dos umbrales cuando existe caja_atencion", () => {
    const { container } = render(<CurvaCajaRV2 data={proyeccion()} />);
    expect(container.textContent).toContain("atención");
    expect(container.textContent).toContain("crítico");
  });

  it("con caja_atencion=null solo dibuja el crítico (compat RF-F3 sin config)", () => {
    const p = proyeccion({ caja_atencion: null });
    const { container } = render(<CurvaCajaRV2 data={p} />);
    expect(container.textContent).not.toContain("atención");
    expect(container.textContent).toContain("crítico");
  });

  it("sombrea la racha 2026-09→10 y la rotula como «valle · 2 meses»", () => {
    const { container } = render(<CurvaCajaRV2 data={proyeccion()} />);
    expect(container.textContent).toMatch(/valle · 2 meses/);
  });

  it("mes en singular usa «mes», no «meses»", () => {
    // Racha de 1 solo mes bajo atención: solo 2026-09.
    const p: Proyeccion = proyeccion({
      meses: [
        mes("2026-07", "200000000"),
        mes("2026-08", "180000000"),
        mes("2026-09", "90000000"),
        mes("2026-10", "180000000"),
      ],
    });
    const { container } = render(<CurvaCajaRV2 data={p} />);
    expect(container.textContent).toMatch(/valle · 1 mes(?!es)/);
  });
});

describe("CurvaCajaRV2 · AC #3 números en la gráfica (último real + fondo del valle)", () => {
  it("escribe el fondo del valle: mes corto + monto compacto", () => {
    const { container } = render(<CurvaCajaRV2 data={proyeccion()} />);
    const rotulo = container.querySelector('[data-testid="fondo-valle-rotulo"]');
    expect(rotulo).toBeInTheDocument();
    // El fondo es 2026-10 con caja $60M. formatMesCorto lo abrevia; solo verificamos
    // que el monto compacto aparezca.
    expect(rotulo?.textContent ?? "").toMatch(/60/);
  });

  it("cuando la caja NUNCA baja de la referencia, no dibuja rótulo de fondo", () => {
    const p: Proyeccion = proyeccion({
      caja_minima: "10000000",
      caja_atencion: "20000000",
      meses: proyeccion().meses.map((m) => ({ ...m, caja: "200000000" })),
    });
    const { container } = render(<CurvaCajaRV2 data={p} />);
    expect(container.querySelector('[data-testid="fondo-valle"]')).toBeNull();
  });
});

describe("CurvaCajaRV2 · AC #4 tooltip por mes", () => {
  it("hover en un mes muestra el tooltip con caja + composición del punto", () => {
    const { container } = render(<CurvaCajaRV2 data={proyeccion()} />);
    // Antes de hover: sin tooltip.
    expect(container.querySelector('[data-testid="curva-tooltip"]')).toBeNull();
    // Hover sobre 2026-07 (ingreso 30M, egresos -20M, flujo 10M).
    const hover = container.querySelector(
      '[data-testid="hover-2026-07"]',
    ) as SVGRectElement;
    fireEvent.mouseEnter(hover);
    const tip = container.querySelector('[data-testid="curva-tooltip"]');
    expect(tip).toBeInTheDocument();
    expect(tip?.textContent).toMatch(/caja:/);
    expect(tip?.textContent).toMatch(/ingreso:/);
    expect(tip?.textContent).toMatch(/egresos:/);
    expect(tip?.textContent).toMatch(/flujo:/);
  });
});

describe("CurvaCajaRV2 · AC #9 color = solo estado (tokens RV-V1)", () => {
  it("las series usan --color-chart-* (no hex hardcodeado)", () => {
    const { container } = render(<CurvaCajaRV2 data={proyeccion()} />);
    const real = container.querySelector('[data-testid="curva-real"]');
    const proy = container.querySelector('[data-testid="curva-proyectada"]');
    expect(real?.getAttribute("stroke")).toBe("var(--color-chart-real)");
    expect(proy?.getAttribute("stroke")).toBe("var(--color-chart-proyectado)");
  });
});

describe("CurvaCajaRV2 · AC #10 enlazada a los campos reales de Proyeccion", () => {
  it("sin datos (meses=[]) muestra vacío honesto, no números inventados", () => {
    const p = proyeccion({ meses: [] });
    render(<CurvaCajaRV2 data={p} />);
    expect(screen.getByText(/Sin datos para dibujar/)).toBeInTheDocument();
  });
});
