# E1 · P6 — Frontend: marcas de origen + mes en curso (ÚLTIMA pieza de E1)

**Fecha:** 2026-08-08 · **Épico:** E1 · **Plan padre:** `docs/COMPAS_PLAN_E1_Anclaje_a_la_Ejecucion.md` (pieza **P6**, §6) ·
**Consume:** el shape de P5 (`meses_anclados`, `sin_mapear`, `mes_en_curso`) · **Criterio:** honestidad **R5**, **B13**.
**Mockup aprobado (CEO 2026-08-08):** look "tal cual" + copys "claros". Gate de diseño Kimi **9.2 GO al spec**.
**Al cerrar P6, E1 queda terminado.**

## 1. Problema

Hacer visible en la vista **Proyecciones** el origen de cada cifra que el backend ya expone (P5),
sin ensanchar la tabla ni romper la vista cuando no hay ciclo. El frontend hoy no consume las 3
claves nuevas; solo presenta el motor + el semáforo de salud de caja.

## 2. Hallazgos del terreno (frontend actual)

- `frontend/src/lib/proyeccion.ts` — cliente + tipos. El `interface Proyeccion` **no tiene** las 3
  claves de P5 → hay que añadirlas (aditivo). Ya existe `type EstadoMes = "ok"|"critico"|"negativo"`
  = **salud de caja**; la marca de **origen** es una **dimensión distinta** — NO reusar ese tipo.
- `frontend/src/pages/ProyeccionPage.tsx` — orquesta KPIs + `ChartCard(ComposicionCaja)` + `TablaEgreso`.
- `frontend/src/components/proyeccion/TablaEgreso.tsx` — tabla; 1ª columna (mes) sticky; columna
  "Estado" con badge de salud (`ESTADO_ESTILO`/`ESTADO_SIMBOLO`); filas expandibles; `overflow-x-auto`.
- `frontend/src/components/charts/ComposicionCaja.tsx` — **SVG hecho a mano** (`<polyline>`, `<line>`,
  `strokeDasharray`), sin recharts → lo sólido/punteado por origen se hace **partiendo la polilínea**
  en el límite anclado/proyectado, sin librerías nuevas.
- Tokens (`src/index.css`): cyan `#0fa9b8`, positivo `#15803d`, atención `#b45309`, crítico `#b91c1c`,
  ink/hairline/surface; **app light-only** ("Fondo blanco"). Raleway/Montserrat.

## 3. Contrato de tipos (aditivo, en `lib/proyeccion.ts`)

```ts
export type MarcaOrigen =
  | "cerrado" | "cerrado_sospechoso" | "en_ejecucion" | "presupuesto";

export interface MesEnCurso {
  mes: string;            // 'YYYY-MM'
  cargado_hasta: string | null; // 'YYYY-MM-DD' | null (aún sin tx)
  dia: number | null;
  formula: string;
}

// añadidos a interface Proyeccion (todos opcionales para no romper mocks viejos):
meses_anclados: Record<string, MarcaOrigen>;  // {} sin anclaje
sin_mapear: string[];                          // [] si nada
mes_en_curso: MesEnCurso | null;               // null sin mes en ejecución
```

Como P5 emite siempre las 3 claves, el front las lee directo; los tests con mocks parciales las
tratan como `?? {}` / `?? []` / `?? null` para no romper.

## 4. Diseño de UI (mockup aprobado)

Todo lo nuevo es **condicional al ciclo**: si `meses_anclados` está vacío y `mes_en_curso` es null,
la UI queda **idéntica a hoy** (candado).

- **(a) Marcas de origen (tabla).** Punto+etiqueta en la **1ª columna sticky** (el mes), NO columna
  nueva → respeta "sin scroll lateral". Vocabulario de `marcas_origen`: Real (cerrado) · En curso
  (en_ejecucion) · Presupuesto · Proyección (meses sin marca) · **Revisar carga** (cerrado_sospechoso,
  con ⚠ ámbar). Leyenda encima de la tabla/gráfico. La marca de origen **no reemplaza** el badge de
  salud de caja (columna Estado) — coexisten.
- **Gráfico (`ComposicionCaja`).** La curva de caja: **sólida** en meses reales + en curso, **punteada**
  del primer mes proyectado en adelante (partir la polilínea en el límite). Punto de alerta ámbar en el
  mes `cerrado_sospechoso`.
- **(b) Comparación del mes en curso.** Callout dedicado + sub-fila en la tabla bajo el mes en curso:
  **Proyectado · Ejecutado (al día N) · Desviación** (color según signo).
- **(c) Completitud B13.** En el callout: "Cargado hasta el día N" + **la fórmula visible** en lenguaje
  de negocio (honestidad R5): "ejecutado + lo que resta del presupuesto". El backend manda la fórmula
  técnica en `mes_en_curso.formula`; el front muestra la versión de negocio (constante) + el día.
