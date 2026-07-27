# Análisis de brecha — Brief "motor configurable" vs. lo construido

**Fecha:** 2026-07-27 · **Base de comparación:** código real en main (C1+C2+C3+F1 desplegados; F1.1 especificada, en ejecución) + auditoría Fase 0 + verificación del motor.
**Veredicto en una frase:** el brief no es una lista de mejoras a lo actual — es un **cambio de categoría del producto**: de "motor paramétrico del negocio RODDOS, verificado al peso" a "plataforma de planeación financiera de propósito general con motor de fórmulas". La fundación construida (borrador+preview, sensibilidad, rolling forecast, ciclo, rubros administrables, sistema de diseño) apunta en la dirección correcta y se reutiliza casi toda; el corazón nuevo (fórmulas, techo de gasto, goal seek, obligaciones genéricas, tablero configurable) no existe.

## 1. Las cuatro preguntas del objetivo — cobertura hoy

| Pregunta | Estado | Qué existe / qué falta |
|---|---|---|
| ¿Cuánto puedo gastar hoy sin comprometer el futuro? | **NO cubierta** | El techo de gasto recomendado (§4.7) no existe. Buena noticia: es una función de optimización sobre el motor actual (que es puro y rápido) — no exige el motor de fórmulas. |
| ¿Cómo me afecta a futuro lo ya ejecutado? | **Parcial** | El rolling forecast existe y funciona (cierre re-ancla el saldo; "Realidad vs. proyección" en Inicio). Falta: la vista proyectado/ejecutado/desviación por rubro, el efecto arrastre cuantificado, y elegir la base de reproyección. |
| ¿Qué pasa si subo un gasto específico desde un mes X? | **Parcial** | C3 entregó exactamente esta mecánica (borrador → preview en vivo → delta vs. vigente → nada se guarda) **pero solo para las variables globales del motor**. Falta: ajustes por rubro/categoría con mes de vigencia, y escenarios nombrados/guardables/comparables (hoy: 3 presets fijos). |
| ¿Qué debo lograr para cerrar con solvencia? | **Parcial** | La sensibilidad (tornado) existe desde C3. Faltan: búsqueda de objetivo (goal seek), punto de quiebre por variable, rango/matriz de escenarios. Igual que el techo: son solvers sobre el motor existente. |

## 2. Principio rector "nada en duro" — dónde está la app HOY, verificado en código

**Ya cumple:** rubros CRUD (crear/editar/reordenar/desactivar, soft-delete con histórico protegido) · mínimo de caja editable · horizonte configurable por request · umbral y parámetros del motor editables con impacto en vivo (C3) · simulación sin escribir datos reales (C3, exactamente como lo pides) · nota/auditoría de cambios · reglas de clasificación bancaria administrables · gastos recurrentes como plantilla administrable · componentes de alistamiento configurables (CR-002) · modelos de moto administrables.

**Cableado en el código hoy (los antipatrones que rechazas, con nombre y apellido):**

1. **Los 6 grupos del plan de cuentas** son un enum (`RubroGrupo`): rubros dinámicos ✓, categorías completas NO.
2. **Horizonte con tope 180** (`HORIZONTE_MAX = 180`): tus 240 meses no pasan sin cambio de código. Granularidad: mensual fija (semanal interna para recaudo; diaria solo en flujo real).
3. **El ingreso NO es editable**: sale del modelo de colocación (motos × cuotas). No hay ingreso proyectado por mes ni líneas de ingreso (§4.2 completa es nueva).
4. **Escenarios = 3 presets fijos** (pesimista/base/optimista, solo mora/recuperación).
5. **Umbrales de semáforo y alertas** (90/100 % del control, +15 pts de QueExigeAtencion) son constantes — comentadas y con nombre, pero constantes.
6. **La deuda de inversores es un caso especial** del motor (no una "obligación" genérica); **Auteco es paramétrico global** (plazo 90/150, tasa 1,6 % — la lógica que pides reutilizar SÍ existe y está verificada contra el golden master), pero **no hay registro factura a factura con plazo elegido por factura**: el motor proyecta el lote, no facturas individuales.
7. **Tarjetas e indicadores fijos** por pantalla (el tablero configurable §4.10 es nuevo).
8. **El "hito de solvencia" no existe como concepto**: el motor calcula el mes más ajustado; nadie puede fijar "mayo" como objetivo configurable contra el cual medir todo.
9. **No hay motor de fórmulas**: las variables son parámetros de un modelo FIJO (el negocio BNPL de RODDOS), no variables definibles con dependencias. §4.8 es el corazón nuevo.

