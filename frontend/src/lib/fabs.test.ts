import { describe, expect, it, vi } from "vitest";
import * as api from "@/lib/api";
import { historialFabs, preguntarFabs } from "@/lib/fabs";

describe("fabs api", () => {
  it("preguntarFabs hace POST /cfo con JSON", async () => {
    const spy = vi.spyOn(api, "apiJson").mockResolvedValue({ texto: "ok", abstuvo: false, cifras: [] } as never);
    await preguntarFabs("hola");
    expect(spy).toHaveBeenCalledWith("/cfo", expect.objectContaining({
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pregunta: "hola" }),
    }));
    spy.mockRestore();
  });

  it("historialFabs hace GET /cfo/historial", async () => {
    const spy = vi.spyOn(api, "apiJson").mockResolvedValue([] as never);
    await historialFabs();
    expect(spy).toHaveBeenCalledWith("/cfo/historial");
    spy.mockRestore();
  });
});
