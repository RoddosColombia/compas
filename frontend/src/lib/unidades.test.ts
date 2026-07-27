// C3 §6.2 — ida y vuelta de unidades sin pérdida y sin float.

import { describe, expect, it } from "vitest";

import {
  esMontoHumanoValido,
  fraccionAPct,
  indiceAMes,
  mesAIndice,
  montoACanonico,
  montoAHumano,
  pctAFraccion,
  pctAnualEquivalente,
  resumenHorizonte,
} from "@/lib/unidades";

describe("porcentajes humano ↔ fracción", () => {
  it("5 (%) ↔ '0.05' sin pérdida", () => {
    expect(pctAFraccion("5")).toBe("0.05");
    expect(fraccionAPct("0.05")).toBe("5");
    expect(fraccionAPct(pctAFraccion("1.6"))).toBe("1.6");
  });

  it("acepta coma decimal humana: '1,6' → '0.016'", () => {
    expect(pctAFraccion("1,6")).toBe("0.016");
  });

  it("equivalente anual compuesto: 5 %/mes ≈ 79,6 % anual", () => {
    expect(pctAnualEquivalente("0.05")).toBe("79.6");
    expect(pctAnualEquivalente("0.03")).toBe("42.6");
  });
});

describe("montos humano ↔ canónico", () => {
  it("1.200.000 ↔ '1200000' sin pérdida", () => {
    expect(montoACanonico("1.200.000")).toBe("1200000");
    expect(montoACanonico("1200000")).toBe("1200000");
    expect(montoAHumano("1200000")).toBe("1.200.000");
    expect(montoACanonico(montoAHumano("692005"))).toBe("692005");
  });

  it("acepta decimales con coma: '1.200.000,50'", () => {
    expect(montoACanonico("1.200.000,50")).toBe("1200000.5");
  });

  it("valida el formato humano", () => {
    expect(esMontoHumanoValido("1.200.000")).toBe(true);
    expect(esMontoHumanoValido("1200000")).toBe(true);
    expect(esMontoHumanoValido("12.34.5")).toBe(false);
    expect(esMontoHumanoValido("abc")).toBe(false);
  });
});

describe("mes calendario ↔ índice del motor", () => {
  it("índice 2 desde jul-2026 es sep-2026, y de vuelta", () => {
    expect(indiceAMes(2, "2026-07")).toBe("2026-09");
    expect(mesAIndice("2026-09", "2026-07")).toBe(2);
    expect(mesAIndice(indiceAMes(17, "2026-07"), "2026-07")).toBe(17);
  });

  it("cruza el año sin perderse", () => {
    expect(indiceAMes(6, "2026-10")).toBe("2027-04");
    expect(mesAIndice("2027-04", "2026-10")).toBe(6);
  });
});

describe("resumen de horizonte", () => {
  it("144 meses desde jul-26 → '12 años, jul-26 → jun-38'", () => {
    expect(resumenHorizonte(144, "2026-07")).toBe("12 años, jul-26 → jun-38");
  });
});
