// F1 §3 — política de formato numérico es-CO: abreviado para cifras
// protagonistas (M / mil M, 1 decimal), delta con signo y flecha. Sin float:
// el redondeo lo decide Decimal; Intl SOLO presenta. Casos = tabla del sistema.

import Decimal from "decimal.js-light";
import { describe, expect, it } from "vitest";

import { formatCOPCompact, formatDelta, formatMesCorto } from "@/lib/money";

describe("formatCOPCompact — abreviación por magnitud (tabla §3)", () => {
  it("millones con 1 decimal: -$ 63,9 M", () => {
    expect(formatCOPCompact("-63897875.14")).toBe("-$ 63,9 M");
    expect(formatCOPCompact("63897875.14")).toBe("$ 63,9 M");
  });

  it("miles de millones se quedan en M hasta 1e10: $ 1.284 M", () => {
    expect(formatCOPCompact("1284000000")).toBe("$ 1.284 M");
  });

  it("desde 1e10 pasa a mil M: $ 95,9 mil M", () => {
    expect(formatCOPCompact("95900000000")).toBe("$ 95,9 mil M");
  });

  it("bajo el millón va completo sin decimales", () => {
    expect(formatCOPCompact("850000")).toBe("$ 850.000");
    expect(formatCOPCompact("0")).toBe("$ 0");
  });

  it("redondea con Decimal (HALF_UP), no con float", () => {
    expect(formatCOPCompact("1250000")).toBe("$ 1,3 M");
    expect(formatCOPCompact(new Decimal("29999999.99"))).toBe("$ 30 M");
  });
});

describe("formatDelta — signo + flecha (§3 comparación)", () => {
  it("positivo sube con ▲", () => {
    expect(formatDelta("12900000")).toEqual({
      texto: "▲ +$ 12,9 M",
      direccion: "sube",
    });
  });

  it("negativo baja con ▼", () => {
    expect(formatDelta("-93900000")).toEqual({
      texto: "▼ -$ 93,9 M",
      direccion: "baja",
    });
  });

  it("cero es igual con —", () => {
    expect(formatDelta("0")).toEqual({
      texto: "— sin cambio",
      direccion: "igual",
    });
  });
});

describe("formatMesCorto — mmm-aa para ejes y anotaciones", () => {
  it("convierte YYYY-MM", () => {
    expect(formatMesCorto("2027-05")).toBe("may-27");
    expect(formatMesCorto("2026-12")).toBe("dic-26");
  });
});
