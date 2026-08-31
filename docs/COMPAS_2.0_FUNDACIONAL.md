# COMPAS 2.0 — Documento base fundacional

| | |
|---|---|
| **Código** | COMPAS-2.0-FND |
| **Versión** | 0.1 · borrador |
| **Fecha** | 2026-08-27 |
| **Modo del método** | crítico (maneja la caja de RODDOS) |
| **Responsable** | Andrés — CEO |
| **Aprueba** | negocio (no técnico) |
| **Referencias** | `docs/NORTE.md`, `docs/ROADMAP.md`, cuaderno técnico (5 cap.), hoja de ruta Paso 1, mockup RV-V2 |

**Histórico**
- 0.1 (2026-08-27): versión inicial. Deriva de la hoja de ruta y de la revisión del código real. Decisiones D-1 y D-2 fijadas por el CEO. Pendiente de revisión independiente (Fase 0) y aprobación.

> **📊 Velocímetro (fuente única):** `docs/COMPAS_2.0_ROADMAP.md`. Este documento describe el ALCANCE; el ROADMAP muestra la EVOLUCIÓN a peso contra `origin/main`. Ante conflicto sobre "cómo vamos", manda el ROADMAP.
>
> Instancia condensada del «Método de trabajo con IA» (11 fases), en modo crítico. Referencia —no repite— las fases ya cerradas. Ante duda de alcance manda `NORTE.md`; ante conflicto de este documento con el código verificado, manda el código.

---

## 0 · Norte 2.0

**Qué ES:** sistema predictivo para administrar el presupuesto mensual de RODDOS y proyectar la caja, con el fin de tomar decisiones presupuestales.
**Qué NO ES:** un sistema contable. El ciclo presupuestal es el cimiento que captura la ejecución real, no el objetivo.

**Objetivo 2.0 (cambio de fecha a regla):** ningún mes del horizonte debe caer bajo los umbrales de caja que el CEO define. Cuando la proyección anticipe un valle, la app lo advierte con anticipación y presenta las palancas para evitarlo. Reemplaza el hito fijo «mayo 2027».

**Regla de priorización (sin cambio):** al priorizar, gana siempre lo que acerque a proyectar caja y decidir, no lo que solo registre el pasado.

---

## 1 · Decisiones fijadas por el CEO

**D-1 · La línea de atención es administrable.** No se deriva del histórico ni queda fija en código: es un campo que el CEO define dentro de la app. Compas 2.0 maneja **dos umbrales configurables**:
- `crítico` — mínimo de caja (ya editable, $30 M). Perforarlo = estado rojo.
- `atención` — nivel superior de vigilancia, nuevo y editable. Cruzarlo = ámbar y dispara la lógica de valles.

El mínimo histórico observado desde abril 2026 se ofrece como *sugerencia* al configurar; el valor lo fija el CEO. Ambos umbrales se versionan con fecha y autor.

**D-2 · Autoridad de motor por tramo.** Cuando el presupuesto aprobado y el motor paramétrico difieran para un rubro:
- **≤ mes en ejecución** → manda el **presupuesto aprobado** (decisión firme del mes en curso).
- **> mes en ejecución** → manda el **motor paramétrico** (mejor proyección hacia adelante).

El cierre de cada mes desplaza la frontera un mes hacia adelante.

---

## 2 · Alcance — funcional (historias)

MoSCoW. Detalle completo en la hoja de ruta Paso 1.

**Velocímetro (2026-08-30, con base en `origin/main`):** funcional **10/10** cerrado en main (must 5/5 · should 3/3 · could 2/2). Todos los RF-F* mergeados.

### Imprescindibles (must)
- **RF-F1 · Reglas sembradas con patrones reales.** Semilla desde *Base real egresos*; cola de «Por clasificar» vaciada con reglas aprendidas. **✅ hecho**
  *AC:* Dado un extracto cargado, cuando corren las reglas, ≥ 90 % de los movimientos entran clasificados y «Por clasificar» deja de ser el mayor rubro del mes; cada movimiento queda sellado con `clasificada_por/at` + `regla_id`.
- **RF-F2 · Costura presupuesto → proyección.** `Ajuste.rubro_id` entra en el cálculo; aprobar el mes genera los ajustes según D-2 y produce una serie versionada. **✅ hecho**
  *AC:* Dado un mes con presupuesto aprobado, cuando se aprueba, la proyección muestra serie nueva, anterior y diferencia en piso y valles, sin recálculo manual. **Golden-master del motor intacto.**
