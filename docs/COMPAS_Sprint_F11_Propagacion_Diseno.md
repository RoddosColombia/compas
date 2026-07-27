# Sprint F1.1 — Propagación del sistema de diseño, pantalla por pantalla

**Fecha:** 2026-07-27 · **Prerequisito:** main con F1+C3 mergeados, deploy de prod sano (verificar antes de arrancar)
**Regla de oro del sprint:** cada pantalla debe responder ¿cómo vamos? → ¿bien o mal? → ¿qué hago?, y pasar la prueba de los 10 segundos. F1 dio las herramientas (tokens, KpiTileV2, ChartCard, CashCurve anotada, formato es-CO); F1.1 las lleva a TODAS las pantallas. Incremental: **un commit por pantalla, revisable por separado** — nada de big bang.
**Orden de ejecución** (impacto primero): §0 pendientes → §1 barridos → §2 Proyecciones → §3 Escenarios → §4 Dashboards → §5 Control → §6 Cabina/Barra → §7 Reportes → §8 IVA + Flujo diario.

---

## 0. Pendientes técnicos heredados (antes de tocar diseño)

1. **Fix del cache de sensibilidad** (bug conocido del QA de C3): el fingerprint no incluye los valores de los parámetros — dos guardados el mismo día sirven el tornado viejo. Incluir hash de los campos del documento en el fingerprint + test (guardar → cambiar → guardar → el tornado refleja el segundo valor).
2. Confirmar deploy de prod sano y migración CR-002 visible (bloque ⑦ con 4 componentes en Supuestos).
3. `formatDelta` gana `direccionBuena: "sube" | "baja"` (default "sube") — en Control y Dashboards bajar el gasto es bueno; el color debe seguir la semántica del negocio, no el signo.
4. **Fix `CashCurve anotada` (hallazgo QA visual en prod, 2026-07-27):** la anotación del mínimo sale SIEMPRE en `critico` — en prod hoy se ve "feb-27 · $ 536,7 M" en rojo con la caja sana. Rojo = crítico (semántica F1): la anotación y su punto usan `critico` SOLO si el mínimo perfora el umbral; si no, `ink`/neutro. Test con ambos casos.

## 1. Barridos globales (mecánicos, un solo commit)

