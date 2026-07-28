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
  periodicidadPara,
  puntosComposicion,
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

function serie(n: number, desde = "2026-07"): MesProyeccion[] {
  const [y0, m0] = desde.split("-").map(Number);
  return Array.from({ length: n }, (_, i) => {
    const idx = m0 - 1 + i;
    const y = y0 + Math.floor(idx / 12);
    const m = (idx % 12) + 1;
    return mes({
      mes: `${y}-${String(m).padStart(2, "0")}`,
      caja: `${(i + 1) * 1000000}.00`,
    });
  });
}

describe("egreso — agregación del gráfico (§2/§5)", () => {
  it("elige periodicidad por longitud de la ventana", () => {
    expect(periodicidadPara(18)).toBe("mes");
    expect(periodicidadPara(60)).toBe("trimestre");
    expect(periodicidadPara(180)).toBe("anio");
  });

  it("ventana corta: un punto por mes, sin agregar", () => {
    const p = puntosComposicion(serie(12), null);
    expect(p).toHaveLength(12);
    expect(p[0].etiqueta).toBe("jul-26");
  });

  it("trimestral: agrupa y SUMA los buckets (en Decimal); caja es la del cierre", () => {
    // 30 meses desde jul-26: jul-sep-26 = T3-26 (3 meses)
    const p = puntosComposicion(serie(30), null, "trimestre");
    expect(p[0].etiqueta).toBe("T3-26");
    // ingreso del trimestre = 3 × 34M, exacto en Decimal
    expect(p[0].ingreso.toFixed(2)).toBe("102000000.00");
    // caja al cierre = la del 3er mes (i=2 → 3.000.000)
    expect(p[0].caja.toFixed(2)).toBe("3000000.00");
  });

  it("anual: un punto por año", () => {
    const p = puntosComposicion(serie(30), null, "anio");
    expect(p.map((x) => x.etiqueta)).toEqual(["2026", "2027", "2028"]);
  });

  it("candado del invariante en la ruta AGREGADA (trimestre y año)", () => {
    // el invariante ingreso − (costo + gasto) == flujo debe sobrevivir a la suma
    // por período: si un bucket se acumula mal, aquí se cae (no solo en mensual).
    for (const modo of ["trimestre", "anio"] as const) {
      for (const p of puntosComposicion(serie(24), null, modo)) {
        expect(p.ingreso.minus(p.costo.plus(p.gasto)).equals(p.flujo)).toBe(
          true,
        );
      }
    }
  });

  it("marca el período real si algún mes cae en la ventana reconciliada", () => {
    const p = puntosComposicion(serie(12), ["2026-09", "2026-09"], "trimestre");
    // T3-26 contiene sep-26 → real
    expect(p[0].real).toBe(true);
    expect(p[1].real).toBe(false);
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
