# AND-4 · Herramientas · Browser MCP + tweakcn (declaración de uso)

> **Qué es:** el inventario de herramientas externas que el método usa en COMPAS
> 2.0, con su contrato de uso, dónde aparecen y qué NO se les pide. La regla:
> nada corre sobre este repo sin figurar acá y en el log de AND-1 §5.

## 1 · Browser MCP (`mcp__Claude_Browser__*`)

**Qué es:** el navegador de Claude, integrado como MCP oficial de Anthropic. Le
da a Claude un DOM real (no un screenshot ciego) — puede navegar, leer la
página como árbol de accesibilidad, hacer clic, tipear, ejecutar JS, y leer
la consola/red.

**Herramientas que expone:**

- `navigate`, `read_page`, `get_page_text`, `find`
- `computer` (click, type, key, scroll, screenshot)
- `form_input`, `javascript_tool`
- `read_console_messages`, `read_network_requests`
- `resize_window`, `tabs_*`
- `preview_start`, `preview_stop`, `preview_logs` (para dev servers locales)

**En qué casos lo usamos:**

- **RV (rebanadas visuales)**: cuando el CEO pide comparar contra el mockup del
  Blueprint, Claude abre el frontend en el Browser MCP, hace `read_page`,
  toma screenshots y valida contraste con la referencia. Es lo que reemplaza
  al «yo lo miro y te digo si está bien».
- **G-PIXEL (cuando se active)**: el candidato ligero para el gate es un test
  local que arranca Vite con `preview_start` y compara pixel-diff contra
  baselines commiteadas.
- **Debug de bugs UI que el CEO reporta**: Claude reproduce en el Browser MCP
  y lee la consola en vez de adivinar la causa.

**Qué NO le pedimos al Browser MCP:**

- **Nunca** entrar credenciales, aceptar términos, ni pagar en su nombre
  (regla del boundary de instrucción — decisión del CEO en cada acción sensible).
- **Nunca** navegar a sitios que no sean del dominio del proyecto
  (`compas.roddos.com`, `roddoscolombia.github.io`, `claude.ai/code/artifact`,
  `github.com/RoddosColombia`). Si Claude necesita otro dominio, lo pide.
- **Nunca** ejecutar acciones destructivas en el frontend real de PROD (borrar
  registros, cerrar meses); esas van por la app con el usuario del CEO logueado
  manualmente.

**Dominios permitidos por default (patrón para el MCP):**

```
compas.roddos.com
roddoscolombia.github.io
claude.ai
github.com/RoddosColombia/*
localhost:5173  (Vite dev)
localhost:8000  (FastAPI dev)
```

## 2 · tweakcn (herramienta de tokens de diseño)

**Qué es:** editor visual de tokens shadcn/ui + Tailwind — `https://tweakcn.com`.
Permite generar el `theme.css` de shadcn con un pipetazo de color y exportarlo
listo para pegar en el frontend.

**Cuándo se usa:**

- **RV-V3/V4/V5** (los «should» del bucket visual): antes de tocar el tema del
  frontend, Claude genera la paleta en tweakcn y compara con la referencia del
  Blueprint (verde/turquesa RODDOS). Solo entonces edita `frontend/src/index.
  css` con los tokens exportados.
- **RV-V10** (control de theme): el mismo `theme.css` sirve como fuente única
  para el toggle claro/oscuro.

**Qué NO se hace con tweakcn:**

- **No** subir capturas del frontend real a tweakcn (no exportar data sensible
  a un servicio de terceros).
- **No** confiar en su preview como validación final — el gate real es
  `npm run build` + revisión manual en el Browser MCP.

## 3 · Chrome DevTools MCP (referencia)

**Qué es:** el MCP más pesado para automatización del navegador de escritorio.
Distinto del Browser MCP integrado: este exige Chrome del OS abierto y con la
sesión del CEO ya loggeada.

**Estado en COMPAS 2.0:** **NO instalado**. El Browser MCP integrado cubre lo
que necesitamos hoy (rebanadas visuales, debug UI, G-PIXEL cuando corresponda).
Chrome DevTools MCP entraría al log de AND-1 solo si en el futuro necesitamos
manipular una sesión real del CEO en `compas.roddos.com` — y ese caso pasa
primero por el checklist §3 de AND-1.

## 4 · Ausentes deliberados

- **Playwright / Puppeteer sin control**: no se instalan como dependencia del
  repo por su tamaño (~300MB) y por la seguridad de la CI. Para G-PIXEL
  usamos `puppeteer-core` apuntando a un Chromium ya existente en el runner,
  o el propio Browser MCP en local.
- **Selenium**: fuera; no aporta sobre lo que ya tenemos.

## 5 · Reglas cruzadas

- Toda herramienta declarada acá **debe** figurar en la tabla de AND-1 §5 (log
  de skills/plugins instalados). Si aparece una que no está en ambos lugares,
  Claude reporta la discrepancia.
- Cualquier nueva herramienta pasa antes por el checklist SkillSpector (AND-1
  §3). Este documento se actualiza en el mismo PR de instalación.
