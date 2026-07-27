// F1.1 §10.2 — guardián de los barridos: verificable por test, no por promesa.
// Si alguien reintroduce una infracción dura del sistema de diseño, CI truena.

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = join(__dirname, "..");

function archivosTsx(dir: string): string[] {
  const out: string[] = [];
  for (const nombre of readdirSync(dir)) {
    const ruta = join(dir, nombre);
    if (statSync(ruta).isDirectory()) {
      out.push(...archivosTsx(ruta));
    } else if (ruta.endsWith(".tsx") && !ruta.endsWith(".test.tsx")) {
      out.push(ruta);
    }
  }
  return out;
}

const ARCHIVOS = archivosTsx(SRC);

function infractores(patron: RegExp, permitidos: string[] = []): string[] {
  return ARCHIVOS.filter(
    (f) =>
      !permitidos.some((p) => f.replaceAll("\\", "/").endsWith(p)) &&
      patron.test(readFileSync(f, "utf-8")),
  ).map((f) => f.replaceAll("\\", "/").split("/src/")[1] ?? f);
}

describe("barridos F1.1 §1 (guardián)", () => {
  it("KpiTile v1 no tiene referencias (murió)", () => {
    expect(infractores(/<KpiTile[\s>]/)).toEqual([]);
    expect(infractores(/\bKpiTileProps\b|\bKpiDelta\b/)).toEqual([]);
  });

  it("cero text-[10px] — mínimo absoluto 12.5px (text-apoyo)", () => {
    expect(infractores(/text-\[10px\]/)).toEqual([]);
  });

  it("cero text-xs sueltos — todo a la escala de roles", () => {
    expect(infractores(/text-xs/)).toEqual([]);
  });

  it("ink-decor jamás como color de TEXTO legible (solo decorativos ⓘ/trazos)", () => {
    // permitido: iconos ⓘ (cursor-help) y strokes; prohibido: párrafos/etiquetas
    for (const f of ARCHIVOS) {
      const s = readFileSync(f, "utf-8");
      for (const linea of s.split("\n")) {
        if (
          linea.includes("text-ink-decor") &&
          !linea.includes("cursor-help")
        ) {
          throw new Error(`texto en ink-decor: ${f}\n${linea.trim()}`);
        }
      }
    }
  });

  it("badges/semáforos sin tokens viejos green/amber/red (salvo button de acción)", () => {
    expect(
      infractores(
        /text-green|bg-green|text-amber|bg-amber|text-red\b|bg-red\b/,
        ["components/ui/button.tsx"],
      ),
    ).toEqual([]);
  });
});
