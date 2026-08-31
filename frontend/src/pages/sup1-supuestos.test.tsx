// SUP-1 (CEO 2026-08-17) — frontend de las dos capacidades nuevas:
//  · el SEGUNDO TRAMO de crecimiento se canoniza a null/null cuando está vacío
//    (un solo tramo) y a fracción + entero cuando el CEO lo llena;
//  · la gráfica se puede FILTRAR POR TIEMPO con granularidad corta (3/6/9/12/15)
//    además de las ventanas largas — en Proyecciones y también en Inicio.

import { describe, expect, it } from "vitest";

import { OPCIONES_HORIZONTE } from "@/components/ui/filtro-barra";
import { tramo2ACanonico } from "@/pages/DatosPage";

describe("SUP-1 · segundo tramo de crecimiento", () => {
  it("vacío = un solo tramo (null/null, comportamiento histórico)", () => {
    expect(tramo2ACanonico({ tasa: "", corte: "" })).toEqual({
      crec_pct_mensual_2: null,
      crec_mes_corte: null,
    });
    expect(tramo2ACanonico({ tasa: "  ", corte: "  " })).toEqual({
      crec_pct_mensual_2: null,
      crec_mes_corte: null,
    });
  });

  it("el % humano viaja como fracción canónica y el corte como entero", () => {
    expect(tramo2ACanonico({ tasa: "3", corte: "18" })).toEqual({
      crec_pct_mensual_2: "0.03",
      crec_mes_corte: 18,
    });
  });

  it("acepta la coma decimal de es-CO", () => {
    expect(
      tramo2ACanonico({ tasa: "2,5", corte: "24" }).crec_pct_mensual_2,
    ).toBe("0.025");
  });
});

describe("SUP-1 · filtro de tiempo de la gráfica", () => {
  it("ofrece la granularidad corta pedida por el CEO", () => {
    const valores = OPCIONES_HORIZONTE.map((o) => o.valor);
    for (const v of ["3", "6", "9", "12", "15"]) {
      expect(valores).toContain(v);
    }
  });

  it("conserva las ventanas largas de decisión estructural", () => {
    // RV-V2 · Fundacional §3 AC #6 + RF-F10 · Fundacional §2: la escala
    // combinada tras rebase es 3·6·9·12·15·18·30·42·54·60·120·240. El «todo»
    // pasó a 240 (20 años) con RF-F10; ya no hay «180» como opción.
    const valores = OPCIONES_HORIZONTE.map((o) => o.valor);
    for (const v of ["18", "30", "60", "240"]) {
      expect(valores).toContain(v);
    }
  });

  it("las opciones están en orden creciente (no confunde al leer)", () => {
    const nums = OPCIONES_HORIZONTE.map((o) => Number(o.valor));
    expect([...nums].sort((a, b) => a - b)).toEqual(nums);
  });
});
