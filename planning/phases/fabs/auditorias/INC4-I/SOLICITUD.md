# SOLICITUD de auditoría Kimi — FABS inc4 rebanada 1 (cerebro analítico · what-if de escenarios) · CÓDIGO

- **Target:** PR (código) · **Ronda:** I (inicial, RETROACTIVA) · **Umbral: ≥ 9.0**
- **Rama:** `feat/fabs-inc4-escenarios` → **YA MERGEADA a main** (`2511398..31684e6`) y **EN VIVO** en el piloto.
- **Fecha:** 2026-08-26 · **Solicita:** Andrés (CEO) / Claude
- **Gate:** **gate-waiver GO CEO 2026-08-23** (Kimi no disponible ~semanas; el CEO autorizó construir y soltar a vivo). Esta es la auditoría **retroactiva** de diseño+código — el gate NUNCA se simuló. Se pide con la pieza YA en producción; si hay hallazgos, se corrigen sobre lo vivo.
- **Por qué gate (crítico):** produce **cifras que el CEO usa para decidir** (impacto en caja, mes de quiebre del umbral, cuántas motos vender). Toca el motor de proyección (de forma ADITIVA) y el control anti-alucinación de FABS. Flag `CFO_ENABLED` **encendido**.

## Qué es (una línea)

FABS ahora responde un **what-if de escenario** en lenguaje natural —*"si arriendo una bodega de $X/mes desde el mes M, ¿cómo me pega en caja, en qué mes cruzo el umbral, y cuántas motos de más vendo para evitarlo?"*— corriendo el **motor real de COMPAS**, sin que el modelo haga una sola operación: COMPAS calcula, FABS cita con evidencia.

## Qué hace, con evidencia verificada al peso

1. **Dos herramientas nuevas** que el modelo puede invocar (primeras tools con parámetros de FABS): `impacto_escenario` (impacto mes a mes + piso con/sin + **mes de quiebre** del umbral) y `motos_para_evitar_umbral` (solver: cuántas unidades extra/mes para no cruzar el umbral).
2. **Las dos respuestas corren sobre el MISMO pipeline completo** (motor → E1 anclaje → D2 reconciliación) → **reconcilian**. Esto fue un fix crítico que atrapó la revisión Opus: con el solver sobre una base motor-only, el "cuántas motos" podía **subestimar el umbral** frente a `impacto_escenario` (falsa confianza en el número de decisión). Verificado EN VIVO: bodega $10M/mes → piso con arriendo **$71.199.133 idéntico** desde ambas herramientas.
3. **Solver de unidades** nuevo (`proyeccion/solver_unidades.py`): bisección **entera** acotada a `[0, cap]`, con `piso(cap)` como oráculo de alcanzabilidad (corrige un bug de la primera versión: falso "no alcanzable" cuando la respuesta caía en `(cap/2, cap]`, + no-enforcement del tope). Async; corre el pipeline completo por candidato N.
4. **Aislamiento S1 respetado:** `cfo/calc` NO importa dominio/motor; el armado de la proyección con params propuestos vive en `proyeccion/service.py::fabrica_proyectar_unidades` (ADITIVO — `motor.py` cero diffs).
5. **Garantía anti-alucinación extendida (multi-valor):** una tool devuelve VARIOS `ResultadoCFO` nombrados; el modelo cita `[[piso_con]]`/`[[impacto_mensual]]`/`[[unidades_extra]]`/`[[piso_con_unidades]]`; **el modelo nunca ve los valores** (`resultado_a_dict` los omite); el verificador rechaza toda cifra/mes/**conteo** crudo (nueva unidad `unidades`; `_RE_UNIDADES` caza "12 motos" sin token, incl. el singular "unidad"); el servicio sustituye tras verificar (1 reintento, luego abstención `motivo="verificacion"`, jamás loop).

## Puntos a auditar con lupa

- **Reconciliación de las dos herramientas:** ¿corren de verdad el mismo pipeline (motor→E1→D2, `primer_mes_acumula=True`) de modo que el "impacto/quiebre" y el "cuántas motos" cuadran para el mismo escenario? ¿Algún camino donde diverjan y den falsa confianza sobre el umbral?
- **Anti-alucinación end-to-end con las tools nuevas:** ¿algún camino por el que un peso/mes/conteo llegue al usuario con `abstuvo=False` sin haber sido computado por COMPAS y citado vía token? (Hueco residual declarado: el mes de quiebre viaja en `evidencia.ref` — el modelo podría repetirlo crudo en prosa; NO es invención, es clase pre-existente; fast-follow.)
- **Solver:** ¿la bisección entera devuelve el mínimo N real, respeta el tope, y reporta "no alcanzable" solo cuando ni el tope alcanza?
- **S1 + motor 0 diffs:** `cfo/**` sin importar dominio/motor; `service.py` aditivo; `motor.py` cero diffs en toda la rama.
- **Decimal en todo** (regla 1); `naturaleza`/`monto` validados en la frontera de la tool (raise, no sign-flip silencioso, no float).

## Evidencia local (verde)

- **Suite backend completa: 1264 passed / 98 skipped (requires_real_mongo) / 0 failed.**
- Golden de referencia (`test_escenario_golden.py`, bodega $20M/mes) con los 5 números "al peso", solver REAL (no fakeado), matemática recalculada a mano en el docstring (no re-derivada del código bajo prueba).
- Test end-to-end (`test_servicio.py`): el modelo pide las 2 tools en un turno, cita 4 tokens, el texto publicado trae valores sustituidos (no crudos); conteo crudo → reintento → abstención.
- `motor.py` **cero diffs** (`git diff 2511398..31684e6 -- app/proyeccion/motor.py app/presupuesto/motor.py` vacío). Sin `float(` en el slice. `ruff` limpio. S1 verde.
- **Review final whole-branch (opus): "Ship-ready", 0 Critical, 1 Important = fast-follow.** Construido por SDD (9 tareas, subagente + review por tarea + fix rounds). Smoke del CEO en vivo: sano, reconcilia.

## Alcance / no-alcance

- **Entra:** rebanada 1 = UN tipo de escenario (un ajuste recurrente gasto/ingreso) + el solver de motos + la citación multi-valor. Motor intocable (aditivo).
- **NO entra (fast-follows anotados):** endurecer el verificador para año-mes crudo `\d{4}-\d{2}`; validar formato `YYYY-MM` en las tools; optimizar load-once del solver (~14 corridas del pipeline por consulta); `CONCEPTOS_CITABLES` stale/dead; ancla a caja real de hoy (§7 del spec); escenarios multi-variable; escenarios guardados; nits cosméticos ("0 motos motos", lista de cifras duplicada).

## Pregunta al auditor

¿La rebanada 1 preserva la garantía anti-alucinación con las herramientas nuevas y multi-valor? ¿El "cuántas motos" y el "impacto/quiebre" reconcilian de forma sólida (mismo pipeline) para que el número de decisión no dé falsa confianza sobre el umbral? ¿El solver es correcto y el aislamiento S1 / motor-0-diffs se respetan? ¿Algo que corregir ahora que ya está en vivo?