- **Muere `KpiTile` v1**: migrar TODOS los usos restantes a `KpiTileV2` (con comparación o contexto obligatorios — si un uso no tiene contra qué comparar, escribir el contexto en lenguaje llano; nada de números desnudos). Borrar el componente v1 al final: el build debe fallar si queda un uso.
- **Cero `text-[10px]` / `text-xs` sueltos**: todo a la escala de roles (`text-apoyo` mínimo). El Sidebar incluido.
- **Cero texto en `ink-decor`** (#94A3B8): grep y a `ink-faint` mínimo.
- **Badges y semáforos** `green/amber/red` → `positivo/atencion/critico` **siempre con símbolo o texto** (los semáforos de Control ya tienen label — conservarlo).
- **Política de precisión por contexto** (F1 §3): tablas de datos SIN centavos (`formatCOP` → variante sin decimales); centavos SOLO en conciliación, cierre y exportes (ahí la exactitud al centavo es el punto). KPIs ya van compactos.
- **Pasada móvil mínima**: la auditoría encontró cero media queries; el AppShell ya tiene sidebar móvil — verificar que cada pantalla propagada no rompa en 390 px (grids con `sm:`/`md:`, tablas con scroll horizontal, barra fija de C1 sin tapar contenido). No es el rediseño móvil completo: es el piso de usabilidad.

## 2. Proyecciones (la más usada después de Inicio — la más lejos del estándar)

- **KPIs:** 6 tiles apretados → **4 KpiTileV2**: Piso de caja (delta vs. umbral, mes en contexto), Meses bajo el mínimo (`n de N` + cuál), Capital requerido (contexto "para sostener el umbral de X"), y **Runway reformulado**: cuando el motor devuelve null → valor `Sin límite`, contexto "la caja crece al ritmo actual"; cuando hay quema → `N meses` con contexto "al ritmo promedio". Caja final pasa a texto del pie del gráfico (a 60 meses es una cifra astronómica que no decide nada — la auditoría lo midió).
- **Gráfico protagonista:** `CashCurve anotada` dentro de `ChartCard` con conclusión dinámica (mismo patrón de Inicio), **default 18 meses** con el juicio calculado a horizonte largo (patrón F1 de Inicio — reutilizar, no reinventar). El selector de horizonte existente se conserva como elección explícita.
- **La tabla de 60–180 filas** (el "volcado" de la auditoría): por defecto muestra **la ventana del gráfico** (18 filas) con "Ver los N meses completos" que expande; columnas sin centavos; header sticky; primera columna sticky en overflow; badge de estado con símbolo; fila del mes crítico resaltada y enlazada desde el titular (anchor, como Control).
- **Criterio de aceptación del CEO (captura 2026-07-27):** en la Proyecciones actual señaló cuatro fallas que esta sección DEBE eliminar — cifras desbordadas de las tarjetas (Piso y Caja final cortados), Runway "—" sin explicación, gráfica sin eje de tiempo ni valores, y curva que "no dice nada". F1.1 §2 se da por terminada solo si las cuatro desaparecen: cero truncamientos (compacto + hover), Runway siempre con lectura ("Sin límite · la caja crece al ritmo actual"), ejes con meses y montos, mínimo anotado y ventana de 18 m por defecto.
- **Rendimiento (la app "se pega", top-3 de la auditoría):** medir con Profiler antes/después — la hipótesis es que las 180 filas × 8 columnas + SVG denso bloquean el render. El default de 18 filas debería resolverlo; si no, virtualizar la tabla expandida. **Criterio verificable: navegar Inicio → Proyecciones → Dashboards sin congelamientos perceptibles (>1 s).**

## 3. Escenarios (el gráfico actual no comunica — 3 líneas superpuestas)

- **Protagonista nuevo con los MISMOS datos:** banda de rango (área entre pesimista y optimista, tinte suave) + línea base encima, **zoom a 18–24 meses** donde los escenarios de verdad divergen, umbral etiquetado, y **anotación del piso de cada escenario** (pesimista -$226 M · base -$64 M · optimista +$17 M — esas tres cifras son la pantalla entera y hoy son invisibles en la escala de 5 años).
- Las 3 tarjetas comparativas → `KpiTileV2` por escenario con tono semántico según piso vs. umbral (pesimista `critico`, base `atencion`, optimista `positivo` — con los datos actuales) y contexto "capital requerido: X".
- Conclusión del ChartCard escrita desde los datos: "En el peor caso faltan $ 256 M; en el mejor, sobra margen".

## 4. Dashboards (barras correctas, cero conclusiones)

- Cada gráfico envuelto en `ChartCard` con **título-conclusión calculado** ("La cobranza proyectada se multiplica por 7 en 24 meses"), subtítulo técnico y pie con fuente.
- **Jerarquía**: Cobranza mensual = protagonista (2×); Colocación y Cartera por añada = soporte.
- **Cartera por añada**: decisión de la verificación del motor — hasta el run-off (~fin 2027) es un espejo de la colocación; **anotarlo en el pie** ("las cohortes aún no terminan su plazo: el desglose igualará a la colocación hasta ~dic-2027") o colapsarla por defecto. Elegir lo primero (información honesta > ocultar).
- **Mora por tramo**: `EstadoVacio` accionable → "Sube el LoanTape semanal de SISMO-V3 →" (botón ya existe; formalizar el patrón).
- Barras: etiquetas ya están por fila (bien); aplicar tokens, alto máximo con scroll para 24+ filas, y valores sin centavos.

## 5. Control / Presupuesto (ya tiene la inteligencia de C2 — falta el vestido)

- KpiTiles → V2 con contexto ("Disponible: lo que queda del presupuesto aprobado").
- Tabla → política sin centavos, tokens, símbolo en el semáforo.
- `QueExigeAtencion` ya cumple F1 — solo revisar `direccionBuena` cuando el delta entre a los mensajes.
- El selector de mes y el toggle Por categoría/Por cuenta → patrón `FiltroBarra` (§9): mismo lugar, estado visible.

## 6. Cabina del mes + MesStatusBar (funcionales de C2 — vestirlas)

- Tiles y resúmenes → V2; `BarraEjecucion` con semánticos + símbolo; stepper con tokens F1 (sigue siendo texto — las florituras no son el punto); `EstadoVacio`/`Cargando`/`ErrorEstado` en todas las tarjetas.
- La barra global: tipografía de la escala, colores semánticos (ya casi cumple).

## 7. Reportes (pantalla; el PDF es Fase 6)

- Resumen ejecutivo → el patrón titular de juicio de Inicio (misma frase reconciliadora, mismos datos) + 4 tiles V2 + `CashCurve anotada` + tabla de escenarios con formato correcto.
- El botón Descargar PDF se conserva tal cual — **el rediseño del PDF y el resumen ejecutivo automático van en Fase 6**, no aquí.

## 8. IVA + Flujo diario (rápidas)

- **IVA:** `EstadoVacio` accionable (hoy es texto plano). El destino real de "cargar facturas" no tiene UI: enlazar a `/cargas` con el texto honesto ("las facturas entran por Cargas") o dejar sin link con quién puede hacerlo — decidir contra el código.
- **Flujo diario:** la columna-sparkline "Evolución del saldo" **se elimina** (la auditoría la midió: 3 px que no comunican nada) y en su lugar entra un **gráfico del saldo arriba de la tabla** (CashCurve simple con la serie diaria — el componente ya lo soporta); KPIs → V2; tabla sin centavos… **excepción**: aquí los montos son movimientos reales — mantener centavos (política F1 §3: dato operativo-contable). Filtros → `FiltroBarra`.

## 9. `FiltroBarra` (el componente §5.4 de F1, ahora sí con consumidores)

Formalizarlo con sus 3 usos reales (Proyecciones, Control, Flujo diario): siempre en `acciones` del PageHeader, estado visible, "Limpiar" cuando difiere del default. Horizonte con opciones consistentes en todo el producto (18 m default · 3 años · 5 años · todo).

## 10. Tests y DoD

1. Por pantalla: render con tokens nuevos (sin `text-[10px]`, sin v1), conclusiones dinámicas correctas con fixtures, estados vacíos accionables.
2. Barridos verificables por grep en CI o test: `KpiTile` v1 sin referencias, `text-[10px]` = 0 usos, `ink-decor` solo en decorativos.
3. Rendimiento §2: sin congelamientos >1 s en la navegación completa (medido, no sentido).
4. `lint + tests + build` verdes por commit; diff 100 % frontend.
5. **Prueba de los 10 segundos** (guion entregado) aplicada al final a **Proyecciones y Dashboards** — las dos más densas. Quien la aplica no puede ser Andrés. Resultado documentado; si falla, se corrige antes de dar F1.1 por cerrado.

## 11. Fuera de alcance

Gráficos NUEVOS (mora por cosecha, embudo de cobranza, rotación de repuestos → **Fase 4**, necesita LoanTape/datos), PDF y resumen ejecutivo automático (**Fase 6**), alertas (**Fase 7**), rediseño móvil completo (solo el piso del §1), sets nombrados de supuestos (C3.1), y cualquier cambio de backend salvo el fix §0.1.

---

### Después de F1.1 (el mapa de lo que falta, para que "falta mucho" tenga forma)

1. **Fase 4 — Catálogo de gráficos nuevos:** mora por cosecha y envejecimiento (con LoanTape cargado), embudo de cobranza, proyección vs. real por mes (cuando el ciclo genere cierres), concentración por producto. Cada uno con su pregunta y su decisión.
2. **Fase 6 — Lo que la app genera:** PDF de Reportes con el sistema de diseño + resumen ejecutivo automático (qué pasó, por qué importa, qué decidir).
3. **Fase 7 — Del hallazgo a la acción:** alertas con umbral y prioridad por plata.
4. **Móvil completo** (media queries reales, la auditoría lo tiene como top-5).