## 3. Cobertura del alcance detallado (§4), ítem por ítem

| Sección | Veredicto | Detalle |
|---|---|---|
| 4.1 Rubros dinámicos | **~80 % cubierto** | CRUD completo con soft-delete ✓; totales recalculan ✓. Falta: crear categorías (grupos) nuevas, y "copiar mes anterior" explícito (el sugerido histórico de C1 cumple el espíritu con algo mejor: prom. 3 m + tendencia). |
| 4.2 Ingreso proyectado | **NO** | Todo nuevo: ingreso editable por mes, líneas de ingreso, resultado y margen, cumplimiento vs. real. |
| 4.3 Flujo diario analítico | **~30 %** | KPIs de resumen ✓; gráfica del saldo viene en F1.1; mínimo de caja como referencia viene con ella. Nuevo: día de saldo más bajo, filtros por categoría/estado, proyectado vs. ejecutado diario, subtotales por categoría, alertas. |
| 4.4 Gráfica de proyecciones | **~50 %** | F1/F1.1 cubren: notación compacta con valor exacto en hover, ejes con mes/año, mes actual sombreado, sin desbordes (el KpiTileV2 lo hace imposible por diseño). Nuevo: área apilada por composición (Auteco/gasto/ingreso), tooltips por mes (el SVG actual no tiene tooltips). |
| 4.5 Simulador administrable | **~40 %** | C3 = el patrón exacto (panel de supuestos, recálculo sin tocar datos, delta vs. base, descartar). Nuevo: ajustes por rubro con vigencia (mes inicio/fin), escenarios nombrados/duplicables/comparables en una gráfica. |
| 4.6 Proyección ↔ ejecución | **~40 %** | Re-anclaje al cierre ✓; real sólido vs. proyectado punteado viene en F1.1 (zona sombreada). Nuevo: 3 columnas por rubro, efecto arrastre cuantificado, base de reproyección elegible. |
| 4.7 Techo de gasto | **NO** | Todo nuevo. Es la tarjeta-respuesta de la pregunta 1 y depende del "hito" configurable (tampoco existe). |
| 4.8 Motor de variables y fórmulas | **NO (el corazón)** | Variables definibles, fórmulas con dependencias y detección circular, mapa de dependencias, obligaciones como entidad genérica de dos naturalezas con facturas registrables. Lo único que existe: la lógica de términos Auteco (global, verificada) para generalizar, y el modelo Factura del IVA como referencia de registro. |
| 4.9 Goal seek / sensibilidad / quiebre | **~25 %** | Sensibilidad ✓ (C3). Goal seek, punto de quiebre y matriz de rango: nuevos — pero baratos sobre el motor puro (bisección sobre `proyectar()`, que corre 14 veces en <0,5 s). |
| 4.10 Tablero configurable | **NO** | Tarjetas elegibles, indicadores propios, vistas con nombre, export Excel/CSV, import de reales. Todo nuevo (import de extractos bancarios sí existe). |
| 4.11 Base de gastos fijos | **~35 %** | La plantilla administrable existe (módulo Gastos recurrentes, con vigencias). Nuevo: detección automática por histórico, clasificación en 3 niveles, conexión al techo de gasto, alertas de recurrente ausente/nuevo. |

**Transversales (§5):** formato es-CO compacto + exacto en hover ✓ (F1) · sin desbordes ✓ (F1/F1.1) · parámetros configurables: los del motor ✓, los de alertas NO · simulación sin escribir ✓ · **240 meses: hoy el tope es 180 y el rendimiento largo es justo el problema medido en la auditoría — F1.1 lo ataca con ventanas, la agregación por año no existe** · migración sin perder histórico: es la práctica establecida (CR-002 lo demostró) · lenguaje visual actual: garantizado, el sistema F1 es nuestro.

## 4. La decisión de arquitectura que el brief esconde (léela antes de encargar)

El activo más valioso de COMPAS hoy es que su motor es una **réplica verificada al peso** del modelo financiero que tú y Fabián construyeron — paridad golden-master en 176 meses, Decimal de punta a punta, semanas reales de cobro. Esa verificabilidad existe *porque* el modelo está fijo en el código.

