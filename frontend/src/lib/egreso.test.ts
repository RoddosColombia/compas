// frontend/src/lib/egreso.test.ts
//
// V1 "Ver el egreso" — los dos candados del sprint:
//  1) Invariante: para cada mes, ingreso − (costo + gasto) == flujo AL PESO,
//     incluida la ventana reconciliada. Si no cuadra, el MAPEO está mal
//     (se corrige el mapeo, nunca el número).
//  2) Anti-doble-conteo (§1): el interés real de las facturas YA viaja dentro
//     de `fondeo` (y por tanto ya está en Costo). `interes_obligaciones` expone
//     ese mismo interés solo para mostrarlo — jamás se suma a los buckets.

import { describe, expect, it } from "vitest";

import {
  autecoDeMes,
  bucketsMes,
  interesConcuerda,
  totales,
} from "@/lib/egreso";
import type { MesProyeccion } from "@/lib/proyeccion";

function mes(over: Partial<MesProyeccion>): MesProyeccion {
  return {
    mes: "2026-10",
    motos: 50,
    cartera: 120,
    recaudo_credito: "30000000.00",
    cuotas_iniciales: "4000000.00",
    ingreso_bruto: "34000000.00",
    neto: "34000000.00",
    provision: "0.00",
    gastos_fijos: "-125000000.00",
    gps: "-4000000.00",
    costo_nueva: "-3000000.00",
    adelanto: "0.00",
    pago_inventario: "0.00",
    fondeo: "0.00",
    int_deuda: "-300000.00",
    iva: "0.00",
    egresos: "-132300000.00",
    flujo: "-98300000.00",
    caja: "40000000.00",
    estado: "critico",
    ...over,
  };
}

// Mes normal (Auteco paramétrico en 0): flujo = 34M − 125M − 4M − 3M − 0,3M.
const NORMAL = mes({});

// Mes reconciliado: factura Auteco $180 M paga este mes, plazo 150 → interés
// real 1,6%×2 = $5,76 M dentro de fondeo; capital $180 M en pago_inventario.
const RECONCILIADO = mes({
  mes: "2027-01",
  pago_inventario: "-180000000.00",
  fondeo: "-5760000.00",
  flujo: "-284060000.00", // 34M −180M −5,76M −3M −125M −4M −0,3M
});

describe("egreso — candado 1: invariante ingreso − (costo + gasto) == flujo", () => {
  it("mes normal: los tres buckets reconcilian con el flujo al peso", () => {
    const b = bucketsMes(NORMAL);
    expect(b.ingreso.minus(b.costo.plus(b.gasto)).toFixed(2)).toBe(
      "-98300000.00",
    );
    expect(b.ingreso.minus(b.costo.plus(b.gasto)).equals(b.flujo)).toBe(true);
  });

  it("mes reconciliado: cuadra igual (el Auteco real ya está en costo)", () => {
    const b = bucketsMes(RECONCILIADO);
    expect(b.ingreso.minus(b.costo.plus(b.gasto)).equals(b.flujo)).toBe(true);
    // el capital del lote real vive en costo (pago_inventario), no en gasto
    expect(b.costo.toFixed(2)).toBe("188760000.00"); // 180M + 5,76M + 3M
    expect(b.gasto.toFixed(2)).toBe("129300000.00"); // 125M + 4M + 0,3M
  });

  it("totales de la ventana reconcilian con la suma de flujos", () => {
    const t = totales([NORMAL, RECONCILIADO]);
    const flujoTotal = t.ingreso.minus(t.costo.plus(t.gasto));
    expect(flujoTotal.toFixed(2)).toBe("-382360000.00"); // −98,3M − 284,06M
    expect(flujoTotal.equals(t.flujo)).toBe(true);
  });
});

describe("egreso — porción Auteco (hover del gráfico)", () => {
  it("suma lote + fondeo como magnitud positiva", () => {
    expect(autecoDeMes(RECONCILIADO).toFixed(2)).toBe("185760000.00"); // 180M + 5,76M
  });

  it("es cero cuando no hay Auteco paramétrico ni real", () => {
    expect(autecoDeMes(NORMAL).toFixed(2)).toBe("0.00");
  });
});

describe("egreso — candado 2: anti-doble-conteo del interés", () => {
  it("interes_obligaciones[mes] == |fondeo[mes]| en el mes de pago", () => {
    const interes = { "2027-01": "5760000.00" };
    expect(interesConcuerda(RECONCILIADO, interes)).toBe(true);
  });

  it("un interés que NO coincide con |fondeo| se detecta (mapeo roto)", () => {
    const interes = { "2027-01": "9999999.00" };
    expect(interesConcuerda(RECONCILIADO, interes)).toBe(false);
  });

  it("meses sin entrada en interes_obligaciones no se evalúan (true)", () => {
    // fuera de la ventana fondeo es paramétrico y no hay entrada: no aplica
    expect(interesConcuerda(NORMAL, {})).toBe(true);
  });

  it("el interés NO se suma a los buckets: costo ya lo contiene vía fondeo", () => {
    // sin interes_obligaciones vs con él, los buckets son idénticos
    const b = bucketsMes(RECONCILIADO);
    expect(b.costo.toFixed(2)).toBe("188760000.00");
    // el interés (5,76M) está DENTRO de costo, no es un sumando aparte
    expect(b.costo.greaterThan("5760000")).toBe(true);
  });
});
