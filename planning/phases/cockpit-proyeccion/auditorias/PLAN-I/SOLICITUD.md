# SOLICITUD DE AUDITORÍA / PLAN — cockpit-proyeccion · COCK-01: motor de proyección C7 (Fase 1)

**Para:** CEO (GO de fase) + Kimi (auditoría diferida) · **Fecha:** 2026-07-23
**Docs contrato:** `docs/Compas_Blueprint_UX.docx` (§5 módulo de proyecciones),
`docs/modelo/PROYECCIONES.md` (motor destilado del SIMULADOR 2030), `COMPAS_NORTE.md`;
CLAUDE.md reglas 1, 2, 3, 4, 9, 11. **Base:** `main` con C1–C5, C9 en prod.
**Nivel:** PLAN (pre-código). **Alcance:** COCK-01 = **motor de proyección BACKEND
Fase 1** (+ modelos de moto administrables, COCK-02). La vista Proyecciones frontend
(COCK-03) y escenarios (COCK-04) van en fases aparte.

> Norte: es EL valor de COMPAS — proyectar el disponible acumulado mes a mes hasta
> dic-2030, marcar la **caja mínima** y el **mes más ajustado**, con recaudo
> **discriminado** (cuota inicial vs crédito). Reemplaza el SIMULADOR 2030.

## Qué se propone (Fase 1: captura manual, sin históricos — Blueprint §1)

**1. `ModeloMoto`** (entidad administrable, paralelo de C1 — requisito CEO):
`nombre · costo_auteco · precio_venta_con_iva · cuota_inicial · cuota_semanal ·
plazo_semanas · matricula · participacion_mix (%) · activo`. CRUD
`/modelos-moto` (`proyeccion:gestionar`, CR-COCK). Baja lógica (un modelo con
proyección no se borra). Hoy: Sport, Raider (Apache en la variante).

**2. `ParametrosProyeccion`** (drivers editables, réplica de PARAMETROS): caja
inicial, caja mínima requerida (el umbral), gastos fijos/mes, colocación
(motos/mes), plazo pago inventario Auteco, costos operativos (GPS/moto, costo moto
nueva), TRM. Captura MANUAL (Blueprint: "Datos → caja inicial + supuestos a mano").
Versionado por `vigente_desde` (como Configuracion).

**3. Motor `proyectar()`** (compute-only, el núcleo): dado el catálogo de modelos +
los parámetros, proyecta mes a mes **jul-2026 → dic-2030**:
- **Ventas:** colocación × mix por modelo.
- **Recaudo DISCRIMINADO (requisito CEO):**
  - `cuota_inicial_mes = Σ_modelo (colocación_modelo × cuota_inicial)`
  - `recaudo_credito_mes = Σ_modelo (Σ ventas vivas × cuota_semanal × semanas_del_mes)`
    — cada venta abre una ventana de `plazo_semanas` cuotas (motor cuota-a-cuota de
    la hoja 'Modelo Pagos'); el recaudo del mes = cuotas activas de todas las ventas
    vivas.
  - `ingreso_bruto = cuota_inicial + recaudo_credito` (se muestran SEPARADOS).
- **Egresos:** costo motos (colocación × costo_auteco, con el plazo de pago Auteco),
  gastos fijos, costos operativos (GPS × motos activas).
- **Flujo:** `flujo_neto = ingreso − egresos`; `disponible_acumulado[m] =
  disponible[m-1] + flujo_neto[m]`, arrancando en caja inicial.
- **Salida:** serie mensual (todo Decimal→string) + KPIs: **piso de caja**, **mes
  más ajustado**, disponible a dic-2030, **meses bajo el mínimo**, y por mes el
  estado OK/Alerta (disponible vs caja mínima).
- Endpoint `GET /proyeccion` (`dashboard:leer`, compute-only, sin estado).

**4. Objetivo de venta (norte):** dado el umbral, cuántas motos/mes evitan cruzar la
caja mínima (búsqueda simple sobre la colocación). Fase 1: reporta el mes crítico y
el faltante; el resolvedor de "motos objetivo" puede ir en COCK-04.

## Decisiones declaradas (necesito tu confirmación — son tuyas)

- **D1 — Excel canónico:** el Blueprint pregunta si `FIXED` reemplaza a `CAMBIOS CON
  APACHE` o son escenarios distintos. **Propongo:** Fase 1 = un solo escenario base
  con modelos administrables (Apache se agrega como modelo, no como variante de
  código). Los 3 escenarios (Conservador/Base/Agresivo) son COCK-04. ¿OK?
- **D2 — valores reales de los drivers:** las cifras canónicas (cuota inicial/semanal
  por modelo, gastos ~$141,9M/mes, caja mínima $55M, precios) viven en el SIMULADOR
  2030 (sensible, fuera del repo). **Fase 1 los captura el CEO a mano en la app**
  (Blueprint §Datos); los tests usan valores ILUSTRATIVOS solo para probar la lógica
  (no es "demo con datos de juguete" — la demo real usará tus cifras). ¿OK, o subes
  el Excel para calcar fórmulas celda-a-celda?
- **D3 — impuesto de renta:** el modelo 2030 hoy NO lo proyecta (Blueprint §5.6).
  Propongo dejarlo fuero de Fase 1 (como el Excel). ¿OK?
- **D4 — mora/recuperación:** PARAMETROS los trae (pesimista/base/optimista). Fase 1
  usa un solo escenario (% recuperación base sobre el recaudo). Los escenarios
  completos → COCK-04. ¿OK?

## Semántica / reglas

Decimal end-to-end (string en API). América/Bogotá, meses al día 1. Pydantic strict.
Compute-only (el motor no escribe transacciones; proyecta). CR-COCK: eventos de
gestión de modelos/parámetros (`modelo_moto.creado/editado/desactivado`,
`parametros_proyeccion.actualizado`) + capacidad `proyeccion:gestionar` — se fija el
número exacto al construir. Modelos/parámetros administrables (regla 9).

## Pregunta al CEO

¿GO para construir COCK-01 Fase 1 (motor + `ModeloMoto` administrable + parámetros
manuales + proyección discriminada a dic-2030 con caja mínima) con TDD, y con las
decisiones D1–D4 como las propongo? Si prefieres subir el SIMULADOR 2030 para calcar
las fórmulas exactas antes, lo espero; si no, construyo la lógica del Blueprint/
PROYECCIONES y tú cargas tus cifras.
