// Titular de /iva (§3①) — la CONCLUSIÓN del período. Cuatro variantes; la del §2
// (recibidas sin decidir) tiene PRECEDENCIA: advierte ANTES de mostrar la cifra.
// Cero aritmética: todo viene del backend.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TitularIva } from "@/components/iva/TitularIva";
import type { FacturaRow } from "@/lib/facturas";
import type { LiquidacionIva, PeriodoIva } from "@/lib/iva";

const HOY = new Date(2026, 6, 15); // C2-2026 (may–ago)

function factura(over: Partial<FacturaRow>): FacturaRow {
  return {
    id: "x",
    tipo: "compra",
    origen: "auteco",
    numero: "FC-1",
    tercero_nombre: "Auteco",
    tercero_nit: "860024781",
    tipo_contribuyente: "persona_juridica",
    fecha: "2026-05-28",
    base_gravable: null,
    total_bruto: "1000000.00",
    tarifa_iva: null,
    iva_valor: "190000.00",
    total: "1190000.00",
    deducible: true,
    deducible_decidido: true,
    activo: true,
    periodo: "2026-C2",
    ...over,
  };
}

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

function renderTitular(liq: LiquidacionIva, facturas: FacturaRow[]) {
  render(<TitularIva liquidacion={liq} facturas={facturas} hoy={HOY} />);
}

describe("TitularIva", () => {
  it("recibidas sin decidir: advierte ANTES de dar la cifra (§2, precedencia)", () => {
    renderTitular({ periodicidad: "cuatrimestral", periodos: [periodo({})] }, [
      factura({ deducible: false, deducible_decidido: false }),
    ]);
    expect(
      screen.getByText(/Faltan 1 factura por revisar/i),
    ).toBeInTheDocument();
    // NO muestra la cifra a pagar mientras la liquidación es provisional
    expect(screen.queryByText(/pagarías/i)).not.toBeInTheDocument();
  });

  it("confiable con saldo a favor", () => {
    renderTitular(
      {
        periodicidad: "cuatrimestral",
        periodos: [
          periodo({ neto_a_pagar: "0.00", saldo_favor_nuevo: "11001452.94" }),
        ],
      },
      [factura({})],
    );
    expect(screen.getByText(/Quedas con saldo a favor/i)).toBeInTheDocument();
  });

  it("confiable, hay que pagar", () => {
    renderTitular({ periodicidad: "cuatrimestral", periodos: [periodo({})] }, [
      factura({}),
    ]);
    expect(screen.getByText(/pagarías/i)).toBeInTheDocument();
    expect(screen.getByText(/a la DIAN/i)).toBeInTheDocument();
  });

  it("línea de completitud sin 'última carga' + línea de honestidad de la compuerta", () => {
    renderTitular({ periodicidad: "cuatrimestral", periodos: [periodo({})] }, [
      factura({}),
    ]);
    expect(screen.getByText(/Cuatrimestre may–ago 2026/i)).toBeInTheDocument();
    expect(screen.getByText(/1 factura cargada/i)).toBeInTheDocument();
    // la cláusula retirada por el CEO no aparece
    expect(screen.queryByText(/última carga/i)).not.toBeInTheDocument();
    // honestidad: la liquidación aún no alimenta la proyección (compuerta apagada)
    expect(
      screen.getByText(/no está incorporada a la proyección/i),
    ).toBeInTheDocument();
  });
});