Un **motor de fórmulas genérico** (§4.8 pleno: cualquier rubro = fórmula sobre variables definibles) es otra clase de software — un motor de hoja de cálculo con resolución de dependencias. Se puede construir, pero: (a) la paridad golden-master deja de proteger lo que definas por fórmula — la verificación pasa a ser tuya, fórmula por fórmula, como en Excel; (b) es el ítem más caro del brief por lejos; (c) el riesgo de reintroducir los errores de los que COMPAS te sacó (el Excel) es real si no se acompaña de trazabilidad fuerte.

**Mi recomendación — híbrido en capas, que cubre las 4 preguntas sin demoler lo verificado:**

- **Capa 1 (el motor actual, intacto):** sigue siendo la fuente de verdad del negocio BNPL — colocación, recaudo, Auteco, deuda. Verificado, rápido, auditado.
- **Capa 2 (ajustes por rubro con vigencia):** deltas configurables sobre el resultado del motor — "+X en arriendos desde sep-2026", "ingreso −10 % desde ene-2027" — con la mecánica de C3 (borrador → preview → guardar como escenario nombrado). Cubre 4.5 y la pregunta 3 completas sin motor de fórmulas.
- **Capa 3 (solvers sobre el motor):** techo de gasto (4.7), goal seek, punto de quiebre (4.9) — funciones de búsqueda sobre `proyectar()`, que ya corre en milisegundos. Con el "hito de solvencia" como entidad configurable nueva (mes objetivo + mínimo + colchón).
- **Capa 4 (entidades generalizadas):** obligaciones de dos naturalezas (generalizando la lógica Auteco existente, factura a factura con plazo como palanca — tu §7 completo), líneas de ingreso editables (4.2), grupos de rubros dinámicos, alertas como reglas.
- **Capa 5 (si aún la quieres después de 1–4):** el motor de fórmulas pleno y el tablero configurable. Mi apuesta: con las capas 1–4 las cuatro preguntas quedan respondidas y esta capa puede resultar innecesaria — decisión tuya con el producto en la mano.

Esto además respeta tu propio NORTE ("elegir siempre lo que acerque a proyectar caja y decidir") y tu instrucción explícita del brief: reutilizar la lógica Auteco existente como fuente única de verdad.

## 5. Choques a resolver antes de encargar (respuestas tuyas, no técnicas)

1. **240 meses vs. tope 180:** ampliar el tope es trivial; hacerlo *fluido* exige la agregación por año/trimestre del §5 — va junto.
2. **El hito "mayo":** el NORTE decía may-2027 y hoy la proyección con datos reales ya no perfora. ¿El hito configurable arranca en may-2027 igual, o defines otro?
3. **"Un solo modelo de cálculo":** hoy presupuesto (sugerido histórico) y proyección (motor paramétrico) son dos motores conectados por el cierre. Unificarlos de verdad es parte de la capa 4 — y hay que decidir cuál manda cuando difieran.
4. **Prioridad entre este brief y el plan vigente:** F1.1 (en ejecución) y las Fases 4/6/7 del rediseño siguen siendo necesarias — el brief las asume ("mantener el lenguaje visual actual"). Propongo: terminar F1.1 → luego este brief por capas (1–4) → el catálogo de gráficos (Fase 4) se funde con el §4.4 del brief para no hacerlo dos veces.

## 6. Respuesta directa a tu pregunta

¿Lo logramos cubrir con el trabajo en desarrollo? **No — el trabajo en desarrollo construyó los cimientos correctos (y varios patrones que el brief pide ya existen tal cual: simulación sin riesgo, sensibilidad, impacto en vivo, rolling forecast, administrables con soft-delete), pero el brief pide un producto sustancialmente más ambicioso.** Ninguno de los sprints C1–F1.1 se pierde: son la condición de posibilidad de esto. Lo nuevo grande: fórmulas/variables (4.8), techo de gasto + hito (4.7), goal seek (4.9), ingreso editable (4.2), escenarios por rubro nombrados (4.5), obligaciones genéricas con facturas (4.8/§7), detección de recurrentes (4.11), tablero configurable (4.10), 240 meses con agregación.

Si apruebas el enfoque de capas del §4, el siguiente entregable es la **spec de la Capa 2 + hito + solvers (Capas 2–3)** — el mayor valor por sprint hacia tus cuatro preguntas — mientras F1.1 termina.
