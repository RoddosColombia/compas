// ComposicionFlujoRV2 — RV-V2 Fundacional §3 AC #8.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ComposicionFlujoRV2 } from "@/components/charts/ComposicionFlujoRV2";
import type { MesProyeccion } from "@/lib/proyeccion";

function mes(m: string, over: Partial<MesProyeccion> = {}): MesProyeccion {
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
    caja: "100000000",
    estado: "ok",
    ...over,
  };
}

const MESES: MesProyeccion[] = [
  mes("2026-07", {
    ingreso_bruto: "30000000",
    gastos_fijos: "-15000000",
    pago_inventario: "-5000000",
    gps: "-2000000",
    flujo: "8000000",
  }),
  mes("2026-08", {
    ingreso_bruto: "25000000",
    gastos_fijos: "-15000000",
    pago_inventario: "-10000000",
    gps: "-1000000",
    flujo: "-1000000",
  }),
  mes("2026-09", {
    ingreso_bruto: "20000000",
    gastos_fijos: "-12000000",
    pago_inventario: "-3000000",
    iva: "-1000000",
    flujo: "4000000",
  }),
];

// ─────────────────────────── AC #8 ───────────────────────────

describe("ComposicionFlujoRV2 · AC #8 gráfica propia (no franja)", () => {
  it("dibuja UN grupo de barras por cada mes de la ventana", () => {
    const { container } = render(<ComposicionFlujoRV2 meses={MESES} />);
    expect(
      container.querySelectorAll('[data-testid^="comp-bar-"]'),
    ).toHaveLength(3);
  });

  it("cada mes tiene 4 barras: ingreso (arriba) + 3 egresos apilados", () => {
    const { container } = render(<ComposicionFlujoRV2 meses={MESES} />);
    for (const m of ["2026-07", "2026-08", "2026-09"]) {
      expect(container.querySelector(`[data-testid="bar-ingreso-${m}"]`)).not.toBeNull();
      expect(container.querySelector(`[data-testid="bar-gasto-fijo-${m}"]`)).not.toBeNull();
      expect(container.querySelector(`[data-testid="bar-auteco-${m}"]`)).not.toBeNull();
      expect(container.querySelector(`[data-testid="bar-otros-${m}"]`)).not.toBeNull();
    }
  });

  it("la barra de INGRESO nace en el cero y va HACIA ARRIBA (y_final < zero)", () => {
    const { container } = render(<ComposicionFlujoRV2 meses={MESES} />);
    // La estrategia: la y de la barra de ingreso debe ser menor que la y del cero
    // (el cero se ubica sobre el que arrancan los egresos).
    const ing = container.querySelector('[data-testid="bar-ingreso-2026-07"]');
    const gf = container.querySelector('[data-testid="bar-gasto-fijo-2026-07"]');
    const yIng = Number(ing?.getAttribute("y"));
    const yGF = Number(gf?.getAttribute("y"));
    expect(yIng).toBeLessThan(yGF);
  });

  it("los egresos se apilan (auteco arranca donde termina gasto-fijo)", () => {
    const { container } = render(<ComposicionFlujoRV2 meses={MESES} />);
    const gf = container.querySelector('[data-testid="bar-gasto-fijo-2026-07"]');
    const aut = container.querySelector('[data-testid="bar-auteco-2026-07"]');
    const yGF = Number(gf?.getAttribute("y"));
    const hGF = Number(gf?.getAttribute("height"));
    const yAut = Number(aut?.getAttribute("y"));
    // Auteco arranca ~ yGF + hGF (con los +2 de separación en el código).
    expect(yAut).toBeGreaterThanOrEqual(yGF + hGF);
  });

  it("dibuja la LÍNEA de flujo neto encima (path continuo con N puntos)", () => {
    const { container } = render(<ComposicionFlujoRV2 meses={MESES} />);
    const linea = container.querySelector('[data-testid="linea-flujo-neto"]');
    expect(linea).toBeInTheDocument();
    // Path con 3 puntos ⇒ 1 "M" + 2 "L" ⇒ 2 comandos L.
    const d = linea?.getAttribute("d") ?? "";
    expect(d.startsWith("M ")).toBe(true);
    expect((d.match(/ L /g) ?? []).length).toBe(2);
  });

  it("la leyenda muestra los 5 conceptos (4 conceptos + neto)", () => {
    render(<ComposicionFlujoRV2 meses={MESES} />);
    expect(screen.getByText(/ingreso neto/i)).toBeInTheDocument();
    expect(screen.getByText(/gastos fijos/i)).toBeInTheDocument();
    expect(screen.getByText(/inventario auteco/i)).toBeInTheDocument();
    expect(screen.getByText(/otros egresos/i)).toBeInTheDocument();
    expect(screen.getByText(/flujo neto/i)).toBeInTheDocument();
  });
});

describe("ComposicionFlujoRV2 · AC #9 color = solo estado (tokens RV-V1)", () => {
  it("las 4 barras usan --color-chart-* (no hex hardcodeado)", () => {
    const { container } = render(<ComposicionFlujoRV2 meses={MESES} />);
    expect(
      container.querySelector('[data-testid="bar-ingreso-2026-07"]')?.getAttribute("fill"),
    ).toBe("var(--color-chart-ingreso)");
    expect(
      container.querySelector('[data-testid="bar-gasto-fijo-2026-07"]')?.getAttribute("fill"),
    ).toBe("var(--color-chart-gasto-fijo)");
    expect(
      container.querySelector('[data-testid="bar-auteco-2026-07"]')?.getAttribute("fill"),
    ).toBe("var(--color-chart-auteco)");
    expect(
      container.querySelector('[data-testid="bar-otros-2026-07"]')?.getAttribute("fill"),
    ).toBe("var(--color-chart-otros)");
  });
});

describe("ComposicionFlujoRV2 · AC #10 datos reales", () => {
  it("sin datos muestra vacío honesto, no barras vacías", () => {
    render(<ComposicionFlujoRV2 meses={[]} />);
    expect(screen.getByText(/Sin datos para dibujar/)).toBeInTheDocument();
  });

  it("respeta la ventana (`ventanaMeses` acota los meses visibles)", () => {
    const { container } = render(
      <ComposicionFlujoRV2 meses={MESES} ventanaMeses={2} />,
    );
    expect(
      container.querySelectorAll('[data-testid^="comp-bar-"]'),
    ).toHaveLength(2);
    // El 3º mes NO debe aparecer.
    expect(container.querySelector('[data-testid="comp-bar-2026-09"]')).toBeNull();
  });
});
