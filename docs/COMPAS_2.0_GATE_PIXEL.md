# G-PIXEL · Gate visual contra el mockup vinculante (COMPAS 2.0)

> **Qué es:** un job de CI que renderiza la vista de **Proyecciones** en un
> navegador real (chrome-devtools-mcp o Playwright headless), toma screenshot
> y lo compara pixel a pixel con `docs/design-references/proyeccion-mockup.html`
> vía **lost-pixel**. Si el diff supera el umbral, el PR **NO se fusiona**.
>
> **Cuándo bloquea:** en TODO PR que toque las 2 gráficas principales
> (`frontend/src/components/charts/CurvaCajaRV2.tsx` y
> `frontend/src/components/charts/ComposicionFlujoRV2.tsx`) o el mockup.
> RV-V2 cerró 10/10 AC contra el mockup; G-PIXEL protege que un cambio
> futuro no desvíe la vista sin aprobación.

## 1 · Estado hoy (2026-08-31)

**Gate DECLARADO, no activo en CI todavía.** Cuando se active, bloqueará el
merge. El motivo del diferimiento: activarlo requiere **Playwright** en
`devDependencies` (~300 MB de browsers) o `chrome-devtools-mcp` con su propio
runtime — **una decisión de dependencias que exige GO explícito del CEO** y
que **G-TRIVY ya activo** verifique las CVEs antes de introducir el paquete.

Regla vigente: hasta que se active G-PIXEL, cualquier PR que toque
`CurvaCajaRV2.tsx` / `ComposicionFlujoRV2.tsx` requiere **revisión visual
manual del CEO contra el mockup** — mismo criterio que aplicó al mergear
las 3 rebanadas de RV-V2 (PRs #124/#131/#133).

## 2 · Activación (paso a paso, cuando el CEO lo autorice)

1. **G-TRIVY primero verde** con un PR chico que agregue `playwright` +
   `lost-pixel` como devDependencies del frontend. Si TRIVY encuentra
   HIGH/CRITICAL, se aborta y se elige otro paquete.
2. **Configurar lost-pixel** en `frontend/lostpixel.config.ts`:
   ```ts
   import type { CustomProjectConfig } from "lost-pixel";
   export const config: CustomProjectConfig = {
     pageShots: {
       pages: [
         {
           path: "/proyeccion?escenario=base&horizonte_meses=60&mes_inicio=2026-09",
           name: "proyeccion-base",
         },
       ],
       baseUrl: "http://localhost:5173",
     },
     imagePathBaseline: "docs/design-references/lost-pixel-baseline",
     threshold: 0.02, // 2 % de diff pixels
   };
   ```
3. **Baseline inicial**: tomar screenshot de referencia contra
   `docs/design-references/proyeccion-mockup.html` y guardar en
   `docs/design-references/lost-pixel-baseline/`.
4. **Workflow nuevo** `.github/workflows/pixel.yml` que:
   - Levanta el dev-server frontend con datos de fixture (mismos que
     `ProyeccionPage.test.tsx`).
   - Corre `npx lost-pixel` contra las 2 gráficas principales.
   - Falla el PR si el diff supera 2 %.
5. **Marcar `G-PIXEL` como required** en branch protection con `gh api`.

## 3 · Alternativa liviana (si Playwright no es viable)

Si el CEO decide no introducir Playwright, alternativas más ligeras:

- **`@vitest/browser` + Playwright browser mínimo** (~50 MB).
- **`puppeteer-core`** apuntando al Chrome del runner (~0 MB extra).
- **Snapshots de DOM en vez de píxeles** (test unit con `render()` + regex
  contra los `path d="..."` esperados de las series). No cubre estilo
  visual pero sí semántica del SVG.

**Recomendación** (Claude, pendiente de GO CEO): empezar con `puppeteer-core`
+ el Chrome del runner + `lost-pixel` — cero dependencias binarias nuevas,
usa el navegador que ya existe en Ubuntu Actions.

## 4 · Salida esperada

Cuando esté activo, cada PR que toque las gráficas produce:
- Screenshot capturado en `frontend/.lostpixel/current/`.
- Comparación contra el baseline en `docs/design-references/lost-pixel-baseline/`.
- Diff visual publicado como artifact del run.
- Verde si diff ≤ 2 %; rojo si supera.

## 5 · Referencias

- Mockup vinculante: `docs/design-references/proyeccion-mockup.html`.
- Componentes bajo el gate: `frontend/src/components/charts/CurvaCajaRV2.tsx`,
  `frontend/src/components/charts/ComposicionFlujoRV2.tsx`.
- Fundacional §5 · Arquitectura, seguridad y gates.
- Regla del método (Fundacional §3, RV-V2 AC #10): las gráficas se enlazan a
  los 23 campos reales de `/api/v1/proyeccion`, nunca a datos de ejemplo.