- **RF-F3 · Objetivo como regla de valles.** Umbral de atención administrable (D-1); valle como entidad (entrada, fondo, salida, profundidad, duración); dos clases de alerta (nivel; y valle nuevo/más profundo vs. versión aprobada). Reusa `valles.py`. **✅ hecho**
- **RF-F4 · Techo de gasto en ventana.** `techo_gasto_ventana(mes_inicio, ventana_meses=9, referencia)`: bandera roja si el valle **dentro de la ventana** perfora la **atención** (no el mínimo), aunque el horizonte cierre bien. Parametriza `techo_gasto`. **✅ hecho**
- **RF-F5 · Solvers dentro de la app.** Techo, objetivo de venta (`goal_seek`) y unidades (`solver_unidades`) expuestos en la cabina del mes y en proyección; cada alerta de valle llega con sus tres palancas. **✅ hecho**

### Debería (should)
- **RF-F6 · Cargas idempotentes por huella** — antes de que entre Bancolombia en septiembre. **✅ hecho**
- **RF-F7 · Recomendaciones por impacto** — reparto del recorte por rubro; motor corrido al revés. **✅ hecho (PR #119, main 62d24d5)**
- **RF-F9 · Plan de cuentas completo** — código contable y clase obligatorios al crear categoría. **✅ hecho (PR #121, main 7aebfba)**

### Podría (could)
- **RF-F8 · Obligaciones factura a factura** — generaliza Auteco; habilita fecha exacta de pago y «negocia esta deuda». Esfuerzo alto. **✅ rebanada A hecha (PR #120, main a24466b · simulación compute-only)** — la persistida queda para CR-RF-F8-B (requiere evento audit nuevo).
- **RF-F10 · Horizonte a 240 meses con agregación** por año/trimestre. **✅ hecho (PR #122, main ab05af7)**

---

## 3 · Alcance — visual y operativo

**Velocímetro visual (2026-08-30, con base en `origin/main`):** RV-V1 ✅ mergeado. RV-V2 en curso — rebanada 1 (7 de 10 AC) ✅ mergeada en main; rebanadas 2 (AC #8) y 3 (AC #5/#7) por venir. RV-V3..V10 y los 6 gates siguen.

### Imprescindibles (must)
- **RV-V1 · DESIGN.md con la gramática de gráficos** (8 reglas) + paleta de marca como tokens. Prerrequisito de todo lo visual. **✅ hecho (PR #123, main a071d46)** — los 7 tokens de rol de gráfico (`--color-chart-*`) materializados en `frontend/src/index.css`; contrato listo para RV-V2.
- **RV-V2 · Rehacer las dos gráficas principales.** Referencia visual vinculante: `docs/design-references/proyeccion-mockup.html`. **🔄 en curso** — rebanada 1 (curva de caja, 7 de 10 AC) ✅ mergeada en main (PR #124, main 031b1ad). Rebanada 2 (AC #8 composición separada) en branch `feat/rv-v2-composicion` (WIP). Rebanada 3 (AC #5 escenario superpuesto + AC #7 motos editable) pendiente.
  *AC (verificable contra el mockup):*
  1. Real en trazo sólido, proyectado punteado, con el ancla marcada.
  2. Valle sombreado como zona con su duración; dos umbrales dibujados (atención ámbar, crítico rojo).
  3. Números en la gráfica: último real, fondo del valle.
  4. Tooltip por mes con caja + desglose de composición.
  5. Escenario superpuesto: base + escenario, área entre ambos coloreada.
  6. Selector de horizonte 3·6·9·12·15·18·30·42·54·60; etiquetas cada 2 meses en proyección.
  7. Motos del escenario editable **antes** de activar; «vender de más» calcula el mínimo (goal-seek de unidades).
  8. Composición del flujo en **gráfica propia** (no franja): ingreso arriba, egresos por concepto abajo, línea de flujo neto.
  9. Color = solo estado (verde sano / ámbar atención / rojo crítico). Series por forma y valor, nunca por color de estado.
  10. Las gráficas se enlazan a los 23 campos reales de `/api/v1/proyeccion`, **nunca a datos de ejemplo** — el mockup los simula solo para diseño.

### Debería (should)
- **RV-V6/V7 · Fase B del navegador con contadores de estado** — 18→11 entradas, el mes como objeto con pestañas; plano reconciliado con las 12 rutas reales.
- **RV-V8/V9 · Confianza del dato en la franja** y **bandeja «Por clasificar» con crear-regla.**
- **RV-V3/V4/V5/V10 · tokens de marca (tweakcn), escenarios superpuestos, sparklines, acabados** (encabezado de tabla fijo, cinco estados).

### Máquina de estados que cambia
La **proyección se vuelve versionada**: cada aprobación de mes produce una versión inmutable de la serie; la anterior no se sobrescribe (histórico sagrado). Las alertas de valle comparan contra la última versión aprobada. Ningún otro objeto cambia su ciclo de vida.

---

## 4 · Anti-principios (tan vinculantes como un requerimiento)

- **No motor de fórmulas genérico.** La verificabilidad del motor existe porque el modelo está fijo en código. Se difiere indefinidamente.
- **No tocar el motor golden-master.** Toda mejora es capa de impactos, solvers o presentación sobre `proyectar()`. Ningún cambio a la paridad de 176 meses sin gate explícito.
- **No clonar Rindegastos.** Compas resuelve la caja, no la rendición de gastos de empleados. El módulo de rendición solo existe si el negocio decide cambiar el proceso.
- **No reglas de negocio en variables de entorno.** Umbrales, políticas y parámetros van en configuración editable y auditada; las variables de entorno solo guardan secretos y cadenas de conexión.
- **No sobrescribir histórico.** Meses cerrados, versiones aprobadas y originales de extracto quedan inmutables.

---

## 5 · Arquitectura, seguridad y gates

**Lo que 2.0 añade:** capa de impactos que consume `Ajuste.rubro_id`; umbral de atención como entidad administrable; valle como entidad derivada de la serie; proyección versionada; (si entra RF-F8) obligaciones factura a factura generalizando Auteco. El motor, la API `/api/v1` y el modelo de datos existentes no se rediseñan.

**Gates de modo crítico (no ceden por cronograma — se mueve la fecha, no el control):**
- Gate de seguridad **bloqueante** antes de liberar; segunda revisión de seguridad externa al equipo.
- **Golden-master del motor en CI** — verde obligatorio en todo PR que toque proyección.
- **Semgrep** con las reglas inviolables (Decimal, histórico inmutable, ninguna ruta sin auth) fallando el PR.
- **Trivy** cierra el hueco de npm — obligatorio antes de introducir cualquier librería de gráficos.
- **chrome-devtools-mcp + lost-pixel** contra `proyeccion-mockup.html` — un PR que desvíe RV-V2 del mockup no se fusiona.
- **axe-core** en las vistas de proyección.

---

## 6 · Andamio y su orden (prerrequisito, no alcance del producto)

1. **SkillSpector / AgentShield primero** — nada se instala sin escanear.
2. **ECC por proyecto, perfil core, hooks apagados,** solo reglas de Python, tag fijado. Dependencia, no proveedor.
3. **Punto 1:** `spec-miner` (mapea el código → registro de capacidades), `tdd-guide` (protege el golden-master), Semgrep, skills propias de RODDOS.
4. **Punto 2:** `DESIGN.md` (gramática), `chrome-devtools-mcp` (ojos), `tweakcn` (tokens), `lost-pixel`/`axe` (protegen gráficas), Trivy (antes de la librería de gráficos).

---

## 7 · Criterios de salida y riesgos

**«Listo» cuando:** las historias imprescindibles (RF-F1..F5, RV-V1, RV-V2) cumplen su AC con evidencia; el golden-master sigue verde; el gate de seguridad está cerrado; el registro de capacidades derivado del código está publicado (cierra el riesgo no técnico); y el CEO valida en demo con datos reales.

| Riesgo | Mitigación |
|---|---|
| Un cambio rompe la paridad del motor sin notarse | `tdd-guide` + golden-master en CI antes de cualquier toque |
| El plan se despega del código (riesgo no técnico) | Registro de capacidades generado por script + detector de deriva en CI; el plan es vista, no fuente |
| Septiembre: Bancolombia junto a Global66 duplica historia | RF-F6 (huella) cerrada antes del cambio de banco |
| Una librería de gráficos abre el árbol de npm sin escanear | Trivy bloqueante en CI antes de introducirla |
| Bus factor 1 sobre el motor | Par revisor designado; módulos críticos documentados; skills versionadas |
