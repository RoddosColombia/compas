# E1 · P6 — Frontend: marcas de origen + mes en curso — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hacer visible en Proyecciones el origen de cada cifra (marcas), la comparación del mes en curso, la completitud (B13) con la fórmula, y `sin_mapear` — consumiendo el shape de P5, sin ensanchar la tabla y sin romper la vista sin ciclo.

**Architecture:** Tipos aditivos en `lib/proyeccion.ts`; dos componentes nuevos de presentación (`MarcaOrigen`, `MesEnCursoCallout`); la tabla y el gráfico existentes reciben las nuevas props y renderizan condicionalmente; la página cablea todo. Cero backend. Todo condicional al ciclo → sin anclaje la UI queda como hoy.

**Tech Stack:** React 19 + TS + Tailwind 4 + shadcn; Vitest + Testing Library; SVG a mano (sin librerías nuevas); decimal.js-light (nunca `Number` sobre montos).

## Global Constraints

- **Dinero:** nunca `Number` sobre un monto; formato con `formatCOP*` / `decimal.js-light`. Montos llegan como string del backend.
- **App light-only** ("Fondo blanco"); tokens reales (`--color-cyan #0fa9b8`, `--color-positivo #15803d`, `--color-atencion #b45309`, `--color-critico #b91c1c`, `hairline`, `ink*`, `surface*`). Clases Tailwind del proyecto (`text-cuerpo`, `text-apoyo`, `bg-surface`, `border-hairline`, `text-cyan`, etc.).
- **Marca de ORIGEN ≠ salud de caja** (`EstadoMes = ok|critico|negativo`): dimensiones separadas, coexisten.
- **Sin scroll lateral** en la tabla: las marcas NO añaden columnas (van en la 1ª columna, el mes).
- **Candado sin ciclo:** `meses_anclados={}` + `mes_en_curso=null` + `sin_mapear=[]` → ningún bloque nuevo se renderiza; la vista queda idéntica a hoy.
- **TDD rojo→verde** con vitest. **build + biome verdes** antes del gate.
- **Copys aprobados por el CEO** (usar exactamente los del spec §4).

## Vocabulario de marcas (una verdad — `MarcaOrigen.tsx`)

| marca (`meses_anclados[mes]`) | etiqueta | símbolo/estilo |
|---|---|---|
| `cerrado` | Real | punto lleno ink |
| `en_ejecucion` | En curso | punto medio cyan |
| `presupuesto` | Presupuesto | punto hueco ink-decor |
| `cerrado_sospechoso` | Revisar carga | ⚠ ámbar (atención) |
| (mes sin entrada) | Proyección | punto punteado gris |

---

## Task 1: Tipos aditivos + componente `MarcaOrigen`

**Files:**
- Modify: `frontend/src/lib/proyeccion.ts`
- Create: `frontend/src/components/proyeccion/MarcaOrigen.tsx`
- Test: `frontend/src/components/proyeccion/MarcaOrigen.test.tsx`

**Interfaces:**
- Produces: `type MarcaOrigen = "cerrado"|"cerrado_sospechoso"|"en_ejecucion"|"presupuesto"`; `interface MesEnCurso {mes:string; cargado_hasta:string|null; dia:number|null; formula:string}`; campos en `Proyeccion`: `meses_anclados: Record<string,MarcaOrigen>`, `sin_mapear: string[]`, `mes_en_curso: MesEnCurso|null`. Componente `<MarcaOrigen marca={MarcaOrigen|undefined} />` (undefined → "Proyección") y `<LeyendaOrigen />`. Helper `MARCA_LABEL: Record<MarcaOrigen|"proyeccion", string>`.

- [ ] **Step 1: Escribir el test que falla**

