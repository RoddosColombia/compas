// Tarjeta de liquidación (§3③): desglose en el orden del cálculo, nunca un pago
// negativo, próximo pago DIAN, y selector HONESTO (período sin facturas dice "sin
// facturas cargadas", no "$ 0,00"). Cero aritmética: los totales vienen del backend.

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LiquidacionCard } from "@/components/iva/LiquidacionCard";
import type { LiquidacionIva, PeriodoIva } from "@/lib/iva";

function periodo(over: Partial<PeriodoIva>): PeriodoIva {
  return {
    anio: 2026,
    periodo: 2,
    etiqueta: "2026-C2",
    generado: "15000000.00",
    descontable: "2000000.00",
    saldo: "13000000.00",
    saldo_favor_previo: "0.00",
    neto_a_pagar: "13000000.00",
    saldo_favor_nuevo: "0.00",
    proximo_pago: null,
    ...over,
  };
}

// hoy en C2-2026 (jul) → el período en curso es 2026-C2
const HOY = new Date(2026, 6, 15);

function renderCard(liq: LiquidacionIva) {
  render(<LiquidacionCard liquidacion={liq} hoy={HOY} />);
}

describe("LiquidacionCard", () => {
  it("desglosa en el orden del cálculo y muestra 'A pagar'", () => {
    renderCard({ periodicidad: "cuatrimestral", periodos: [periodo({})] });
    expect(screen.getByText(/IVA generado/i)).toBeInTheDocument();
    expect(screen.getByText(/IVA descontable/i)).toBeInTheDocument();
    expect(screen.getByText(/Subtotal del período/i)).toBeInTheDocument();
    expect(screen.getByText(/A pagar/i)).toBeInTheDocument();
  });

  it("nunca un pago negativo: descontable > generado → saldo a favor y A pagar $ 0,00", () => {
    renderCard({
      periodicidad: "cuatrimestral",
      periodos: [
        periodo({
          neto_a_pagar: "0.00",
          saldo_favor_nuevo: "11001452.94",
          saldo: "-11001452.94",
        }),
      ],
    });
    expect(
      screen.getByText(/saldo a favor que se arrastra/i),
    ).toBeInTheDocument();
    // la fila "A pagar" muestra 0, nunca un negativo (§8.1)
    const aPagar = screen.getByTestId("a-pagar").textContent ?? "";
    expect(aPagar).not.toContain("-");
  });

  it("muestra el próximo pago DIAN con los días", () => {
    renderCard({
      periodicidad: "cuatrimestral",
      periodos: [periodo({ proximo_pago: { fecha: "2026-09-10", dias: 42 } })],
    });
    expect(screen.getByText(/Próximo pago/i)).toBeInTheDocument();
    expect(screen.getByText(/septiembre de 2026/i)).toBeInTheDocument();
    expect(screen.getByText(/42 días/i)).toBeInTheDocument();
  });

  it("selector honesto: un período sin facturas dice 'sin facturas cargadas', no $ 0,00", () => {
    // solo C2 tiene facturas; C1 (sintetizado) no
    renderCard({ periodicidad: "cuatrimestral", periodos: [periodo({})] });
    fireEvent.click(screen.getByRole("button", { name: /ene.*abr 2026/i }));
    expect(screen.getByText(/sin facturas cargadas/i)).toBeInTheDocument();
    expect(screen.queryByText(/A pagar/i)).not.toBeInTheDocument();
  });
});
