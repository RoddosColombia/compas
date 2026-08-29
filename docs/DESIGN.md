# DESIGN.md — gramática de gráficos de COMPAS (RV-V1)

| | |
|---|---|
| **Método** | COMPAS 2.0, Fase 0 (crítico) · deliverable F0-3 / historia RV-V1 |
| **Fecha** | 2026-08-27 |
| **Estatus** | **vinculante** — prerrequisito de todo lo visual (RV-V2 en adelante). Un PR de gráficos que lo viole no se fusiona (gate `lost-pixel`/`axe`, Fundacional §5). |
| **Fuente de los tokens** | `frontend/src/index.css` (`@theme`) — **autoridad**. La paleta NO se inventa; se deriva de ahí. La referencia visual es `docs/design-references/proyeccion-mockup.html`. |

> El mockup usa una aproximación de color propia (slate + `#0C8FAC`…); **manda `index.css`**.
> Donde el mockup y `index.css` difieran en un hex, gana `index.css`.

---

## 1 · Las 8 reglas de la gramática

Derivadas de la Fundacional §3 (RV-V2, AC 1–10). Son la **gramática**; RV-V2 es su
aplicación a las dos gráficas principales.

1. **Real vs. proyectado se distinguen por FORMA, no por color.** Real = trazo **sólido**;
   proyección = **punteado**; el **ancla** (último cierre real) va marcada con su valor.
2. **El color es SOLO estado.** `positivo` (sano) · `atención` (ámbar) · `crítico` (rojo).
   Ninguna serie se distingue de otra por un color de estado; para eso están la forma, la
   posición y la etiqueta. El rojo jamás decora — está **reservado** a la perforación de caja.
3. **Los dos umbrales siempre dibujados.** Línea de **atención** (ámbar, administrable D-1)
   y línea de **crítico** (rojo, mínimo). El **valle** se sombrea como **zona** con su
   duración rotulada.
4. **Los números que importan van escritos en la gráfica**, no solo en el tooltip: el
   **último real** y el **fondo del valle** (mes + monto).
5. **Tooltip por punto** = caja de fin de mes **+ desglose de composición** de ese mes, con
   el estado (sobre umbral / atención / crítico) marcado por símbolo y color.
6. **Escenario superpuesto** = base + escenario dibujados juntos, con el **área entre ambos
   coloreada**; las motos del escenario son **editables antes** de activar; «vender de más»
   corre el goal-seek de unidades.
7. **La composición vive en su propia gráfica**, nunca comprimida en una franja: **ingreso
   neto arriba** de la línea cero, **egresos por concepto abajo**, y la **línea de flujo
   neto** encima. Un concepto = un color categórico (regla 9 abajo).
8. **Solo datos reales.** Las gráficas se enlazan a los **23 campos de `/api/v1/proyeccion`**,
   jamás a datos de ejemplo (el mockup los simula solo para diseñar). El **horizonte** es un
   selector (`3·6·9·12·15·18·30·42·54·60`), con etiquetas del eje **cada 2 meses** en la
   zona de proyección.

### Regla transversal (color)
> **Estado ≠ categoría.** Hay dos familias de color que NUNCA se mezclan:
> - **Semáforo de estado** (regla 2): `positivo` / `atención` / `crítico`. Comunican «cómo
>   estamos». Reservados.
> - **Categórica de composición** (regla 7): distingue conceptos de egreso entre sí. Debe
>   ser **visualmente disjunta** del semáforo (ni verde, ni ámbar, ni rojo de estado).

---

## 2 · Paleta como tokens (derivada de `index.css`)

### 2.1 Marca (acción y positivo)
| Token | Hex | Uso |
|-------|-----|-----|
| `--color-cyan` | `#0fa9b8` | acción primaria + navegación activa (Cyber Cyan) |
| `--color-cyan-soft` | `#76e5ec` | acentos/hover |
| `--color-cyan-tint` | `#ecfbfc` | fondo tenue del ítem activo |
| `--color-green` | `#12a312` | positivo/éxito (Growth Green) |

### 2.2 Estado (semáforo AA sobre blanco) — **reservado, regla 2**
| Token | Hex | Contraste | Significado (con símbolo) |
|-------|-----|-----------|---------------------------|
| `--color-positivo` | `#15803d` | 4,5:1 | dentro de meta (▲ / ✓) |
| `--color-atencion` | `#b45309` | 4,5:1 | cerca del límite / umbral de atención (● / !) |
| `--color-critico` | `#b91c1c` | 5,9:1 | fuera de rango / perforación (▼ / ✗) |