`frontend/src/components/proyeccion/MarcaOrigen.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MarcaOrigen } from "@/components/proyeccion/MarcaOrigen";

describe("MarcaOrigen", () => {
  it("muestra la etiqueta de cada marca del backend", () => {
    const { rerender } = render(<MarcaOrigen marca="cerrado" />);
    expect(screen.getByText("Real")).toBeInTheDocument();
    rerender(<MarcaOrigen marca="en_ejecucion" />);
    expect(screen.getByText("En curso")).toBeInTheDocument();
    rerender(<MarcaOrigen marca="presupuesto" />);
    expect(screen.getByText("Presupuesto")).toBeInTheDocument();
    rerender(<MarcaOrigen marca="cerrado_sospechoso" />);
    expect(screen.getByText("Revisar carga")).toBeInTheDocument();
  });

  it("un mes sin marca (undefined) es 'Proyección'", () => {
    render(<MarcaOrigen marca={undefined} />);
    expect(screen.getByText("Proyección")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `cd frontend && npx vitest run src/components/proyeccion/MarcaOrigen.test.tsx`
Expected: FAIL — no se resuelve el módulo `MarcaOrigen`.

- [ ] **Step 3: Añadir los tipos a `lib/proyeccion.ts`**

Tras `export type EstadoMes = ...` añadir:

```ts
// E1·P6 — marca de ORIGEN de la cifra (dimensión distinta de EstadoMes/salud de caja).
export type MarcaOrigen =
  | "cerrado"
  | "cerrado_sospechoso"
  | "en_ejecucion"
  | "presupuesto";

export interface MesEnCurso {
  mes: string; // 'YYYY-MM'
  cargado_hasta: string | null; // 'YYYY-MM-DD' | null si aún sin tx
  dia: number | null;
  formula: string; // fórmula técnica del backend (Regla A)
}
```

y dentro de `interface Proyeccion` (al final, aditivo):

```ts
  // E1·P6 — origen de cada cifra (P5 shape). Vacíos si no hay anclaje.
  meses_anclados: Record<string, MarcaOrigen>;
  sin_mapear: string[];
  mes_en_curso: MesEnCurso | null;
```

- [ ] **Step 4: Crear `MarcaOrigen.tsx`**

```tsx
// components/proyeccion/MarcaOrigen.tsx
//
// E1·P6 — marca de ORIGEN de la cifra (Real · En curso · Presupuesto · Proyección ·
// Revisar carga). Dimensión distinta de la salud de caja (EstadoMes). Presentación
// pura: una verdad para tabla, gráfico (leyenda) y callout.

import type { MarcaOrigen as Marca } from "@/lib/proyeccion";
import { cn } from "@/lib/utils";

type Clave = Marca | "proyeccion";

export const MARCA_LABEL: Record<Clave, string> = {
  cerrado: "Real",
  en_ejecucion: "En curso",
  presupuesto: "Presupuesto",
  cerrado_sospechoso: "Revisar carga",
  proyeccion: "Proyección",
};

const PUNTO: Record<Clave, string> = {
  cerrado: "bg-ink",
  en_ejecucion: "bg-cyan ring-2 ring-cyan/40",
  presupuesto: "border-2 border-ink-decor bg-transparent",
  cerrado_sospechoso: "bg-atencion",
  proyeccion: "border-2 border-dashed border-ink-decor bg-transparent",
};

function clave(marca: Marca | undefined): Clave {
  return marca ?? "proyeccion";
}

export function MarcaOrigen({ marca }: { marca?: Marca }) {
  const k = clave(marca);
  return (
    <span className="inline-flex items-center gap-1.5 text-apoyo text-ink-faint">
      <span className={cn("inline-block h-2.5 w-2.5 flex-none rounded-full", PUNTO[k])} />
      {k === "cerrado_sospechoso" && <span aria-hidden className="text-atencion">⚠</span>}
      {MARCA_LABEL[k]}
    </span>
  );
}

