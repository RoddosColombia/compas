// ScenarioChip: pill de escenario. Activo = pill negra; inactivo = borde hairline.
// Estado activo + click SON comportamiento → se prueban.

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ScenarioChip } from "@/components/ui/scenario-chip";

describe("ScenarioChip", () => {
  it("el activo marca aria-pressed y fondo tinta", () => {
    render(<ScenarioChip label="Base" active onClick={() => {}} />);
    const chip = screen.getByRole("button", { name: "Base" });
    expect(chip).toHaveAttribute("aria-pressed", "true");
    expect(chip).toHaveClass("bg-ink");
  });

  it("el inactivo no marca aria-pressed y dispara onClick", () => {
    const onClick = vi.fn();
    render(<ScenarioChip label="Pesimista" active={false} onClick={onClick} />);
    const chip = screen.getByRole("button", { name: "Pesimista" });
    expect(chip).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(chip);
    expect(onClick).toHaveBeenCalledOnce();
  });
});
