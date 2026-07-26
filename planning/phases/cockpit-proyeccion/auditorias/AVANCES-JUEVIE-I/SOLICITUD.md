# SOLICITUD DE AUDITORÍA — AVANCES JUE-VIE (2026-07-23 y 24) · Ronda I

**Para:** Kimi (auditoría adversarial, RETROACTIVA) · **Umbral:** ≥ 9.0
**Fecha:** 2026-07-25 (sábado) · **Autor:** Claude Code · **Autoriza merge:** CEO (Andrés)
**Rama base:** `main` (auto-deploy; todo lo de abajo YA está en producción)
**Docs contrato:** `docs/modelo/PROYECCIONES.md`, `docs/modelo/ARQUITECTURA_PRESUPUESTAL.md`,
`docs/Compas_Blueprint_UX.docx`, `COMPAS_NORTE.md`, `docs/COMPAS_Spec_Tecnica_v1_1_2.docx`;
CLAUDE.md reglas 1–12.
**Evidencia:** `EVIDENCIA.md` (código y salidas de tests reales, en este mismo paquete).

---

## 0. Regla de juego de esta auditoría (léela primero)

Esto es una **auditoría RETROACTIVA**, no un gate pre-merge. Kimi estuvo **ausente**
hasta el 25-jul; durante jue-vie el CEO autorizó los merges bajo **gate-waiver
trazable** (registrado en el tracker, hoja Gates), con el compromiso explícito de
**auditoría Kimi retroactiva** una vez disponible. Este paquete cumple ese compromiso.

- **NADA aquí simula una aprobación de Kimi.** Los merges se hicieron bajo GO del CEO,
  no bajo una nota de Kimi inventada.
- Se pide veredicto retroactivo (nota + hallazgos accionables) sobre **todo** lo
  construido jue-vie, con foco en el **código crítico de dinero**.
- **Autodivulgación:** el propio autor encontró **dos omisiones materiales del motor
  C7** (§5). No se ocultan para “pasar el gate”: se declaran, se cuantifica su efecto y
  se propone la remediación. Se pide a Kimi que las valide y busque **otras**.

---

## 1. Inventario de lo desarrollado jue-vie