export function LeyendaOrigen() {
  const orden: Clave[] = [
    "cerrado",
    "en_ejecucion",
    "presupuesto",
    "proyeccion",
    "cerrado_sospechoso",
  ];
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 rounded-xl border border-cyan/20 bg-cyan-tint px-4 py-2.5 text-apoyo">
      <span className="font-semibold text-ink">Origen de cada cifra:</span>
      {orden.map((k) => (
        <span key={k} className="inline-flex items-center gap-1.5 text-ink-soft">
          <span className={cn("inline-block h-2.5 w-2.5 flex-none rounded-full", PUNTO[k])} />
          {MARCA_LABEL[k]}
        </span>
      ))}
    </div>
  );
}
```

Nota: si `bg-cyan-tint` no existe como clase, usar `style={{background:"var(--color-cyan-tint)"}}` o la utilidad equivalente del proyecto.

- [ ] **Step 5: Correr el test (verde)**

Run: `cd frontend && npx vitest run src/components/proyeccion/MarcaOrigen.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 6: biome**

Run: `cd frontend && npx biome check src/components/proyeccion/MarcaOrigen.tsx src/components/proyeccion/MarcaOrigen.test.tsx src/lib/proyeccion.ts`
Expected: sin errores (aplicar `biome check --write` si hay formato).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/proyeccion.ts frontend/src/components/proyeccion/MarcaOrigen.tsx frontend/src/components/proyeccion/MarcaOrigen.test.tsx
git commit -m "feat(e1-p6): tipos aditivos + componente MarcaOrigen (vocabulario de origen)"
```

---

## Task 2: `MesEnCursoCallout` (comparación + B13 + arrastre)

**Files:**
- Create: `frontend/src/components/proyeccion/MesEnCursoCallout.tsx`
- Test: `frontend/src/components/proyeccion/MesEnCursoCallout.test.tsx`

**Interfaces:**
- Consumes: `MesEnCurso`, `MesProyeccion`, `formatMesCorto`, `formatCOPCompact`, `formatDelta`, `parseMonto` (de `@/lib/money`).
- Produces: `<MesEnCursoCallout mesEnCurso={MesEnCurso} fila={MesProyeccion} proyectado={string} ejecutado={string} />` — muestra Proyectado/Ejecutado (al día N)/Desviación + "Cargado hasta el N de [mes]" + fórmula de negocio + copy de arrastre. (Proyectado = `fila.egresos`/`fila.caja` según lo que el motor exponga como total del mes; ejecutado se deriva de lo real — ver nota.)

Nota de datos: el "ejecutado (al día N)" y el "proyectado del mes" salen del `MesProyeccion` del mes en curso — el motor ya ancló ese mes con la Regla A. Para el mockup se usan los totales del mes; el implementador confirma qué campo del `MesProyeccion` representa el proyectado vs. el ejecutado parcial (probablemente el callout compara `fila` anclada vs. el mismo mes SIN anclar no está disponible en el front → **decisión: mostrar Ejecutado = suma real hasta el día N** proveniente de un campo ya disponible o, si no lo hay en el shape, mostrar solo completitud + fórmula y **omitir la sub-comparación numérica** —degradación honesta— documentándolo en el gate). **RESOLVER en Step 1 leyendo qué expone el shape**; NO inventar cifras.

- [ ] **Step 1: Confirmar los datos disponibles + escribir el test**

Verificar en `lib/proyeccion.ts` / la respuesta real qué campos permiten "proyectado vs ejecutado al día N" para el mes en curso. Si el shape NO trae el ejecutado parcial separado, el callout muestra completitud (B13) + fórmula + arrastre, y la comparación numérica se marca como "disponible al detalle" (sin inventar). Escribir el test acorde a lo que exista:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MesEnCursoCallout } from "@/components/proyeccion/MesEnCursoCallout";
import type { MesEnCurso } from "@/lib/proyeccion";

const MEC: MesEnCurso = {
  mes: "2026-08",
  cargado_hasta: "2026-08-06",
  dia: 6,
  formula: "ejecutado + max(0, definido - ejecutado) por concepto",
};

describe("MesEnCursoCallout — B13", () => {
  it("muestra la completitud y la fórmula en lenguaje de negocio", () => {
    render(<MesEnCursoCallout mesEnCurso={MEC} />);
    expect(screen.getByText(/cargado hasta el 6/i)).toBeInTheDocument();
    expect(
      screen.getByText(/ejecutado \+ lo que resta del presupuesto/i),
    ).toBeInTheDocument();
  });

  it("muestra el copy de efecto-arrastre con el mes", () => {
    render(<MesEnCursoCallout mesEnCurso={MEC} />);
    expect(
      screen.getByText(/cuando cierres agosto/i),
    ).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Correr (falla)**

Run: `cd frontend && npx vitest run src/components/proyeccion/MesEnCursoCallout.test.tsx`
Expected: FAIL — módulo no resuelto.

- [ ] **Step 3: Implementar `MesEnCursoCallout.tsx`**

```tsx
// components/proyeccion/MesEnCursoCallout.tsx
//
// E1·P6 — el mes en curso: completitud (B13, "cargado hasta el día N") con la fórmula
// en lenguaje de negocio (honestidad R5: se ve cómo se armó, no solo el resultado) +
// copy de efecto-arrastre. La comparación proyectado/ejecutado/desviación se muestra
// solo si hay datos (nunca se inventa cifra).

