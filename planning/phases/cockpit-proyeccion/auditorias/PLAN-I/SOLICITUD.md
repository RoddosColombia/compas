# SOLICITUD DE AUDITORÍA / PLAN — cockpit-proyeccion · COCK-01: motor de proyección C7

**Para:** CEO (GO de fase) + Kimi (auditoría diferida) · **Fecha:** 2026-07-23
**Docs contrato:** `docs/modelo/ARQUITECTURA_PRESUPUESTAL.md` (§2 motor de ingresos,
§3 flujo/runway/escenarios, §5 economía unitaria), `docs/modelo/PROYECCIONES.md`
(SIMULADOR 2030 destilado), `docs/Compas_Blueprint_UX.docx` (§5 Proyecciones =
corazón), `COMPAS_NORTE.md`; CLAUDE.md reglas 1, 2, 3, 4, 9, 11.
**Base:** `main` con la fundación construida — C1 (plan de cuentas de 6 grupos con
código + Fijo/Variable), C4, C5, C9 en prod.
**Nivel:** PLAN (pre-código). **Alcance:** COCK-01 = **motor de proyección BACKEND**:
escenarios + ingreso por 2 vías + flujo de caja/runway + horizonte configurable a 15
años, replicando las **fórmulas** del SIMULADOR (no sus datos). La vista Proyecciones
frontend (COCK-03) va en fase aparte.

> Norte: es EL valor de COMPAS — proyectar el disponible acumulado mes a mes, marcar
> la **caja mínima requerida** (umbral del norte) y el **mes más ajustado**, con
> recaudo **discriminado** (cuota inicial vs crédito), bajo escenarios
> Base/Optimista/Conservador y a horizonte largo (hasta 180 meses). Reemplaza el
> SIMULADOR 2030 y le da estructura desde la realidad, más allá de dic-2030.

## Principios (fijados por el CEO)
- **Fórmulas, no datos.** Se replica la macro/función del Simulador (semanas exactas,
  recaudo cuota-a-cuota, flujo de caja), NUNCA sus cifras. Toda cifra se carga después
  en la app; el armazón no necesita datos para construirse ni testearse.
- **Fuente canónica = `docs/modelo/Dashboard Artefacto.jsx`** (2.544 líneas): la
  formulación LIMPIA y CORREGIDA del simulador (sus comentarios documentan el fix del
  saldo rodante Auteco que daba caja negativa espuria). Se replican sus funciones
  `simular()` y `calcularCredito()` a Python. **Test de paridad golden-master:** el
  motor Python debe reproducir las salidas del artefacto con sus parámetros por
  defecto (config de 2 modelos Raider/Apache) — eso ES el "calcar celda a celda", sin
  cargar data de negocio. Los movimientos Global ene-jul son para Fase 2 (actuals).
- **CAJA VERAZ (decisión CEO 2026-07-23):** el flujo de caja refleja EFECTIVO real.
  `neto = bruto + mora + recuperación + default`. La **provisión NIIF 9 NO resta caja**
  (es asiento contable) — va solo a las métricas de P&G / economía unitaria (§5).
  Corrige el artefacto/Excel, que la restaba del flujo (FC filas 17-20) subestimando la
  caja y solapando la pérdida esperada.
- **Mora y default MENSUALES editables (decisión CEO):** cada mes arranca del valor
  "real" como aviso inicial (default = % plano del escenario) y se puede ajustar mes a
  mes (curva de mora/default opcional) para organizar la proyección. Extiende el
  mecanismo `overridesMes` del artefacto.
- **Administrable (regla 9).** Modelos de moto y parámetros se dan de alta/editan desde
  la app y crecen con RODDOS; nada hardcodeado. Baja lógica (nada se borra).
- **Horizonte configurable hasta 15 años.** El Excel llega a dic-2030 (~60 meses);
  COMPAS lo extiende hasta 180 meses — infraestructura con más capacidad que el Excel.

## Qué se construye (unidades, cada una con TDD)

**Unidad A — `ModeloMoto`** (Document administrable, paralelo de C1):
`nombre · costo_auteco · precio_venta_con_iva · cuota_inicial · cuota_semanal ·
plazo_semanas · matricula · participacion_mix (%) · activo · es_sistema`. CRUD
`/api/v1/modelos-moto` (`proyeccion:gestionar`). Baja lógica (un modelo con proyección
no se borra). Único (nombre). Saga O1 fail-closed idéntica a `rubros/service.py`.
Hoy: Raider, Sport, Apache — pero se agregan modelos nuevos sin tocar código.

**Unidad B — `ParametrosProyeccion`** (drivers editables, réplica de PARAMETROS,
versionado por `vigente_desde` como `Configuracion`): caja inicial, **caja mínima
requerida (el umbral)**, gastos fijos/mes, colocación (motos/mes), plazo pago
inventario Auteco (150 días → desfase de caja), costos operativos (GPS/moto activa,
costo por moto nueva), TRM, y los **multiplicadores por escenario** (colocación y %
recuperación de cartera para Base/Optimista/Conservador). Todo `Money` (Decimal).
Endpoint de lectura/actualización con `proyeccion:gestionar`; captura MANUAL (Fase 1).

**Unidad C — el motor `proyectar()`** (función PURA, sin I/O — el núcleo, estilo
`presupuesto/motor.py`, auditable celda-a-celda). Dado {catálogo de modelos activos,
parámetros, escenario, mes_inicio, horizonte_meses}, proyecta mes a mes:
- **Semanas exactas de cobro del mes:** `INT((fin_mes − primer_día_cobro)/7) + 1`
  (p. ej. jul-2026 = 5 miércoles). Es el driver del recaudo, no "4 semanas fijas".
