# SOLICITUD DE AUDITORÍA — E1 PR6-I: frontend (marcas de origen + mes en curso) — ÚLTIMA pieza de E1

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** 2026-08-08
**Plan padre:** `docs/COMPAS_PLAN_E1_Anclaje_a_la_Ejecucion.md` (pieza **P6**, §6) · **Criterios:** honestidad **R5**, **B13** · **Brief:** etapa post-P5 (a–f) + **exigencia de capturas** (etapa62)
**Rama / PR:** `feat/e1-p6-frontend-marcas` · commit final del código a confirmar en el PR
**Spec/Plan:** `docs/superpowers/specs/2026-08-08-e1-p6-frontend-marcas-design.md` · `docs/superpowers/plans/2026-08-08-e1-p6-frontend-marcas.md`
**Diseño (mockup):** aprobado por el CEO (look "tal cual" + copys "claros"); tu gate de diseño **9.2 GO al spec**.

## Qué hace

P6 consume el shape de P5 y hace visible en **Proyecciones** el origen de cada cifra. Cierra E1. Todo **condicional al ciclo**: sin anclaje la vista queda idéntica a hoy (candado). **Las 3 capturas reales de la página implementada están embebidas en `EVIDENCIA.md` / este PDF** (con ejecución · mes sospechoso · sin ciclo).

### Alcance del brief (a–f), todo entregado

- **(a) Marcas de origen** — componente puro `MarcaOrigen.tsx` (Real · En curso · Presupuesto · Proyección · Revisar carga). Punto+etiqueta en la **1ª columna** de la tabla (NO columna nueva → sin scroll lateral) + **leyenda** encima. Es una dimensión **distinta** del `EstadoMes` (salud de caja ok/crítico/negativo) que ya existía; coexisten.
- **Gráfico** — `ComposicionCaja` (SVG a mano, sin librería nueva): la curva de caja va **sólida** en meses reales/en curso y **punteada** de la proyección; punto **ámbar** en el mes `cerrado_sospechoso`.
- **(b) Comparación del mes en curso** — callout `MesEnCursoCallout.tsx`: **Presupuesto del mes · Ejecutado (al día N) · Resta del presupuesto**. **DECISIÓN CEO: se amplió P6 al backend** para exponer los 2 datos que P5 no traía (`ejecutado` = Σ egresos reales del mes a la fecha; `proyectado` = Σ presupuesto definido) en `cargar_completitud_mes_en_curso` (sumas planas, sin mapeo/B12, TDD mongomock + real-mongo).
- **(c) Completitud B13** — "Cargado hasta el N de [mes]" + **la fórmula visible** en lenguaje de negocio (honestidad R5): "ejecutado + lo que resta del presupuesto".
- **(d) `sin_mapear`** — aviso al pie de la tabla, **solo si** hay rubros sin clasificar.
- **(e) Efecto-arrastre** — "Cuando cierres [mes], su ejecución real reemplaza esta estimación y arrastra el resto del año."
- **(f) Sin scroll lateral** — garantizado por (a).

## Punto de honestidad a revisar contigo (copy)

El brief pedía "**desviación**" como 3ª cifra del mes en curso. Al implementarlo vi que comparar el **ejecutado parcial** (al día N) contra el **presupuesto completo** del mes da una "desviación" **siempre negativa a mitad de mes** → engañosa. Cambié la etiqueta a **"Resta del presupuesto"** (= proyectado − ejecutado, lo que la Regla A añade para completar el mes), que es veraz y amarra con la fórmula. **¿De acuerdo, o prefieres otra formulación?**

## Semántica preservada (candados)

- **Candado sin ciclo:** sin `meses_anclados` → sin leyenda, sin callout, **sin marca bajo el mes** (fix dedicado + test) y **una sola línea de caja** → vista idéntica a hoy. Ver captura 3.
- **Marca de origen ≠ salud de caja** (dimensiones separadas, no se mezclan).
- **Aditivo:** los 3 campos del tipo `Proyeccion` son opcionales → los mocks/consumidores viejos no se rompen.
- **Dinero:** el front nunca hace `Number` sobre montos (decimal.js-light / `formatCOP*`).
- **Backend (ampliación P6-b):** `motor.py` cero diffs; solo se amplió el helper de P5 con 2 sumas; regresión backend **910 passed / 0 fallos**.

## Puntos a auditar con lupa

1. **Capturas vs implementación.** Las 3 PNG salen de un harness que monta los **componentes reales** con el `index.css` real (tokens cyan/semáforo, Raleway/Montserrat). ¿El visual honra el cockpit y el brief?
2. **Candado sin ciclo (captura 3):** ¿de verdad queda como hoy (sin marca, sin leyenda, sin callout, línea única)?
3. **Marca vs EstadoMes:** ¿bien separadas? La marca es origen; el badge de salud sigue en su columna.
4. **Gráfico:** ¿el corte sólido→punteado cae en el límite anclado/proyección y el punto ámbar marca el sospechoso?
5. **P6-b backend:** `ejecutado`/`proyectado` como sumas planas (sin B12) — ¿correcto y sin doble conteo? Honestidad de "Resta del presupuesto".

## Evidencia (ver `EVIDENCIA.md` / este PDF)

- **3 capturas reales** embebidas (con ejecución · sospechoso · sin ciclo).
- **vitest:** 248 passed (45 archivos) · **build** (tsc + vite) OK · **biome** limpio (132 archivos).
- **Backend:** regresión 910 passed / 95 skipped / 0 fallos; TDD del helper (mongomock + real-mongo); ruff limpio.
- Diff por pieza (tipos → MarcaOrigen → MesEnCursoCallout → tabla → gráfico → página → candado + backend P6-b).

## Cumplimiento de reglas

- R5 honestidad (fórmula + "resta" no engañosa). B13 (completitud + fórmula). Regla 1 (Decimal). R0 (motor.py 0 diffs). Catálogo sin crecer.
- Plan E1 §6-P6 (a–f): ✅. Exigencia de capturas (etapa62): ✅. TDD por pieza.
