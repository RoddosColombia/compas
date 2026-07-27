import { describe, expect, it } from "vitest";

import { cruceTecho } from "./techo";

describe("cruceTecho (D2 Pieza 0 — techo × ejecutado del mes)", () => {
  it("dentro del presupuesto: positivo, techo intacto", () => {
    const r = cruceTecho("80000000", "100000000", "20000000", 50);
    expect(r.estado).toBe("positivo");
    expect(r.sobreActual).toBe("0.00");
    expect(r.disponibleTecho).toBe("20000000.00");
    expect(r.pctConsumido).toBe(0);
    expect(r.excede).toBe(false);
  });

  it("sobre-gasto pero el ritmo NO supera el techo: atención", () => {
    // $5 M sobre el presupuesto al 50% del mes → proyecta $10 M < techo $20 M
    const r = cruceTecho("105000000", "100000000", "20000000", 50);
    expect(r.estado).toBe("atencion");
    expect(r.sobreActual).toBe("5000000.00");
    expect(r.ritmoSobre).toBe("10000000.00");
    expect(r.excede).toBe(false);
    expect(r.disponibleTecho).toBe("15000000.00");
  });

  it("el ritmo proyectado SUPERA el techo: crítico, indica en cuánto", () => {
    // $15 M sobre el presupuesto al 50% → proyecta $30 M > techo $20 M
    const r = cruceTecho("115000000", "100000000", "20000000", 50);
    expect(r.estado).toBe("critico");
    expect(r.ritmoSobre).toBe("30000000.00");
    expect(r.excede).toBe(true);
    expect(r.exceso).toBe("10000000.00"); // $30 M − $20 M
  });

  it("umbral exacto: ritmo == techo no excede (crítico solo si lo supera)", () => {
    // $10 M sobre al 50% → proyecta $20 M == techo $20 M → NO excede
    const r = cruceTecho("110000000", "100000000", "20000000", 50);
    expect(r.excede).toBe(false);
    expect(r.estado).toBe("atencion");
  });

  it("mes futuro (0% transcurrido): no divide por cero; ritmo = sobre actual", () => {
    const r = cruceTecho("105000000", "100000000", "20000000", 0);
    expect(r.ritmoSobre).toBe("5000000.00");
    expect(r.excede).toBe(false);
  });

  it("techo 0 (sin holgura): cualquier sobre-gasto es crítico, pct null", () => {
    const r = cruceTecho("101000000", "100000000", "0", 50);
    expect(r.pctConsumido).toBeNull();
    expect(r.estado).toBe("critico"); // ritmo $2 M > techo $0
    expect(r.excede).toBe(true);
  });

  it("pctConsumido se calcula sobre el techo", () => {
    const r = cruceTecho("110000000", "100000000", "20000000", 100);
    expect(r.sobreActual).toBe("10000000.00");
    expect(r.pctConsumido).toBe(50); // $10 M de $20 M
  });
});
