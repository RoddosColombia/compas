# SOLICITUD de auditoría Kimi — FABS Incremento 1 (cimiento determinista)

- **Target:** PR1 (código) · **Ronda:** I (inicial)
- **Rama:** `feat/fabs-inc1` · **Commits:** `588a300..0a8f0ca` (13 commits)
- **Fecha:** 2026-08-11 · **Solicita:** Andrés (CEO) / Claude
- **Por qué gate:** FABS **lee cifras de plata** (caja, runway, IVA) para alimentar decisiones — merge crítico según la política del proyecto. **Umbral: ≥ 9.0.**

## Qué es (una línea)

El **cimiento determinista** del agente CFO (FABS): un módulo `backend/app/cfo/` de **solo lectura** que consume el motor que COMPAS ya tiene y devuelve **cada cifra con su evidencia**, más el arnés de evaluación (goldens). **Sin LLM todavía** (eso es el incremento 2). Flag `CFO_ENABLED` **apagado** ⇒ COMPAS byte-idéntico.

## Qué hace, con evidencia verificada al peso

1. **Contrato cifra→evidencia** (`cfo/calc/evidencia.py`): `ResultadoCFO{concepto, valor:Decimal|None, unidad, disponible, evidencia{fuente, fecha_corte, ref}, detalle}`. El modelo nunca calcula; sin dato → `disponible=False, valor=None` (**abstención honesta**, corrige el defecto FP6 del legado SISMO-V2).
2. **3 conceptos** que envuelven servicios de COMPAS (fórmulas viven en COMPAS, D5):
   - `caja_hoy` ← `caja.service.caja_diaria` (último saldo + fecha de corte).
   - `runway` ← `proyeccion.service.proyectar_vigente` (KPI `runway_meses`).
   - `iva_cuatrimestre` ← `facturas.service.liquidacion_iva` (neto del cuatrimestre vigente + fecha DIAN).
   Verificados contra PROD (read-only, 2026-08-11): caja 704.722.003; runway abstención (sin quema neta); IVA C2-2026 36.204.698,10 (DIAN 10-sep).
3. **Refactor DRY** `liquidacion_iva()`: extraído del router de facturas al servicio (endpoint **idéntico**, probado por 153 tests de facturas/IVA verdes). Helpers `etiqueta_periodo`/`proximo_pago` movidos a `app/iva/liquidacion.py` (lógica byte-idéntica).
4. **Arnés de goldens** (`cfo/goldens/`): modelo `cfo_goldens`, runner con tolerancia híbrida ($1 COP / 0,1 meses) + casos de abstención, semilla idempotente (snapshot real de PROD).
5. **Salvaguarda S1** (`tests/cfo/test_s1_aislamiento.py`, no-vacía): `cfo/` solo importa la capa de servicios de COMPAS; escribe solo en `cfo_*`.

## Puntos a auditar con lupa

- **Regla #1 (ninguna cifra sin evidencia; el modelo no calcula):** ¿todo `ResultadoCFO` trae evidencia? ¿la abstención es honesta (nunca un $0 falso)?
- **Motor intocable:** `backend/app/proyeccion/motor.py` **cero diffs** (confirmar ausente del diff).
- **Flag-off = COMPAS idéntico:** ningún router `cfo` registrado; los únicos cambios a código existente son el refactor DRY (comportamiento preservado), el registro de `CFOGolden` y el bump de la aserción `len(DOMAIN_DOCUMENTS)` 19→20.
- **S1:** ningún import de `app.domain.*` ni del driver de Mongo en `cfo/calc`|`cfo/goldens` (salvo `goldens/modelo.py`).
- **Decimal en todo el pipeline** (regla 1); cero float.
- **Sin eventos de auditoría nuevos** (catálogo cerrado intacto).

## Evidencia local (verde)

- Suite COMPAS completa: **940 passed / 95 skipped / 0 failed** con el módulo presente y el flag apagado (idéntico).
- Suite `tests/cfo/`: **17 passed**. Facturas/IVA tras el refactor: **153 passed**.
- `ruff check app/cfo/` limpio.
- Construido con SDD (subagente por tarea + review de dos etapas). **Review final de rama (whole-branch): APPROVE FOR MERGE**, 0 Critical/Important; 3 minors diferidos a inc2 (documentados en `docs/COMPAS_FABS_ROADMAP.md §6`).

## Alcance declarado (lo que NO hace)

Sin LLM, sin Telegram, sin alertas, sin escrituras sobre datos financieros, sin el set completo de 240+60 goldens (esto es el arnés + semilla). Alegra = cero. CXC socios / devengado = fuera.

## Pregunta al auditor

¿El cimiento es sólido y seguro para que el incremento 2 (loop del LLM) construya encima? ¿Algún hueco en el contrato de evidencia, la abstención, el aislamiento S1, o el refactor DRY que deba cerrarse antes de conectar el modelo?