- **Ingreso por 2 vías (discriminado, SIEMPRE separado):**
  - *Vía 1 — Recaudo de crédito (0110):* motor **cuota-a-cuota** — cada venta abre una
    ventana de `plazo_semanas`; el recaudo del mes = Σ cuotas semanales activas de
    todas las ventas vivas × semanas de cobro del mes, por modelo, ajustado por el
    **% recuperación** del escenario (mora).
  - *Vía 2 — Cuotas iniciales (0120):* `Σ_modelo (colocación_modelo × cuota_inicial)`.
  - `ingreso_bruto = Vía 1 + Vía 2`.
- **Egresos:** compra inventario Auteco (colocación × costo_auteco, **desfasada 150
  días** — anti-doble-conteo, entra UNA vez), gastos fijos, costos operativos
  (GPS × motos activas), servicio de deuda (placeholder Fase 1; el cronograma real es
  C10). Costos de motos nuevas (SOAT/matrícula) por colocación.
- **Flujo/runway:** `caja_final[m] = caja_final[m-1] + ingreso_bruto − egresos`,
  arrancando en caja inicial; `runway = caja_final ÷ burn_neto_promedio`.
- **Escenario:** selector `Base/Optimista/Conservador` que aplica los multiplicadores
  de la Unidad B sobre colocación y % recuperación (mecánica INDEX del Excel).
- **Salida:** serie mensual (todo Decimal→string, regla 1) + KPIs: **piso de caja**,
  **mes más ajustado**, disponible al final del horizonte, **meses bajo el mínimo**,
  runway, y por mes el estado OK/Alerta (caja_final vs caja mínima). Hitos de resumen
  a 12/24/36/48/60/120/180 meses.

**Unidad D — endpoint `GET /api/v1/proyeccion`** (compute-only, sin estado,
`dashboard:leer`). Query: `escenario` (default `base`), `horizonte_meses` (default 60,
**máx 180**), `mes_inicio` (default mes vigente). Orquesta: carga modelos activos +
parámetros vigentes → llama al motor puro → serializa.

**Unidad E — CR-COCK (declarar antes de construir):**
- Eventos nuevos (catálogo cerrado, hoy 40 → 44): `modelo_moto.creado`,
  `modelo_moto.editado`, `modelo_moto.desactivado`, `parametros_proyeccion.actualizado`.
- Capacidad nueva `proyeccion:gestionar` = {financiero, admin} (gestiona modelos y
  parámetros). La proyección en sí es `dashboard:leer` (todos los roles la ven).

## Decisiones (RESUELTAS con el CEO 2026-07-23)
- **D1 — Escenarios en el motor: SÍ.** El motor acepta `escenario` de primera clase;
  los presets (Pesimista/Base/Optimista del artefacto: mora 6/3/1.5%, recuperación
  30/40/60%) modulan mora/recuperación vía `ParametrosProyeccion`. Comparación visual
  de los 3 → frontend (COCK-03).
- **D2 — Construir la lógica YA, sin cargar data.** Cifras canónicas viven en el
  Simulador (sensible); Fase 1 las captura el CEO en la app. Tests con valores del
  artefacto (golden-master) para probar la lógica. **Confirmado por el CEO:** no se
  requiere subir data para calcar las fórmulas.
- **D3 — Servicio de deuda / renta.** Cronograma acreedor×mes = C10; IVA = C11 (fases
  aparte). En COCK-01 el servicio de deuda entra como egreso paramétrico (int. deuda,
  como el artefacto fila 26); renta fuera de Fase 1.
- **D4 — Horizonte.** Default 60 meses (paridad Excel), tope 180 (15 años).
- **D5 — Caja veraz (CEO):** provisión NIIF 9 fuera del flujo; mora+default en el
  flujo pero editables mes a mes con default al % del escenario. Ver Principios.

## Semántica / reglas innegociables
Decimal end-to-end (string en API, regla 1). América/Bogotá, meses al día 1 (regla 2).
Pydantic `strict=True, extra="forbid"` (regla 3). Motor **compute-only**: no escribe
transacciones ni toca el histórico (regla 4 en espíritu). Modelos/parámetros
administrables desde capacidades (regla 9). Eventos solo del catálogo + CR-COCK
(regla 11). Saga O1 fail-closed en las mutaciones (compensar si falla el emit).

## Orden de construcción (TDD, red→green)
1. **Unidad C primero** (motor puro): sin Mongo → red-green rápido, es el corazón y lo
   que "replica las fórmulas". Tests celda-a-celda de semanas exactas, recaudo
   cuota-a-cuota, discriminación 2 vías, flujo/runway, KPIs, escenarios.
2. Unidad A + B (entidades + CRUD, mongomock; transacción/índices con real-mongo).
3. Unidad D (endpoint) + CR-COCK (eventos + permiso).
4. Tracker + demo con cifras del CEO.

## Pregunta al CEO
¿GO para construir COCK-01 así — motor puro (2 vías + semanas exactas + flujo/runway +
escenarios + horizonte a 180 meses) + `ModeloMoto` y `ParametrosProyeccion`
administrables + `GET /proyeccion` — con TDD y las decisiones D1–D4 como las propongo?
Si prefieres subir el SIMULADOR 2030 para calcar alguna fórmula celda-a-celda antes,
lo espero; si no, construyo la lógica del contrato y tú cargas tus cifras.