### Crítico de dinero (lo que Kimi audita a fondo)
| # | Área | Commit(s) | Estado gate |
|---|---|---|---|
| A | **Motor de proyección C7** (COCK-01/02): motor puro + `ModeloMoto` + `ParametrosProyeccion` + `GET /proyeccion` + CR-COCK | `395d3c4` (#33) | **PLAN aprobado por CEO; CÓDIGO sin auditar** ← centro |
| B | **C4 — Ajuste diario de caja** (CR-S6): `PATCH /meses/{mes}/saldos` + conciliación | `670ba4e` (#27) | merge bajo gate-waiver CEO; retro pend. |
| C | **C9 — Pagos de la semana** (CR-S7): `PagoPlaneado` + veredicto | `be9512b` (#29) | merge bajo GO CEO; retro pend. |
| D | **COCK-00 — Fundación plan de cuentas** (ARQUITECTURA_PRESUPUESTAL): `Rubro` con código + grupos + Fijo/Variable | `c2c0faf` (#31), `737bcb0` (#32) | merge bajo GO CEO; retro pend. |

### Presentación / sin-gate (incluido a pedido del CEO, revisión ligera)
| # | Área | Commit(s) |
|---|---|---|
| E | **C5 — Vista combinada categoría × cuenta** (read-only) | `635fe5e` (#30) |
| F | **Cockpit frontend Blueprint** — Fase A (sistema de diseño + shell) + Fase B (8 vistas: Proyecciones, Inicio, Datos, Escenarios, Presupuesto re-vestido, Reportes, Dashboards, herramientas re-vestidas) | `a7b2101`, `b2fc416`, `f9307fa`, `f66424d`, `9801fec`, `ebb46c5`, `704607e`, `2f55aa6`, `6491131`, `41bde32` |
| G | Pantalla Caja C4 (frontend) | `f95d364` (#28) |

---

## 2. Qué hace cada área — CRÍTICO

### A. Motor de proyección C7 (el corazón del producto) — CENTRO DE ESTA AUDITORÍA
Réplica en Python (funciones **puras, compute-only**, auditable celda-a-celda) de la
formulación limpia del SIMULADOR 2030 (`docs/modelo/referencia/Dashboard_Artefacto.jsx`).
Produce, mes a mes y a horizonte configurable (hasta 180 meses):
1. **Semanas exactas de cobro** (miércoles reales del mes; jul-26 = 5, no “4 fijas”).
2. **Colocación encadenada** `C10 = ROUND(C9×(1+g))` (50,51,52… con soporte de rampa real).
3. **Recaudo DISCRIMINADO en 2 vías** (requisito CEO, SIEMPRE separadas):
   Vía 1 = recaudo de crédito **cuota-a-cuota** (ventana de `plazo_semanas` por venta);
   Vía 2 = cuotas iniciales (`Σ colocación×cuota_inicial`).
4. **CAJA VERAZ** (decisión CEO 2026-07-23): `neto = bruto + mora + recuperación +
   default`; la **provisión NIIF 9 NO resta caja** (va a P&G), y mora/default son
   **editables mes a mes** (overrides) con default al % del escenario.
5. **Egresos:** inventario Auteco **saldo rodante anti-doble-conteo** (el lote se paga
   una vez, desfasado `INT(plazo/30)` meses) + fondeo + gastos fijos + GPS×cartera +
   costo moto nueva + interés de deuda (ventana de meses).
6. **Flujo + caja acumulada + KPIs:** piso de caja, mes más ajustado, meses bajo el
   umbral, caja final, capital requerido, runway. Primer mes con caja fija.
7. **Escenarios** (presets mora/recuperación pesimista/base/optimista).
Entidades **administrables** (regla 9): `ModeloMoto` y `ParametrosProyeccion`
(versionado por `vigente_desde`), CRUD con capacidad `proyeccion:gestionar`, baja lógica.
Endpoint `GET /api/v1/proyeccion` compute-only (`dashboard:leer`), fail-closed si falta
config (409, no inventa cifras). CR-COCK: 4 eventos nuevos del catálogo cerrado +
capacidad `proyeccion:gestionar`.

### B. C4 — Ajuste diario de caja (CR-S6)
`PATCH /api/v1/meses/{mes}/saldos`: reporte diario de saldos por banco + conciliación.
Transaccional multi-documento; guardas de **no-retroceso por banco** e integridad
(TOCTOU cierre/reapertura acotado). Evento de auditoría del catálogo.

### C. C9 — Pagos de la semana (CR-S7)
`PagoPlaneado` (Document) + servicio con **veredicto** (planeado vs ejecutado) y
`/api/v1/pagos`. Capacidad + evento del catálogo. Marca de pago con test real-mongo.

### D. COCK-00 — Fundación plan de cuentas (ARQUITECTURA_PRESUPUESTAL)
`Rubro` reestructurado a los **6 grupos** con **código de cuenta** y clasificación
**Fijo/Variable**, expuesto en API y en la pantalla Categorías. Armazón sin datos de
negocio; baja lógica; `es_sistema` protegido.

---

## 3. Cambios de valores esperados (verificados al peso, en tests)

| Caso (motor C7) | Antes | Después | Test |
|---|---|---|---|
| Semanas de cobro jul-2026 | (no existía) | **5** miércoles (1,8,15,22,29) | `test_julio_2026_tiene_cinco_miercoles` |
| Colocación 50 @1% encadenada | — | **50,51,52,53,54** (no 50×1.01^k) | `test_colocacion_encadenada_...` |
| Recaudo cuota-a-cuota cruza meses (1 moto, cuota 100, plazo 6, jul-26) | — | jul=**500**, ago=**100** | `test_recaudo_credito_cuota_a_cuota_cruza_meses` |
| Neto con provisión (bruto 1000, mora 3%, rec 40%, def 3%, **prov 2%**) | 932 (si prov restara) | **952.00** (prov NO resta caja) | `test_neto_por_mora_caja_veraz_excluye_provision` |
| Inventario Auteco saldo rodante (lote 10.000, plazo 150d) | doble-conteo | pago único desfasado (m5=-5000, m6=-9000) | `test_inventario_auteco_saldo_rodante_y_fondeo` |
| Primer mes de caja | — | **fija = caja inicial** (flujo no la mueve) | `test_proyectar_caja_acumulada_primer_mes_fijo` |

---

## 4. Semántica preservada (NO cambia)
- **Dinero = Decimal** end-to-end; API expone montos **string** (`money_str`); frontend
  `decimal.js-light`, nunca `Number` sobre montos (regla 1). Motor cuantiza COP 2 dec.
- **América/Bogotá**, meses al día 1; el motor opera con `datetime.date` de calendario (regla 2).
- **Pydantic `strict=True, extra="forbid"`** en las entidades nuevas (regla 3).
- **Histórico inmutable**; el motor es **compute-only**: no escribe transacciones ni toca
  meses cerrados (regla 4 en espíritu). `audit_log` append-only intacto.
- **RBAC por capacidad** (regla 9): navbar del cockpit derivado de un único config
  (`navegacion.ts`); nada mapea rol→UI disperso.
- **Catálogo de eventos cerrado** (regla 11): solo se añaden los del CR-COCK y los CRs S6/S7.

---

## 5. ⚠ AUTODIVULGACIÓN — dos omisiones materiales del motor C7 (auditar con lupa)

El autor auditó el motor contra su **artefacto de referencia** (`Dashboard_Artefacto.jsx`,
commit `29850fd` del 22-jul, que el motor dice replicar) y encontró **dos líneas de caja
del artefacto AUSENTES del motor**. Ambas son de **efectivo real** y afectan la decisión
insignia (umbral de mayo-2027).

### 5.1 Cartera previa (recaudo de los 111 créditos preexistentes) — OMITIDA
- **El artefacto** suma cada mes `recaudoPrevio(w)` al recaudo y `activosPrevios(wRef)` a
  la cartera (líneas 451 y 473): la **serie semanal EXACTA de los 111 créditos vivos** del
  LoanTape (con moras reales).
- **`motor.py` NO lo hace:** `recaudo_credito_mensual` solo proyecta recaudo de las motos
  colocadas *dentro* del horizonte. No hay campo en `ParametrosProyeccion` ni mecanismo
  que lo inyecte.
- **Cronología (git):** artefacto con la previa = 22-jul; motor = 24-jul (dos días
  después, mismo repo) → **omisión original**, no regresión, ajena a v6.
- **Materialidad y signo:** en 2026-27 la cartera previa es la fuente **dominante** de
  recaudo (las motos nuevas apenas acumulan cuotas). Omitirla **SUBESTIMA la caja** justo
  en el período del umbral. `PROYECCIONES.md` §Drivers ya la listaba (“motos iniciales en
  cartera”) → el motor está **incompleto vs su propia spec**, no scoped-down a propósito.

### 5.2 IVA — OMITIDO del flujo
- El `egresos` del motor **no tiene línea de IVA**. El artifact v6 (Fabián) aporta un
  módulo de IVA cuatrimestral (auditado en `docs/modelo/AUDITORIA-IVA-ARTIFACT-V2.md`).
- **Signo OPUESTO al de la previa:** el IVA omitido (egreso) **SOBREESTIMA la caja**.
  Diferido como C11 (IVA-01…06) por decisión del CEO.

### 5.3 Consecuencia y remediación propuesta
Los dos errores tienen **signo opuesto** → arreglar solo uno **empeora** el sesgo neto.
Por eso se propone **un solo CR “Fidelidad de caja del motor C7”**: cartera previa + IVA
+ el **test de paridad golden-master** (tarea #21, prometido en el PLAN-I y diferido — es
justo el control que habría cazado la omisión). Ninguna cifra corregida se muestra a
junta/CEO hasta que aterricen las dos y pase la paridad. **Se pide a Kimi** validar esta
caracterización, el signo/materialidad, y si hay **otras** líneas del artefacto ausentes.

---

## 6. Puntos a auditar con lupa
1. **§5 — las dos omisiones del motor.** ¿La caracterización (mecanismo, signo,
   materialidad) es correcta? ¿Hay OTRAS líneas del `Dashboard_Artefacto.jsx` que el
   motor no replique (p. ej. inyección de capital `mesInyeccion`, eventos `overrides`,
   balance/P&G)? ¿El CR de remediación propuesto es suficiente?
2. **Motor — anti-doble-conteo Auteco** (`inventario_auteco_mensual`): el saldo rodante
   con `max(pago[m-1],0)` y el desfase `INT(plazo/30)`. ¿Reproduce el fix del artefacto
   sin fugas ni doble pago?
3. **Caja veraz:** que la provisión quede FUERA del flujo pero SÍ en las métricas P&G.
   ¿Coherente con la decisión CEO y sin subestimar la pérdida esperada dos veces?
4. **Decimal/redondeo:** cuantización `ROUND_HALF_EVEN` COP en el motor vs `ROUND_HALF_UP`
   en conteos enteros (colocación, split por mix). ¿Consistente con el artefacto?
5. **C4/C9 — transaccionalidad y guardas:** no-retroceso de saldos, TOCTOU
   cierre/reapertura, idempotencia. ¿Fail-closed real?
6. **RBAC y eventos:** capacidades nuevas (`proyeccion:gestionar`) y eventos solo del
   catálogo cerrado. ¿Alguna ruta sin dependencia de permiso?

---

## 7. Evidencia local (salidas reales — ver `EVIDENCIA.md`)
- **Backend crítico (9 áreas):** `129 passed` (motor, proyección endpoints, caja saldos
  guards, pagos semana, rubros endpoints, domain rubro, control por cuenta, audit events,
  rbac). Motor puro aislado: `18 passed`.
- **Frontend:** `npm run build` verde (tsc -b + vite) · `vitest run` = `49 passed` / 17 files.
- **Suites `*realmongo`** (caja/pagos): requieren `COMPAS_TEST_MONGO_URI` (cluster), no
  disponible en esta sesión; verdes en CI al mergear cada PR. Se declara sin maquillar.
- Reglas innegociables verificadas: Decimal/string, TZ Bogotá, Pydantic strict+forbid,
  motor compute-only, audit append-only, eventos del catálogo, RBAC por capacidad.

## 8. Cumplimiento del DoD / reglas de CLAUDE.md
Cubre DoD de proyección (motor auditable + KPIs + horizonte), reglas 1 (Decimal), 2 (TZ),
3 (strict), 4 (inmutable/compute-only), 9 (RBAC/nav único), 11 (catálogo eventos). Pendiente
declarado: **tarea #21 (paridad golden-master)** y el **CR de fidelidad** de §5.
