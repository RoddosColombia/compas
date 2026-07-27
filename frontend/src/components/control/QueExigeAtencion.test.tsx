// QueExigeAtencion (C2 §7.3): ordena por |desvío| en pesos desc (sobre-ejecutados
// primero), la heurística de calendario dispara con el umbral (+15 pts), y el
// silencio también informa ("todo en rango").

import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import {
  QueExigeAtencion,
  calcularAtencion,
  pctMesTranscurrido,
} from "@/components/control/QueExigeAtencion";
import type { ControlGrupo, ControlLinea } from "@/lib/control";

function linea(overrides: Partial<ControlLinea>): ControlLinea {
  return {
    rubro_id: "r0",
    rubro: "Rubro",
    definido: "1000000.00",
    ejecutado: "0.00",
    disponible: "1000000.00",
    pct_ejecutado: "0",
    semaforo: "verde",
    ...overrides,
  };
}

// 15 de agosto de 2026 → 15/31 ≈ 48.4 % del mes transcurrido.
const HOY = new Date(2026, 7, 15);

describe("pctMesTranscurrido", () => {
  it("mes pasado 100, mes futuro 0, mes actual proporcional", () => {
    expect(pctMesTranscurrido("2026-07", HOY)).toBe(100);
    expect(pctMesTranscurrido("2026-09", HOY)).toBe(0);
    expect(pctMesTranscurrido("2026-08", HOY)).toBeCloseTo((15 / 31) * 100, 5);
  });
});

describe("calcularAtencion", () => {
  it("sobre-ejecutados primero por |disponible| desc, luego en riesgo", () => {
    const grupos: ControlGrupo[] = [
      {
        grupo: "operacion",
        subtotal: { definido: "0", ejecutado: "0", disponible: "0" },
        lineas: [
          // riesgo: 80 % ejecutado con ~48 % del mes (80 > 48.4+15)
          linea({
            rubro_id: "r3",
            rubro: "Cafetería",
            definido: "1000000.00",
            ejecutado: "800000.00",
            disponible: "200000.00",
            pct_ejecutado: "80",
            semaforo: "amarillo",
          }),
          // sobre-ejecutado chico
          linea({
            rubro_id: "r2",
            rubro: "Papelería",
            disponible: "-500000.00",
            pct_ejecutado: "150",
            semaforo: "rojo",
          }),
        ],
      },
      {
        grupo: "nomina",
        subtotal: { definido: "0", ejecutado: "0", disponible: "0" },
        lineas: [
          // sobre-ejecutado grande → debe salir PRIMERO aunque venga después
          linea({
            rubro_id: "r1",
            rubro: "Arriendos",
            disponible: "-2300000.00",
            pct_ejecutado: "114",
            semaforo: "rojo",
          }),
        ],
      },
    ];
    const items = calcularAtencion(grupos, pctMesTranscurrido("2026-08", HOY));
    expect(items.map((i) => i.rubro_id)).toEqual(["r1", "r2", "r3"]);
    expect(items[0].mensaje).toContain("Arriendos");
    // Intl inserta NBSP entre $ y el número → normalizar whitespace
    expect(items[0].mensaje.replace(/\s/g, " ")).toContain("$ 2.300.000,00");
    expect(items[0].mensaje).toContain("114 % del presupuesto");
    expect(items[2].mensaje).toContain("va al 80 %");
  });

  it("la heurística de calendario NO dispara dentro del umbral (+15 pts)", () => {
    const grupos: ControlGrupo[] = [
      {
        grupo: "operacion",
        subtotal: { definido: "0", ejecutado: "0", disponible: "0" },
        lineas: [
          // 60 % con 48.4 % del mes → 60 < 63.4: en rango
          linea({
            rubro_id: "r1",
            ejecutado: "600000.00",
            disponible: "400000.00",
            pct_ejecutado: "60",
          }),
        ],
      },
    ];
    expect(
      calcularAtencion(grupos, pctMesTranscurrido("2026-08", HOY)),
    ).toHaveLength(0);
  });
});

describe("QueExigeAtencion (render)", () => {
  it("'todo en rango' cuando no hay problemas", () => {
    render(
      <MemoryRouter>
        <QueExigeAtencion grupos={[]} mes="2026-08" hoy={HOY} />
      </MemoryRouter>,
    );
    expect(screen.getByText("Todos los rubros en rango ✓")).toBeInTheDocument();
  });

  it("con anchors, cada ítem enlaza a la fila de la tabla", () => {
    const grupos: ControlGrupo[] = [
      {
        grupo: "operacion",
        subtotal: { definido: "0", ejecutado: "0", disponible: "0" },
        lineas: [
          linea({
            rubro_id: "r1",
            rubro: "Arriendos",
            disponible: "-100000.00",
            pct_ejecutado: "110",
          }),
        ],
      },
    ];
    render(
      <MemoryRouter>
        <QueExigeAtencion grupos={grupos} mes="2026-08" conAnchors hoy={HOY} />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: /Arriendos/ })).toHaveAttribute(
      "href",
      "#rubro-r1",
    );
  });

  it("recorta al top N y avisa cuántos más hay", () => {
    const grupos: ControlGrupo[] = [
      {
        grupo: "operacion",
        subtotal: { definido: "0", ejecutado: "0", disponible: "0" },
        lineas: [1, 2, 3].map((n) =>
          linea({
            rubro_id: `r${n}`,
            rubro: `Rubro ${n}`,
            disponible: `-${n}00000.00`,
            pct_ejecutado: "120",
          }),
        ),
      },
    ];
    render(
      <MemoryRouter>
        <QueExigeAtencion grupos={grupos} mes="2026-08" max={2} hoy={HOY} />
      </MemoryRouter>,
    );
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByText(/y 1 más/)).toBeInTheDocument();
  });
});
