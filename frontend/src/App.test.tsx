import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import App from "@/App";
import { MAX_BYTES, validarArchivo } from "@/lib/cargas";
import { formatCOP, formatFecha } from "@/lib/money";

describe("App (shell con router y auth)", () => {
  it("sin sesión termina en el login", async () => {
    render(<App />);
    // La restauración de sesión falla (sin backend en jsdom) → /login.
    expect(
      await screen.findByRole("heading", { name: "COMPAS" }),
    ).toBeInTheDocument();
    expect(await screen.findByLabelText("Correo")).toBeInTheDocument();
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

describe("cargas — validación F-22 en cliente (espejo del backend)", () => {
  it("acepta .xlsx y .xls dentro del límite", () => {
    expect(validarArchivo("extracto.xlsx", 1024)).toBeNull();
    expect(validarArchivo("EXTRACTO.XLS", 1024)).toBeNull();
  });

  it("rechaza .xlsm (macros) siempre", () => {
    expect(validarArchivo("macro.xlsm", 10)).toMatch(/xlsm/);
  });

  it("rechaza extensiones desconocidas", () => {
    expect(validarArchivo("datos.csv", 10)).toMatch(/no soportada/);
  });

  it("rechaza archivos de más de 10 MB", () => {
    expect(validarArchivo("grande.xlsx", MAX_BYTES + 1)).toMatch(/10 MB/);
  });
});
