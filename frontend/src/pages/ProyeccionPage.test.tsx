// frontend/src/pages/ProyeccionPage.test.tsx
//
// F1.1 §2 — Proyecciones al estándar: juicio a horizonte largo (60 m) con
// ventana de 18 m por defecto, 4 KpiTileV2 (Runway "Sin límite" cuando null),
// ChartCard con conclusión dinámica, tabla-ventana expandible sin centavos con
// el mes crítico resaltado/anclado, y FiltroBarra de horizonte con "Limpiar".

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { MesProyeccion, Proyeccion } from "@/lib/proyeccion";
import ProyeccionPage from "@/pages/ProyeccionPage";

function mesProy(
  i: number,
  extras: Partial<MesProyeccion> = {},
): MesProyeccion {
  const y = 2026 + Math.floor((6 + i) / 12);
  const m = ((6 + i) % 12) + 1;
  return {
    mes: `${y}-${String(m).padStart(2, "0")}`,
    motos: 50 + i,
    cartera: 120,
    recaudo_credito: "30000000.00",
    cuotas_iniciales: "5000000.00",
    ingreso_bruto: "35000000.00",
    neto: "34000000.00",
    provision: "-700000.00",
    gastos_fijos: "-125000000.00",
    gps: "-4000000.00",
    costo_nueva: "-3000000.00",
    adelanto: "0.00",
    pago_inventario: "0.00",
    fondeo: "0.00",
    int_deuda: "-300000.00",
    iva: "0.00",
    aval: "0.00",
    mora: "0.00",
    recuperacion: "0.00",
    default: "0.00",
    egresos: "-132300000.00",
    flujo: "-98300000.00",
    caja: "200000000.00",
    estado: "ok",
    ...extras,
  };
}

// 60 meses (lo que trae la query de juicio); el crítico es el mes 3 (2026-10).
const MESES = Array.from({ length: 60 }, (_, i) =>
  i === 3 ? mesProy(i, { caja: "40000000.00", estado: "critico" }) : mesProy(i),
);

const PROY: Proyeccion = {
  escenario: "base",
  caja_minima: "125000000.00",
  fondo_provision: [],
  piso_caja: "40000000.00",
  mes_mas_ajustado: "2026-10",
  meses_bajo_minimo: 1,
  caja_final: "200000000.00",
  capital_requerido: "85000000.00",
  runway_meses: null,
  ventana_reconciliada: null,
  interes_obligaciones: {},
  meses: MESES,
};

const mocks = vi.hoisted(() => ({
  obtenerProyeccion: vi.fn(),
  obtenerProyeccionAgregada: vi.fn(),
}));

vi.mock("@/lib/proyeccion", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/proyeccion")>();
  return {
    ...real,
    obtenerProyeccion: mocks.obtenerProyeccion,
    obtenerProyeccionAgregada: mocks.obtenerProyeccionAgregada,
  };
});

// ENTREGA 3 pieza 1: el techo de gasto se gatilla con proyeccion:gestionar y usa el
// solver. Se stubea el auth (el CEO lo tiene) y el solver (compute-only).
vi.mock("@/auth/AuthContext", () => ({
  useAuth: () => ({ puede: () => true }),
}));

vi.mock("@/lib/decisiones", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/decisiones")>();
  return {
    ...real,
    obtenerValles: vi.fn().mockResolvedValue({
      escenario: "base",
      caja_minima: "125000000.00",
      valles: [],
    }),
    resolver: vi.fn().mockResolvedValue({
      objetivo: "techo_gasto",
      techo_mensual: "5000000.00",
      valle_limitante_mes: "2027-05",
      piso_resultante: "10000000.00",
      meta: "0.00",
      colchon: "0.00",
      hay_holgura: true,
    }),
  };
});

