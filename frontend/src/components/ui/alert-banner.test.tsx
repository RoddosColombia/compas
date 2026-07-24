// AlertBanner: franja de estado del cockpit (ok=verde, warn=ámbar, danger=rojo).
// La variante peligro es la ÚNICA que usa rojo (perforación de caja) → se prueba
// que expone role=alert; las demás, role=status.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AlertBanner } from "@/components/ui/alert-banner";

describe("AlertBanner", () => {
  it("muestra el mensaje", () => {
    render(<AlertBanner variant="ok">Caja por encima del mínimo</AlertBanner>);
    expect(screen.getByText("Caja por encima del mínimo")).toBeInTheDocument();
  });

  it("peligro usa role=alert (perforación)", () => {
    render(
      <AlertBanner variant="danger">Caja perforada en 2026-09</AlertBanner>,
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("ok/warn usan role=status (no urgente)", () => {
    render(<AlertBanner variant="warn">Mes ajustado</AlertBanner>);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });
});