import { Card } from "@/components/ui/card";
import { formatMesCorto } from "@/lib/money";
import type { MesEnCurso } from "@/lib/proyeccion";

const FORMULA_NEGOCIO = "ejecutado + lo que resta del presupuesto";

export function MesEnCursoCallout({ mesEnCurso }: { mesEnCurso: MesEnCurso }) {
  const mesTxt = formatMesCorto(mesEnCurso.mes);
  return (
    <Card className="border-cyan/30 p-0">
      <div className="grid gap-0 sm:grid-cols-[1.4fr_1fr]">
        <div className="p-5">
          <span className="inline-flex items-center gap-2 text-apoyo font-semibold uppercase tracking-wide text-cyan">
            <span className="inline-block h-2.5 w-2.5 rounded-full bg-cyan ring-2 ring-cyan/40" />
            Mes en curso · {mesTxt}
          </span>
          <p className="mt-3 border-l-[3px] border-cyan pl-3 text-cuerpo text-ink-soft">
            Cuando cierres {mesTxt.toLowerCase()}, su ejecución real reemplaza esta
            estimación y arrastra el resto del año.
          </p>
        </div>
        <div className="border-t border-hairline bg-surface-muted p-5 sm:border-t-0 sm:border-l">
          <span className="text-apoyo font-semibold uppercase tracking-wide text-ink-soft">
            Completitud del mes
          </span>
          <p className="mt-1 font-display text-cuerpo font-semibold text-ink">
            {mesEnCurso.dia === null
              ? `${mesTxt}: aún sin movimientos cargados`
              : `Cargado hasta el ${mesEnCurso.dia} de ${mesTxt.toLowerCase()}`}
          </p>
          <p className="mt-2 text-apoyo text-ink-soft">
            Los días que faltan se estiman así:{" "}
            <span className="rounded-md border border-hairline bg-surface px-1.5 py-0.5 text-ink">
              {FORMULA_NEGOCIO}
            </span>
          </p>
        </div>
      </div>
    </Card>
  );
}
```

- [ ] **Step 4: Correr (verde)**

Run: `cd frontend && npx vitest run src/components/proyeccion/MesEnCursoCallout.test.tsx`
Expected: PASS.

- [ ] **Step 5: biome + commit**

```bash
cd frontend && npx biome check --write src/components/proyeccion/MesEnCursoCallout.tsx src/components/proyeccion/MesEnCursoCallout.test.tsx
git add frontend/src/components/proyeccion/MesEnCursoCallout.tsx frontend/src/components/proyeccion/MesEnCursoCallout.test.tsx
git commit -m "feat(e1-p6): MesEnCursoCallout (completitud B13 + fórmula de negocio + arrastre)"
```

---

## Task 3: `TablaEgreso` — marca en la 1ª columna + `sin_mapear` al pie

**Files:**
- Modify: `frontend/src/components/proyeccion/TablaEgreso.tsx`
- Test: `frontend/src/components/proyeccion/TablaEgreso.test.tsx`

**Interfaces:**
- Consumes: `MarcaOrigen` component, `MarcaOrigen` type.
- Produces: `TablaEgreso` acepta props nuevas opcionales: `mesesAnclados?: Record<string, MarcaOrigen>`, `sinMapear?: string[]`. Bajo el nombre del mes (1ª columna) muestra `<MarcaOrigen marca={mesesAnclados[m.mes]} />`. Al pie, si `sinMapear` no vacío, un aviso.

- [ ] **Step 1: Escribir/extender el test (falla)**

Añadir a `TablaEgreso.test.tsx`:

```tsx
it("muestra la marca de origen de cada mes bajo el nombre", () => {
  render(
    <TablaEgreso
      filas={[PROYECTADO, RECONCILIADO]}
      mesCritico="2026-10"
      perforada={true}
      ventanaReconciliada={["2027-01", "2027-01"]}
      mesesAnclados={{ "2027-01": "cerrado" }}
    />,
  );
  expect(screen.getByText("Real")).toBeInTheDocument(); // 2027-01 = cerrado
  expect(screen.getAllByText("Proyección").length).toBeGreaterThan(0); // 2026-10 sin marca
});

