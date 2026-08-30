// frontend/src/design-tokens.test.ts
//
// RV-V1 · Fundacional §3 — DESIGN.md con paleta de marca como TOKENS. Este
// test es el candado en CI contra la regresión silenciosa (alguien borra un
// token de `index.css` y RV-V2 rompe sin ruido).
//
// Lee `src/index.css` como TEXTO ESTÁTICO (no depende de jsdom + Tailwind, que
// no compila `@theme` en tiempo de test), y verifica que:
//   1. Los 7 tokens de rol de gráfico están declarados en el `@theme` block.
//   2. Los tokens de marca y del semáforo semántico (que RV-V1 documenta como
//      dependencias del contrato de gráficos) siguen presentes.
//
// Si un token cambia de HEX, el test NO falla — se afinarán en RV-V3 (tweakcn).
// Falla solo si el token DESAPARECE del contrato.

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// Ruta relativa al cwd de vitest (frontend/). Estable en CI y local.
const INDEX_CSS = readFileSync(join("src", "index.css"), "utf-8");

// Tokens de MARCA que DESIGN.md (§2.1/2.2/2.4) usa como fuente de los `--chart-*`.
// Si alguno de estos se va, RV-V1 pierde su contrato de derivación.
const TOKENS_DEPENDENCIA = [
  "--color-cyan",
  "--color-positivo",
  "--color-atencion",
  "--color-critico",
  "--color-ink",
  "--color-hairline",
];

// Tokens de ROL DE GRÁFICO (RV-V1 §3): los que RV-V2 va a consumir directo.
const TOKENS_CHART = [
  "--color-chart-real",
  "--color-chart-proyectado",
  "--color-chart-escenario",
  "--color-chart-ingreso",
  "--color-chart-gasto-fijo",
  "--color-chart-auteco",
  "--color-chart-otros",
];

function declara(token: string): boolean {
  // La declaración vive dentro de `@theme { ... }` como `--token: valor;`.
  const re = new RegExp(`^\\s*${token}\\s*:`, "m");
  return re.test(INDEX_CSS);
}

describe("RV-V1 · tokens de gráfico en index.css", () => {
  it("las dependencias del contrato (marca + semáforo + neutros) están declaradas", () => {
    const faltan = TOKENS_DEPENDENCIA.filter((t) => !declara(t));
    expect(faltan).toEqual([]);
  });

  it("los 7 tokens de rol de gráfico están declarados (contrato para RV-V2)", () => {
    const faltan = TOKENS_CHART.filter((t) => !declara(t));
    expect(faltan).toEqual([]);
  });

  it("regla 9: los categóricos de composición NO usan hex del semáforo semántico", () => {
    // Los tokens categóricos que declara RV-V1 NO deben ser identificos al hex
    // de crítico (#b91c1c) o atención (#b45309). Ingreso sí puede ser positivo
    // (por diseño — arriba del cero es la única categoría que toca el verde).
    const hexCritico = /--color-chart-(gasto-fijo|auteco|otros)\s*:\s*#b91c1c/i;
    const hexAtencion = /--color-chart-(gasto-fijo|auteco|otros)\s*:\s*#b45309/i;
    expect(INDEX_CSS).not.toMatch(hexCritico);
    expect(INDEX_CSS).not.toMatch(hexAtencion);
  });
});
