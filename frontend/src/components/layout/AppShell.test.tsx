// FIX-UI-1: el lienzo de contenido es de ancho completo SOLO en /proyeccion (la foto
// del CEO a ~1918px sin scroll lateral); el resto del cockpit sigue centrado a max-w-6xl.

import { describe, expect, it } from "vitest";

import { anchoContenido } from "@/components/layout/AppShell";

describe("anchoContenido — ancho del lienzo por ruta (FIX-UI-1)", () => {
  it("/proyeccion → ancho completo (sin max-w)", () => {
    expect(anchoContenido("/proyeccion")).toBe("w-full");
  });

  it("subrutas de /proyeccion → ancho completo", () => {
    expect(anchoContenido("/proyeccion/algo")).toBe("w-full");
  });

  it("otras rutas → centrado a max-w-6xl", () => {
    expect(anchoContenido("/obligaciones")).toBe("mx-auto max-w-6xl");
    expect(anchoContenido("/inicio")).toBe("mx-auto max-w-6xl");
    expect(anchoContenido("/")).toBe("mx-auto max-w-6xl");
  });
});