it("muestra el aviso de sin_mapear solo si hay rubros", () => {
  const { rerender } = render(
    <TablaEgreso
      filas={[PROYECTADO]}
      mesCritico="2026-10"
      perforada={true}
      ventanaReconciliada={null}
      sinMapear={["Ajuste raro 4040"]}
    />,
  );
  expect(screen.getByText(/sin clasificar/i)).toBeInTheDocument();
  expect(screen.getByText(/Ajuste raro 4040/)).toBeInTheDocument();
  rerender(
    <TablaEgreso
      filas={[PROYECTADO]}
      mesCritico="2026-10"
      perforada={true}
      ventanaReconciliada={null}
      sinMapear={[]}
    />,
  );
  expect(screen.queryByText(/sin clasificar/i)).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Correr (falla)**

Run: `cd frontend && npx vitest run src/components/proyeccion/TablaEgreso.test.tsx`
Expected: FAIL — props no existen / textos ausentes.

- [ ] **Step 3: Implementar**

En `TablaEgreso.tsx`: importar `import { MarcaOrigen } from "@/components/proyeccion/MarcaOrigen";` y el tipo `MarcaOrigen as TMarca` de `@/lib/proyeccion`. Extender props:

```tsx
interface TablaEgresoProps {
  filas: MesProyeccion[];
  mesCritico: string;
  perforada: boolean;
  ventanaReconciliada: [string, string] | null;
  mesesAnclados?: Record<string, TMarca>;
  sinMapear?: string[];
}
```

En la firma: `}: TablaEgresoProps) {` añadir defaults `mesesAnclados = {}, sinMapear = []`.

Dentro de la celda del mes (tras `{formatMesCorto(m.mes)}` dentro del `<button>`), añadir la marca en una segunda línea. Cambiar el contenido del botón a una columna:

```tsx
<button
  type="button"
  onClick={() => toggle(m.mes)}
  aria-expanded={abierto}
  className="flex w-full flex-col items-start px-4 py-2 text-left hover:underline"
>
  <span className="flex items-center">
    <span className="mr-1.5 inline-block text-ink-faint">{abierto ? "▾" : "▸"}</span>
    {formatMesCorto(m.mes)}
  </span>
  <MarcaOrigen marca={mesesAnclados[m.mes]} />
</button>
```

Al final del `<table>` (tras `</tfoot>`), NO — el aviso va fuera de la tabla pero dentro del `Card`, después del `<div className="overflow-x-auto">`. Añadir tras ese div de scroll y antes de cerrar `</Card>`:

```tsx
      {sinMapear.length > 0 && (
        <div className="border-t border-hairline px-4 py-3 text-apoyo text-ink-soft">
          <span className="font-semibold text-ink">
            {sinMapear.length} rubro{sinMapear.length > 1 ? "s" : ""} con movimiento sin
            clasificar:
          </span>{" "}
          {sinMapear.map((r) => `«${r}»`).join(", ")}. No suman a ningún total del motor —
          revísalos.
        </div>
      )}
```

- [ ] **Step 4: Correr (verde) + no romper los tests previos**

Run: `cd frontend && npx vitest run src/components/proyeccion/TablaEgreso.test.tsx`
Expected: PASS (previos + 2 nuevos).

- [ ] **Step 5: biome + commit**

```bash
cd frontend && npx biome check --write src/components/proyeccion/TablaEgreso.tsx src/components/proyeccion/TablaEgreso.test.tsx
git add frontend/src/components/proyeccion/TablaEgreso.tsx frontend/src/components/proyeccion/TablaEgreso.test.tsx
git commit -m "feat(e1-p6): marca de origen en la tabla + aviso sin_mapear (sin columna nueva)"
```

---

## Task 4: `ComposicionCaja` — línea sólida/punteada + alerta sospechoso

**Files:**
- Modify: `frontend/src/components/charts/ComposicionCaja.tsx`
- Test: `frontend/src/components/charts/ComposicionCaja.test.tsx` (crear si no existe)

**Interfaces:**
- Produces: `ComposicionCaja` acepta `mesesAnclados?: Record<string, TMarca>`. La línea de caja se parte: **sólida** hasta el último mes anclado (cerrado/cerrado_sospechoso/en_ejecucion), **punteada** de ahí en adelante. Punto ámbar en el mes `cerrado_sospechoso`. Sin meses anclados → una sola línea sólida (comportamiento de hoy).

- [ ] **Step 1: Escribir el test (falla)**

`ComposicionCaja.test.tsx` — verificar por conteo de `<polyline>` de caja y presencia del marcador:

```tsx
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ComposicionCaja } from "@/components/charts/ComposicionCaja";
import type { MesProyeccion } from "@/lib/proyeccion";
// reutilizar un factory local mínimo de MesProyeccion (copiar el de TablaEgreso.test)

function mes(over: Partial<MesProyeccion>): MesProyeccion { /* …igual que en TablaEgreso.test… */ return { /* … */ ...over } as MesProyeccion; }

const M = [mes({ mes: "2026-07", caja: "168000000.00" }), mes({ mes: "2026-08", caja: "152000000.00" }), mes({ mes: "2026-09", caja: "140000000.00" })];

describe("ComposicionCaja — marcas de origen", () => {
  it("sin anclaje dibuja una sola línea de caja", () => {
    const { container } = render(<ComposicionCaja meses={M} umbral="125000000.00" ventanaReconciliada={null} />);
    // la línea de caja tiene la clase stroke-cyan; sin split hay una sola
    expect(container.querySelectorAll("polyline.stroke-cyan").length).toBe(1);
  });

  it("con meses anclados parte la línea en sólida + punteada", () => {
    const { container } = render(
      <ComposicionCaja meses={M} umbral="125000000.00" ventanaReconciliada={null}
        mesesAnclados={{ "2026-07": "cerrado", "2026-08": "en_ejecucion" }} />,
    );
    // sólida (anclados) + punteada (proyección) = 2 polilíneas de caja
    expect(container.querySelectorAll("polyline[data-caja]").length).toBe(2);
  });
});
```

(Ajustar los selectores a los `data-caja`/clases que se añadan en Step 3; el objetivo es asertar 1 vs 2 tramos.)

- [ ] **Step 2: Correr (falla)**

Run: `cd frontend && npx vitest run src/components/charts/ComposicionCaja.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implementar el split**

En `ComposicionCaja.tsx` extender props con `mesesAnclados?: Record<string, TMarca>` (default `{}`). Tras calcular `lineaCaja`, derivar el índice de corte y dos polilíneas:

```tsx
const ANCLADAS = new Set(["cerrado", "cerrado_sospechoso", "en_ejecucion"]);
// último índice cuyo mes está anclado (real/en curso). -1 si ninguno.
let corte = -1;
for (let i = 0; i < meses.length; i++) {
  if (ANCLADAS.has(mesesAnclados[meses[i].mes] ?? "")) corte = i;
}
const puntos = cajas.map((v, i) => `${cx(i)},${yCaja(v)}`);
const solido = corte >= 0 ? puntos.slice(0, corte + 1).join(" ") : puntos.join(" ");
const punteado = corte >= 0 && corte < puntos.length - 1
  ? puntos.slice(corte).join(" ") // solapa en el corte para continuidad
  : "";
const sospIdx = meses.findIndex((m) => mesesAnclados[m.mes] === "cerrado_sospechoso");
```

Reemplazar el `<polyline points={lineaCaja} …>` por:

```tsx
<polyline data-caja points={solido} fill="none" className="stroke-cyan" strokeWidth={2.5} vectorEffect="non-scaling-stroke" />
{punteado && (
  <polyline data-caja points={punteado} fill="none" className="stroke-ink-decor" strokeWidth={2} strokeDasharray="7 5" vectorEffect="non-scaling-stroke" />
)}
{sospIdx >= 0 && (
  <circle cx={cx(sospIdx)} cy={yCaja(cajas[sospIdx])} r={5} className="fill-atencion" />
)}
```

(Con `mesesAnclados={}`, `corte=-1` → `solido` = toda la serie, `punteado` vacío → una sola línea = hoy. Candado.)

- [ ] **Step 4: Correr (verde)**

Run: `cd frontend && npx vitest run src/components/charts/ComposicionCaja.test.tsx`
Expected: PASS.

- [ ] **Step 5: biome + commit**

```bash
cd frontend && npx biome check --write src/components/charts/ComposicionCaja.tsx src/components/charts/ComposicionCaja.test.tsx
git add frontend/src/components/charts/ComposicionCaja.tsx frontend/src/components/charts/ComposicionCaja.test.tsx
git commit -m "feat(e1-p6): curva de caja sólida (real/en curso) → punteada (proyección) + alerta sospechoso"
```

---

## Task 5: Cableado en `ProyeccionPage` (leyenda + props + callout) + candado

**Files:**
- Modify: `frontend/src/pages/ProyeccionPage.tsx`
- Test: `frontend/src/pages/ProyeccionPage.test.tsx`

**Interfaces:**
- Consumes: `LeyendaOrigen`, `MesEnCursoCallout`, y las 3 claves de `data`.

- [ ] **Step 1: Escribir/extender el test (falla)**

En `ProyeccionPage.test.tsx` (o el que cubra el render con `data`), añadir un caso con ciclo y uno sin ciclo. Con el patrón de mock del archivo (probablemente mockea `obtenerProyeccion`), afirmar:

```tsx
// con ciclo: leyenda + callout + marca visibles
expect(await screen.findByText(/Origen de cada cifra/i)).toBeInTheDocument();
expect(screen.getByText(/Mes en curso/i)).toBeInTheDocument();

// candado sin ciclo (meses_anclados {}, mes_en_curso null, sin_mapear []):
expect(screen.queryByText(/Origen de cada cifra/i)).not.toBeInTheDocument();
expect(screen.queryByText(/Mes en curso/i)).not.toBeInTheDocument();
```

(Ajustar al estilo de mock del archivo existente; añadir las 3 claves al objeto `Proyeccion` de prueba.)

- [ ] **Step 2: Correr (falla)**

Run: `cd frontend && npx vitest run src/pages/ProyeccionPage.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Cablear en `ProyeccionPage.tsx`**

Importar `LeyendaOrigen` y `MesEnCursoCallout`. En `ProyeccionContenido` (recibe `data`):

- Renderizar `{Object.keys(data.meses_anclados ?? {}).length > 0 && <LeyendaOrigen />}` encima del `ChartCard` (o de la tabla).
- Pasar `mesesAnclados={data.meses_anclados}` a `<ComposicionCaja … />` y a `<TablaEgreso … />`, y `sinMapear={data.sin_mapear}` a `<TablaEgreso />`.
- Renderizar `{data.mes_en_curso && <MesEnCursoCallout mesEnCurso={data.mes_en_curso} />}` entre el `ChartCard` y la tabla.

Todo guardado con `?? {}` / `?? []` / `?? null` por si un mock viejo no las trae. Candado: sin ciclo, todas las guardas son falsas → nada nuevo se pinta.

- [ ] **Step 4: Correr (verde) + suite frontend completa**

Run: `cd frontend && npx vitest run src/pages/ProyeccionPage.test.tsx`
Expected: PASS.
Run: `cd frontend && npx vitest run`
Expected: toda la suite verde (los tests que construyen `Proyeccion` sin las claves nuevas siguen pasando por las guardas `??`; si alguno tipa estricto, añadir las 3 claves vacías al mock — cambio de test aditivo).

- [ ] **Step 5: build + biome + commit**

Run: `cd frontend && npx biome check --write src/pages/ProyeccionPage.tsx src/pages/ProyeccionPage.test.tsx && npm run build`
Expected: biome limpio + build OK.

```bash
git add frontend/src/pages/ProyeccionPage.tsx frontend/src/pages/ProyeccionPage.test.tsx
git commit -m "feat(e1-p6): cablea leyenda + callout mes en curso + props de origen (candado sin ciclo)"
```

---

## Cierre (fuera de tasks — tras verde completo)

1. **Capturas Playwright (exigencia del gate PR6-I):** levantar el front con datos de ejemplo y capturar mín. 2 pantallas (con ejecución/marcas · sin ciclo/fallback), ideal 3 (+ mes sospechoso). Guardar en `planning/phases/e1-anclaje-ejecucion/auditorias/PR6-I/`. Si el front en vivo no tiene datos anclados, usar un test/story de Playwright que monte la página con un `Proyeccion` mock que incluya las 3 claves.
2. **Gate PR6-I:** SOLICITUD + EVIDENCIA (vitest + build + biome + **capturas embebidas/adjuntas**) + PAQUETE.pdf. El CEO lo sube a Kimi. Umbral ≥9.0.
3. **PR** desde `feat/e1-p6-frontend-marcas`; CI verde (frontend + build); no hay backend nuevo. **No mergear sin GO Kimi + GO CEO.**
4. Con GO: squash-merge + tracker (Tareas E1-P6 Hecha + Gates GATE-KIMI E1-P6) + memoria → **E1 TERMINADO**. Cola: FIX-I-2, UX de copys, dependabot, checklist G1.

## Self-Review (cobertura del spec)

- **(a) marcas en tabla + leyenda** → Task 1 (componente) + Task 3 (tabla) + Task 5 (leyenda). ✔
- **gráfico sólido/punteado + sospechoso** → Task 4. ✔
- **(b) comparación mes en curso** → Task 2 (callout) + Task 5 (render). Nota: la sub-comparación numérica depende de datos disponibles (Step 1 de Task 2 lo resuelve sin inventar). ✔ (con degradación honesta documentada)
- **(c) B13 completitud + fórmula** → Task 2. ✔
- **(d) sin_mapear** → Task 3. ✔
- **(e) efecto-arrastre** → Task 2. ✔
- **(f) sin scroll lateral** → Task 3 (marca sin columna nueva). ✔
- **Candado sin ciclo** → Task 4 (una línea) + Task 5 (guardas). ✔
- **Marca ≠ salud de caja** → Task 1 (tipo separado) + Task 3 (coexisten). ✔
- **Tipos consistentes:** `MarcaOrigen`/`MesEnCurso` definidos en Task 1 y usados igual en 3/4/5; props `mesesAnclados`/`sinMapear`/`mesEnCurso` con los mismos nombres en todos los consumidores. ✔
- **Evidencia visual (gate)** → Cierre §1 (Playwright). ✔