function renderPage() {
  mocks.obtenerProyeccion.mockResolvedValue(PROY);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ProyeccionPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ProyeccionPage — F1.1 §2", () => {
  it("el juicio pide horizonte largo aunque la ventana sea 18 m", async () => {
    renderPage();
    await screen.findByText("Piso de caja");
    expect(mocks.obtenerProyeccion).toHaveBeenCalledWith({
      escenario: "base",
      horizonteMeses: 60,
    });
  });

  it("muestra los 4 KPIs con juicio — Runway null es 'Sin límite'", async () => {
    renderPage();
    expect(await screen.findByText("Piso de caja")).toBeInTheDocument();
    expect(screen.getByText("1 de 60")).toBeInTheDocument();
    expect(screen.getByText("Capital requerido")).toBeInTheDocument();
    expect(screen.getByText("Sin límite")).toBeInTheDocument();
    expect(
      screen.getByText("la caja crece al ritmo actual"),
    ).toBeInTheDocument();
    // ya no hay tile de Caja final: vive en el pie del gráfico
    expect(screen.queryByText("Caja final")).toBeNull();
    expect(screen.getByText(/Caja final a 60 meses/)).toBeInTheDocument();
  });

  it("la conclusión del gráfico nombra el mes crítico y lo ancla en la tabla", async () => {
    renderPage();
    expect(
      await screen.findByRole("heading", {
        name: /La caja toca su punto más bajo en oct-26/,
      }),
    ).toBeInTheDocument();
    // botón accesible (no <a>): expande y desplaza a la fila del mes crítico
    const ancla = screen.getByRole("button", { name: /Ver el mes crítico/ });
    expect(ancla).toBeInTheDocument();
    expect(document.getElementById("mes-critico")).not.toBeNull();
  });

  it("crítico fuera de la ventana: 'Ver el mes crítico' expande la tabla", async () => {
    // el mes crítico cae en el índice 30 (2029-01), fuera de la ventana de 18 m
    Element.prototype.scrollIntoView = vi.fn(); // jsdom no lo implementa
    const meses = Array.from({ length: 60 }, (_, i) =>
      i === 30
        ? mesProy(i, { caja: "40000000.00", estado: "critico" })
        : mesProy(i),
    );
    mocks.obtenerProyeccion.mockResolvedValue({
      ...PROY,
      mes_mas_ajustado: meses[30].mes,
      meses,
    });
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={qc}>
        <ProyeccionPage />
      </QueryClientProvider>,
    );
    await screen.findByText("Piso de caja");
    // ventana por defecto: 18 filas y el mes crítico aún NO está en el DOM
    expect(document.querySelectorAll("tbody tr")).toHaveLength(18);
    expect(document.getElementById("mes-critico")).toBeNull();
    // clic en el botón → la tabla se expande y el mes crítico aparece
    fireEvent.click(screen.getByRole("button", { name: /Ver el mes crítico/ }));
    expect(document.querySelectorAll("tbody tr")).toHaveLength(60);
    expect(document.getElementById("mes-critico")).not.toBeNull();
  });

  it("la tabla es ventana (18 filas), sin centavos, y se expande a los 60", async () => {
    renderPage();
    await screen.findByText("Piso de caja");
    expect(document.querySelectorAll("tbody tr")).toHaveLength(18);
    // sin centavos en la tabla (política F1 §3). La columna Ingreso = neto (34M).
    expect(screen.queryByText(/\$\s?34\.000\.000,00/)).toBeNull();
    expect(
      screen.getAllByText((t) => t.replace(/\s/g, " ") === "$ 34.000.000")
        .length,
    ).toBeGreaterThan(0);
    // estado con símbolo (color nunca solo)
    expect(screen.getAllByText(/✓ OK/).length).toBeGreaterThan(0);
    fireEvent.click(
      screen.getByRole("button", { name: "Ver los 60 meses completos" }),
    );
    expect(document.querySelectorAll("tbody tr")).toHaveLength(60);
  });

  it("FiltroBarra: cambiar el horizonte muestra 'Limpiar' y restaura el default", async () => {
    renderPage();
    await screen.findByText("Piso de caja");
    expect(screen.queryByRole("button", { name: "Limpiar" })).toBeNull();
    // RF-F10 (2026-08-30): «todo» pasó de 180 → 240 meses en OPCIONES_HORIZONTE.
    fireEvent.change(screen.getByLabelText(/Horizonte/), {
      target: { value: "240" },
    });
    const limpiar = await screen.findByRole("button", { name: "Limpiar" });
    fireEvent.click(limpiar);
    expect(screen.queryByRole("button", { name: "Limpiar" })).toBeNull();
    expect(screen.getByLabelText(/Horizonte/)).toHaveValue("18");
  });

  it("Compromiso Auteco sin compromisos: lo dice, no muestra $0 (ítem 6)", async () => {
    renderPage(); // todos los meses con Auteco paramétrico 0 → no hay compromiso
    expect(await screen.findByText("Compromiso Auteco")).toBeInTheDocument();
    expect(
      screen.getByText(/ninguno en el horizonte proyectado/),
    ).toBeInTheDocument();
  });

  it("Compromiso Auteco: muestra el PRÓXIMO compromiso con su distancia (ítem 6)", async () => {
    // un mes con Auteco > 0 (índice 2 = 2026-09, a 2 meses de jul-26)
    const conAuteco = MESES.map((m, i) =>
      i === 2
        ? { ...m, pago_inventario: "-180000000.00", fondeo: "-5760000.00" }
        : m,
    );
    mocks.obtenerProyeccion.mockResolvedValue({ ...PROY, meses: conAuteco });
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={qc}>
        <ProyeccionPage />
      </QueryClientProvider>,
    );
    expect(
      await screen.findByText("Próximo compromiso Auteco"),
    ).toBeInTheDocument();
    expect(screen.getByText(/en 2 meses/)).toBeInTheDocument();
  });

  it("muestra el techo de gasto (pieza 1): la pregunta y la cifra grande", async () => {
    renderPage();
    expect(
      await screen.findByText(/¿Cuánto puedo gastar al mes/i),
    ).toBeInTheDocument();
    // la frase de lectura del techo (única de la tarjeta) confirma la rama con holgura
    expect(
      screen.getByText(
        /la caja se sostiene sobre el mínimo de caja los 60 meses/i,
      ),
    ).toBeInTheDocument();
  });

  it("ofrece los tres escenarios", async () => {
    renderPage();
    await screen.findByText("Piso de caja");
    for (const e of ["Pesimista", "Base", "Optimista"]) {
      expect(screen.getByRole("button", { name: e })).toBeInTheDocument();
    }
  });

  // E1·P6 — con ciclo: leyenda de origen + callout del mes en curso visibles.
  it("con anclaje muestra la leyenda de origen y el callout del mes en curso", async () => {
    mocks.obtenerProyeccion.mockResolvedValue({
      ...PROY,
      meses_anclados: { "2026-07": "cerrado", "2026-08": "en_ejecucion" },
      sin_mapear: ["Ajuste raro 4040"],
      mes_en_curso: {
        mes: "2026-08",
        cargado_hasta: "2026-08-06",
        dia: 6,
        formula: "ejecutado + max(0, definido - ejecutado) por concepto",
        ejecutado: "41000000.00",
        proyectado: "168000000.00",
      },
    });
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={qc}>
        <ProyeccionPage />
      </QueryClientProvider>,
    );
    expect(
      await screen.findByText(/Origen de cada cifra/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/Mes en curso/i)).toBeInTheDocument();
    expect(screen.getByText(/sin clasificar/i)).toBeInTheDocument();
  });

  // Candado: sin ciclo (PROY no trae las 3 claves) → nada nuevo se renderiza.
  it("sin ciclo la UI queda como hoy (sin leyenda ni callout)", async () => {
    renderPage();
    await screen.findByText("Piso de caja");
    expect(screen.queryByText(/Origen de cada cifra/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Mes en curso/i)).not.toBeInTheDocument();
  });

  // RF-F10 · Fundacional §2 — Horizonte largo con agregación.

  it("con horizonte < 60 meses no muestra la tarjeta de vista agregada", async () => {
    renderPage();
    await screen.findByText("Piso de caja");
    // default = 18 meses; la tarjeta aparece solo desde 60.
    expect(
      screen.queryByText("Horizonte largo — vista agregada"),
    ).toBeNull();
    expect(mocks.obtenerProyeccionAgregada).not.toHaveBeenCalled();
  });

  it("con horizonte ≥ 60 meses muestra la tarjeta y llama al endpoint agregado", async () => {
    mocks.obtenerProyeccionAgregada.mockResolvedValue({
      escenario: "base",
      granularidad: "anual",
      caja_minima: "125000000.00",
      caja_atencion: null,
      periodos: [
        {
          etiqueta: "2027",
          desde: "2027-01",
          hasta: "2027-12",
          meses_en_periodo: 12,
          caja_final: "135000000.00",
          piso: "90000000.00",
          flujo: "-50000000.00",
          ingreso_bruto: "420000000.00",
          egresos: "-470000000.00",
          motos: 137,
        },
      ],
    });
    renderPage();
    await screen.findByText("Piso de caja");
    fireEvent.change(screen.getByLabelText(/Horizonte/), {
      target: { value: "60" },
    });
    // La tarjeta aparece y el mock recibe granularidad="anual" (default).
    expect(
      await screen.findByText("Horizonte largo — vista agregada"),
    ).toBeInTheDocument();
    expect(mocks.obtenerProyeccionAgregada).toHaveBeenCalledWith(
      "anual",
      expect.objectContaining({ horizonteMeses: 60 }),
    );
    // La fila del periodo muestra la etiqueta y las motos totales.
    expect(await screen.findByTestId("periodo-2027")).toBeInTheDocument();
    expect(screen.getByText("137")).toBeInTheDocument();
  });

  it("cambiar granularidad a Trimestre re-consulta con la nueva granularidad", async () => {
    mocks.obtenerProyeccionAgregada.mockResolvedValue({
      escenario: "base",
      granularidad: "anual",
      caja_minima: "125000000.00",
      caja_atencion: null,
      periodos: [],
    });
    renderPage();
    await screen.findByText("Piso de caja");
    fireEvent.change(screen.getByLabelText(/Horizonte/), {
      target: { value: "120" },
    });
    await screen.findByText("Horizonte largo — vista agregada");
    fireEvent.click(screen.getByRole("button", { name: /trimestre/i }));
    // Se pidió la agregación con "trimestre".
    expect(mocks.obtenerProyeccionAgregada).toHaveBeenCalledWith(
      "trimestre",
      expect.objectContaining({ horizonteMeses: 120 }),
    );
  });
});
