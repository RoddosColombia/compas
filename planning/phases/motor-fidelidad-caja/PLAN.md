# PLAN — Fidelidad de caja del motor C7 (CR "Fidelidad")

**Fase:** `motor-fidelidad-caja` · **Fecha:** 2026-07-25 · **Autor:** Claude Code
**Gate:** Kimi ausente → **GO del CEO** habilita construir (gate-waiver trazable +
auditoría Kimi retroactiva). Código CRÍTICO de dinero.
**Docs contrato:** `docs/modelo/PROYECCIONES.md`, `docs/modelo/referencia/Dashboard_Artefacto.jsx`
(fuente canónica), `docs/modelo/AUDITORIA-IVA-ARTIFACT-V2.md`, `COMPAS_NORTE.md`;
CLAUDE.md reglas 1, 2, 3, 4, 9, 11 + SKILL IVA cuatrimestral.

## Problema (en una oración)
El motor C7 omite **dos líneas de caja** que el artefacto de referencia SÍ tiene — el
**recaudo de la cartera previa** (subestima caja) y el **IVA** (sobreestima caja) — por lo
que la proyección del umbral de mayo-2027 no es confiable.

## Objetivo
Que el motor **reproduzca el Excel validado** (`Dashboard_Artefacto.jsx`, diferencia
< 0.1%) y por tanto la decisión insignia (umbral mayo-2027) sea confiable. Las dos
correcciones tienen **signo opuesto** → se acoplan en UN CR; ninguna cifra corregida se
muestra a junta hasta que aterricen ambas + pase la paridad.

## Alcance — 3 piezas (cada una con TDD)

### PR-1 — Cartera previa (recaudo de los 111 créditos preexistentes) ← ARRANCA AQUÍ
La serie EXACTA (97 semanas, w1 = mié 2026-03-04 → w97 ≈ ene-2028; con moras reales)
ya vive en el repo (`Dashboard_Artefacto.jsx` → `RECAUDO_PREVIA_SEMANAL`).
- **Unidad 1 — datos persistentes** `CarteraPreviaRecaudo` (o config equivalente):
  `semana_global:int · recaudo:Money · n_activos:int`. Administrable (regla 9), baja
  lógica, **seed idempotente** desde la serie del artefacto (migración fechada). Captura
  única; es historia fija (serie finita que se agota ~ene-2028).
- **Unidad 2 — motor:** `recaudo_credito_mensual` suma `recaudo_previo(w)` por cada
  semana de cobro del mes; `cartera_activa_mensual` suma `activos_previos(w_ref)`.
  Funciones puras, Decimal, réplica de las líneas 451/473 del artefacto.
- **Nota clave:** la previa NO es una de las "2 vías" (inicial vs crédito); es un **tercer
  sumando** del recaudo de crédito. Se mantiene la discriminación existente.
- **Salida:** la caja proyectada 2026-27 sube por el recaudo previo; el `MesProyeccion`
  puede exponer `recaudo_previo` como sub-línea informativa (a decidir en TDD).

### PR-2 — IVA cuatrimestral (esto ES el C11 diferido, acoplado aquí)
- Entidad `Factura` por **cargue** (requisito CEO): compras Auteco, otras compras
  deducibles, ventas RODDOS. `iva_generado` (ventas × 19/119) − `iva_descontable`
  (compras × 19%) con **arrastre de saldo a favor**.
- **Egreso de IVA en la caja en la fecha DIAN real** (dígito NIT 2: 13-may-26 /
  10-sep-26 / 14-ene-27) — corrige la omisión IVA del motor. Fondo de provisión sugerido.
- Vista IVA del cockpit (reemplaza el placeholder). Reusa/created eventos ya existentes
  (`factura.creada`, `iva.declarado`, `iva_generado.override`, `factura_emitida.*`).

### PR-3 — Test de paridad golden-master (tarea #21)
El motor Python reproduce las salidas del artefacto con su config por defecto (2 modelos
Raider/Apache + la previa), diferencia < 0.1%. Es el control que caza omisiones; corre en
CI. Se hace parcial tras PR-1 (previa) y completo tras PR-2 (IVA).

## Orden de construcción (TDD, red→green)
1. **PR-1 previa** primero: chico, autocontenido, toca el umbral. Seed + motor + tests.
2. **PR-3 parcial**: paridad de recaudo/cartera con la previa incluida.
3. **PR-2 IVA/C11**: el módulo grande (Factura + liquidación + egreso DIAN + vista).
4. **PR-3 completo**: paridad de la caja completa < 0.1%.

## CR (declarar antes de construir — regla 11)
- **Entidad nueva** `CarteraPreviaRecaudo` (PR-1) + `Factura` (PR-2, si no existe ya el
  armazón). Verificar contra `domain/` antes de crear.
- **Evento nuevo** (PR-1): `cartera_previa.cargada` (seed/carga de la serie). Catálogo
  cerrado hoy 44 → 45. Los eventos de IVA/factura ya existen en `events.py`.
- **Capacidad:** reusar `proyeccion:gestionar` para la previa; IVA a decidir en PR-2.

## Semántica / reglas innegociables
Decimal end-to-end (string en API, regla 1). América/Bogotá, meses al día 1, fechas DIAN
`YYYY-MM-DD` (regla 2). Pydantic strict+forbid (regla 3). Motor **compute-only**; la previa
es dato persistente, no toca el histórico (regla 4). Administrable por capacidad (regla 9).
Eventos solo del catálogo + este CR (regla 11). **IVA CUATRIMESTRAL, nunca bimestral.**

## Decisión a confirmar con el CEO (D-A)
**¿Cómo se captura la cartera previa?**
- **Opción 1 (recomendada):** serie semanal EXACTA como dato persistente, sembrada desde
  la del artefacto (ya en el repo). Máxima precisión (incluye moras reales), reproduce el
  Excel, habilita el golden-master. Bajo esfuerzo: la data ya existe.
- **Opción 2:** aproximación paramétrica (n activos inicial, cuota promedio, semanas
  restantes). Menos preciso, NO casa con el golden-master.

## Pregunta al CEO
¿**GO** para construir el CR "Fidelidad de caja" en este orden (PR-1 previa → paridad →
PR-2 IVA → paridad completa), con TDD, y con la **Opción 1** para la previa? Con tu GO
arranco por PR-1 (seed + motor + tests) sin tocar más nada.
