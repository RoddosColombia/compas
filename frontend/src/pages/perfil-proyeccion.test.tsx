// F1.1 §2/§10.3 — rendimiento MEDIDO con React.Profiler, no estimado.
// Medición con este mismo arnés y fixture de 180 meses (jsdom, 2026-07-27):
//   ANTES  (tabla-volcado de 180 filas): total 144,5 ms · render máx 126,8 ms
//   DESPUÉS (ventana de 18 filas):       total  56,2 ms · render máx  35,3 ms
// La aserción de abajo es un tope holgado anti-regresión catastrófica (§10.3:
// sin congelamientos >1 s): si el mount vuelve a acercarse al segundo, truena.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { Profiler } from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { MesProyeccion, Proyeccion } from "@/lib/proyeccion";
import ProyeccionPage from "@/pages/ProyeccionPage";

function mesProy(i: number): MesProyeccion {
  const y = 2026 + Math.floor((6 + i) / 12);
  const m = ((6 + i) % 12) + 1;
  return {
    mes: `${y}-${String(m).padStart(2, "0")}`,
    motos: 85 + i,
    cartera: 400 + i * 3,
    recaudo_credito: `${100000000 + i * 1000000}.00`,
    cuotas_iniciales: "35000000.00",
    ingreso_bruto: `${135000000 + i * 1000000}.00`,
    neto: "130000000.00",
    provision: "-1000000.00",
    gastos_fijos: "-125000000.00",
    gps: "-14000000.00",
    costo_nueva: "-60000000.00",
    adelanto: "0.00",
    pago_inventario: "-200000000.00",
    fondeo: "-9000000.00",
    int_deuda: "-300000.00",
    iva: "0.00",
    egresos: "-400000000.00",
    flujo: `${i % 7 === 0 ? "-" : ""}30000000.00`,
    caja: `${500000000 + i * 7000000}.00`,
    estado: i % 11 === 0 ? "critico" : "ok",
  };
}

const PROY: Proyeccion = {
  escenario: "base",
  caja_minima: "125000000.00",
  fondo_provision: [],
  piso_caja: "77800000.00",
  mes_mas_ajustado: "2027-05",
  meses_bajo_minimo: 1,
  caja_final: "1800000000.00",
  capital_requerido: "47200000.00",
  runway_meses: null,
  meses: Array.from({ length: 180 }, (_, i) => mesProy(i)),
};

vi.mock("@/lib/proyeccion", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/proyeccion")>();
  return { ...real, obtenerProyeccion: () => Promise.resolve(PROY) };
});

describe("PERFIL ProyeccionPage (180 meses)", () => {
  it("mide mount + updates", async () => {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const medidas: { phase: string; actual: number }[] = [];
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <Profiler
            id="proy"
            onRender={(_id, phase, actualDuration) =>
              medidas.push({ phase, actual: actualDuration })
            }
          >
            <ProyeccionPage />
          </Profiler>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText("Piso de caja")).toBeInTheDocument();
    const total = medidas.reduce((a, m) => a + m.actual, 0);
    const filas = document.querySelectorAll("tbody tr").length;
    console.log(
      `PERFIL filas=${filas} renders=${medidas.length} totalMs=${total.toFixed(1)} max=${Math.max(...medidas.map((m) => m.actual)).toFixed(1)}`,
    );
    // ventana por defecto (no el volcado) + tope anti-congelamiento (§10.3)
    expect(filas).toBe(18);
    expect(total).toBeLessThan(1000);
  });
});
