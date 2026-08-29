// RF-F2 — VersionDiffCallout: si no hay versión anterior no pinta nada; con anterior,
// muestra piso, mes del piso, y cambios de valles.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { VersionDiffCallout } from "@/components/proyeccion/VersionDiffCallout";
import type { VersionDiff } from "@/lib/proyeccion";

describe("VersionDiffCallout", () => {
  it("no pinta cuando no hay versión anterior", () => {
    const { container } = render(
      <VersionDiffCallout diff={{ hay_anterior: false }} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("muestra piso vs. anterior, valles nuevos y desaparecidos", () => {
    const diff: VersionDiff = {
      hay_anterior: true,
      version_anterior: 2,
      mes_aprobado_anterior: "2026-08-01",
      piso: {
        anterior: "100000000",
        actual: "130000000",
        delta: "30000000.00",
      },
      mes_mas_ajustado: { anterior: "2027-05", actual: "2027-06" },
      valles: {
        anterior: 1,
        actual: 2,
        nuevos: ["2027-06-01"],
        desaparecidos: [],
      },
    };
    render(<VersionDiffCallout diff={diff} />);
    expect(screen.getByText(/vs\. última aprobación/i)).toBeInTheDocument();
    // versión + mes anterior
    expect(screen.getByText(/v2/)).toBeInTheDocument();
    expect(screen.getByText(/aprobada para 2026-08/i)).toBeInTheDocument();
    // delta del piso (▲ y +$30 M algo)
    expect(screen.getByText(/▲ \+/)).toBeInTheDocument();
    // valle nuevo etiquetado
    expect(screen.getByText(/nuevos: 2027-06/)).toBeInTheDocument();
    // cambio de mes del piso
    expect(screen.getByText(/antes: 2027-05/)).toBeInTheDocument();
  });
});