- **(d) `sin_mapear`.** Aviso al pie de la tabla, **solo si** la lista no está vacía: "N rubros con
  movimiento sin clasificar: …".
- **(e) Efecto-arrastre.** Copy contextual junto al callout: "Cuando cierres [mes], su ejecución real
  reemplaza esta estimación y arrastra el resto del año."
- **(f) Sin scroll lateral.** Garantizado por (a): las marcas no añaden columnas.

### Copys aprobados (CEO)

- Aviso B13: "Cargado hasta el N de [mes]" + "Los días que faltan se estiman así: ejecutado + lo que
  resta del presupuesto."
- Sospechoso: "[Mes] quedó cerrado con una ejecución muy por debajo de lo presupuestado. Puede que
  falten movimientos por cargar — revísalo. (Se ancla igual; solo se marca.)"
- Arrastre: "Cuando cierres [mes], su ejecución real reemplaza esta estimación y arrastra el resto del año."
- sin_mapear: "N rubros con movimiento sin clasificar: «…». No suman a ningún total del motor — revísalos."

## 5. Estructura de archivos

- **Modify** `frontend/src/lib/proyeccion.ts` — tipos `MarcaOrigen`, `MesEnCurso`, 3 campos en `Proyeccion`.
- **Create** `frontend/src/components/proyeccion/MarcaOrigen.tsx` — punto+etiqueta + leyenda (presentación
  pura del vocabulario; una verdad para tabla y callout). Constantes de color/símbolo por marca.
- **Create** `frontend/src/components/proyeccion/MesEnCursoCallout.tsx` — comparación + B13 + arrastre.
- **Modify** `frontend/src/components/proyeccion/TablaEgreso.tsx` — marca en la 1ª columna + sub-fila de
  comparación del mes en curso + aviso `sin_mapear` al pie. Recibe `mesesAnclados`, `mesEnCurso`,
  `sinMapear` por props.
- **Modify** `frontend/src/components/charts/ComposicionCaja.tsx` — partir la polilínea sólida/punteada
  según el límite anclado; punto de alerta en sospechoso. Recibe `mesesAnclados` por prop.
- **Modify** `frontend/src/pages/ProyeccionPage.tsx` — leyenda + pasar las 3 nuevas props hacia abajo +
  render del callout.
- **Tests (vitest):** `.test.tsx` por componente nuevo + extensiones a los existentes.

## 6. Tests (vitest, TDD)

1. **Marca por estado** — `MarcaOrigen` renderiza el label/símbolo correcto para las 4 marcas + sospechoso.
2. **Marcas en la tabla** — cada mes muestra su marca según `mesesAnclados`; un mes sin entrada → "Proyección".
3. **Comparación del mes en curso** — la sub-fila/callout muestra proyectado/ejecutado/desviación con el signo correcto.
4. **Aviso de completitud (B13)** — "cargado hasta el día N" + la fórmula de negocio visible.
5. **`sin_mapear` visible** — aparece con lista si hay; ausente si `[]`.
6. **Candado sin ciclo** — con `meses_anclados={}`, `mes_en_curso=null`, `sin_mapear=[]`: no se renderiza
   ninguno de los bloques nuevos (la tabla/vista queda como hoy).
7. **Gráfico** — (si es testeable) la polilínea se parte en el límite; el punto de alerta aparece en el sospechoso.

## 7. Candados

- **Sin ciclo → UI idéntica a hoy** salvo los bloques nuevos ocultos. Consumidores viejos ignoran las
  claves nuevas (tipos aditivos/opcionales).
- **Sin scroll lateral** en la tabla (marcas sin columna nueva).
- **Marca de origen ≠ salud de caja** (`EstadoMes`): dimensiones separadas, no se mezclan.
- **Backend intacto:** P6 es solo frontend (cero cambios de backend; R0 trivial). Dinero: el front nunca
  hace `Number` sobre montos (regla 1) — formato con `formatCOP`/`decimal.js-light`.
- **build + biome verdes.**

## 8. Entrega y gate

- **Rama:** `feat/e1-p6-frontend-marcas` (desde main post-9f011ef). **Un PR.**
- **Gate Kimi normal ≥9.0**, paquete `planning/phases/e1-anclaje-ejecucion/auditorias/PR6-I/`
  (SOLICITUD + EVIDENCIA + PAQUETE.pdf).
- **EXIGENCIA NUEVA DEL GATE (Kimi etapa62):** el paquete debe incluir **capturas de pantalla reales**
  de la página implementada — mín. 2 (con ejecución/marcas · sin ciclo/fallback), ideal 3 (+ mes
  sospechoso) — además de vitest + build + biome. Se capturan con **Playwright** (ya en el stack).
- **No mergear sin GO Kimi + GO CEO.**