`--color-red #e0524d` y `--color-amber #e8a83a` son el semáforo histórico; en gráficos nuevos
se usan los **semánticos AA** de arriba.

### 2.3 Gama de rojos para costo/gasto (barras, NO estado)
| Token | Hex | Uso |
|-------|-----|-----|
| `--color-costo` | `#d1483f` | rojo pleno del **costo** |
| `--color-gasto` | `#ef938c` | mismo tono, más claro, del **gasto** |

> Distintos del `crítico` (que queda para alertas). Nunca se usan como estado.

### 2.4 Neutrales sobre blanco
| Token | Hex | Contraste | Uso |
|-------|-----|-----------|-----|
| `--color-ink` | `#0f172a` | 15,9:1 | texto principal / **la serie real** |
| `--color-ink-soft` | `#475569` | 7,5:1 | texto secundario |
| `--color-ink-faint` | `#64748b` | 4,8:1 | metadatos, ejes (**mínimo para texto**) |
| `--color-ink-decor` | `#94a3b8` | 2,8:1 | SOLO decorativo (grilla, separadores) — jamás texto |
| `--color-surface` | `#ffffff` | — | fondo (tema claro, decisión CEO) |
| `--color-hairline` | `#e2e8f0` | — | bordes 1px / líneas de grilla |

### 2.5 Tipografía
- **Montserrat** (`--font-display`): titulares y **cifras** (tabular-nums). Ejes de valor y
  etiquetas de mes en las gráficas usan cifras Montserrat/mono, alineadas.
- **Raleway** (`--font-sans`): cuerpo y UI.
- Escala por rol: `--text-cifra-lg 2rem` (LA cifra, 1 por pantalla) · `--text-cifra 1.5rem`
  (KPI) · `--text-titulo 1.375rem` · `--text-seccion 1rem` · `--text-cuerpo .875rem` ·
  `--text-apoyo .78125rem` (**12,5px = mínimo**; ejes y leyendas **no bajan de aquí**).

---

## 3 · Tokens de rol para gráficos (a agregar en `@theme`)

`index.css` tiene marca y estado, pero **aún no** los roles que las gráficas necesitan. RV-V1
los **define** aquí (derivados de los de arriba) para que RV-V2 tenga contrato de tokens.
Se materializan en `index.css` cuando se construya RV-V2 (y se afinan con **tweakcn**, RV-V3).

### 3.1 Series de la curva de caja (por forma; el color solo refuerza)
| Rol | Deriva de | Trazo |
|-----|-----------|-------|
| `--chart-real` | `--color-ink` `#0f172a` | sólido, con puntos + ancla |
| `--chart-proyectado` | `--color-cyan` `#0fa9b8` | punteado |
| `--chart-escenario` | `--color-positivo` `#15803d` | punteado + área |

### 3.2 Composición del flujo (categórica, **disjunta del semáforo** — regla 9)
| Rol | Deriva de | Nota |
|-----|-----------|------|
| `--chart-ingreso` | `--color-positivo` `#15803d` | única categoría que sí toca el verde: es ingreso neto, arriba del cero |
| `--chart-gasto-fijo` | familia azul (nuevo, provisional) | egreso — azul, fuera del semáforo |
| `--chart-auteco` | familia magenta (nuevo, provisional) | inventario Auteco — el que dispara el valle |
| `--chart-otros` | familia teal (nuevo, provisional) | otros egresos |

> **Provisional:** los tres colores categóricos de egreso (azul/magenta/teal) **no** existen
> aún en `index.css`. Se fijan en **RV-V3 (tweakcn)** con verificación de contraste AA y de
> daltonismo, garantizando que **ninguno colisione** con `positivo/atención/crítico`. Hasta
> entonces, RV-V2 los toma de este contrato como variables, nunca hardcodeados.

---

## 4 · Anti-reglas (tan vinculantes como las reglas)
- **Nada de color decorativo.** Si un color no comunica estado (semáforo) ni categoría de
  composición, no va.
- **El rojo de estado (`crítico`) no se reutiliza** para costo/gasto ni para categorías: es
  solo perforación/alerta.
- **Ninguna serie se distingue por color de estado** (regla 2): la diferencia real/proyección
  es forma; base/escenario es forma + área.
- **Ejes y leyendas nunca bajan de 12,5px** (`--text-apoyo`) ni usan `--color-ink-decor` como
  texto.
- **Cero datos de ejemplo** en producción (regla 8): si un campo de `/api/v1/proyeccion` no
  llega, se muestra el vacío honesto, no un número inventado.
