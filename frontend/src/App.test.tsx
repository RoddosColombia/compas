import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import App from "@/App";
import { formatCOP, formatFecha } from "@/lib/money";

describe("App (esqueleto Sesion 1)", () => {
  it("renderiza el titulo COMPAS", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: "COMPAS" })).toBeInTheDocument();
  });
});

describe("money — regla 1 (formato es-CO, nunca Number sobre montos)", () => {
  it("formatea un monto-string como COP con separadores es-CO", () => {
    // Intl inserta un espacio especial (NBSP/narrow) entre $ y el numero;
    // normalizamos cualquier whitespace para no acoplarnos al code point.
    const out = formatCOP("1234567.89").replace(/\s/g, " ");
    expect(out).toBe("$ 1.234.567,89");
  });

  it("formatea fecha YYYY-MM-DD como dd-mmm-aaaa", () => {
    expect(formatFecha("2026-07-18")).toBe("18-jul-2026");
  });
});
