# SOLICITUD de auditoría Kimi — FABS Incremento 2 (loop del agente + verificador cifra→evidencia)

- **Target:** PR1 (código) · **Ronda:** I (inicial)
- **Rama:** `feat/fabs-inc2` · **Commits:** `4085944..1955cb9` (16 commits de código + 1 de docs `74ad981`)
- **Fecha:** 2026-08-17 · **Solicita:** Andrés (CEO) / Claude
- **Por qué gate (crítico):** conecta el **LLM** que **lee cifras de plata** para asesorar decisiones, **agrega 2 eventos al catálogo cerrado de auditoría** (CR-CFO-1) y toca **RBAC** (nueva capacidad). Merge crítico según la política del proyecto. **Umbral: ≥ 9.0.**

## Qué es (una línea)

El **loop del agente CFO (FABS)** sobre el cimiento determinista de inc1: un módulo `backend/app/cfo/agente/` que deja que **el LLM elija qué concepto de COMPAS leer** (tools de solo lectura) y **narre**, con un **verificador cifra→evidencia** que **impide publicar cualquier número que no venga de una tool**. El modelo **nunca calcula**: si una cifra no tiene respaldo, FABS **se abstiene**. Todo detrás del flag `CFO_ENABLED` **apagado** ⇒ COMPAS byte-idéntico.

## Qué hace, con evidencia verificada al peso

1. **Verificador cifra→evidencia** (`agente/verificador.py`) — EL control (lección Deloitte). Extrae toda cifra monetaria/unitaria/porcentual del texto del modelo y exige que cada una esté dentro de tolerancia (±$1 COP / ±0,1 meses) de un valor que **una tool devolvió en este turno** (conjunto cerrado). Cifra sin respaldo ⇒ `ok=False` ⇒ no se publica. **Robusto al formato wire real** de las tools (`str(Decimal(money_str(x)))` = `"704722003.00"`, punto decimal) y al es-CO humano (`$704.722.003`), distinguidos por semántica de separadores. **Porcentajes** siempre huérfanos (COMPAS no calcula %). Batería adversarial de 24 casos.
2. **3 tools de solo lectura** (`agente/tools.py`) sobre los conceptos de inc1 (caja hoy · runway · IVA cuatrimestre), cada una devuelve `ResultadoCFO` completo (valor **string**, evidencia, `disponible`). Dispatcher cerrado; tool desconocida ⇒ `KeyError` (fail-closed).
3. **Loop acotado** (`agente/loop.py`, ≤3 iter, temp 0.1, modelo por config) — ciclo modelo↔tool; no muta la lista del caller; el texto solo se produce, la verificación la hace el servicio.
4. **Servicio orquestador** (`agente/servicio.py`) — emite `cfo.consulta` → loop → verifica → **1 reintento correctivo** → publica o **se abstiene** (`sin_api_key`/`tope_iter`/`verificacion`/`error_llm`/`error`); **backstop de nivel superior**: `consultar` NUNCA revienta al caller (un read siempre devuelve `RespuestaCFO`). **Auditoría fail-soft**: un fallo de la BD de auditoría no bloquea la respuesta.
5. **Endpoint** `POST /api/v1/cfo` (`agente`/`router.py`) — **doble barrera** (router montado en `create_app()` solo si `cfo_enabled()` + guard 404) + `require_permission("cfo:consultar")` + `actor_id = str(user.id)` **real**.
6. **CR-CFO-1**: eventos `cfo.consulta` + `cfo.respuesta` al catálogo cerrado (62 → 64). Cliente Anthropic lazy (`anthropic==0.100.0`), key **solo por env var** (nunca en repo).

## Puntos a auditar con lupa

- **Regla #1 (ninguna cifra sin evidencia; el modelo no calcula):** ¿el verificador atrapa TODA fabricación monetaria plausible (dígito pelado, es-CO, con/sin centavos, %, suma inventada)? ¿la abstención es honesta (nunca un $0 falso)?
- **Deferral vinculante:** el verificador agrupa evidencia por **unidad** (COP/meses), no por **concepto** (caja e iva comparten COP) → una cifra REAL mal etiquetada podría pasar. Documentado en código; **exposición cero con flag OFF**. ¿De acuerdo en diferirlo a un CR antes de encender el flag (inc3)?
- **Flag-off = COMPAS idéntico:** router ausente de `create_app()`, sin efectos de import (anthropic es lazy), S1 intacto. Confirmar.
- **Motor intocable:** `backend/app/proyeccion/motor.py` **cero diffs** (`git diff 229746f..HEAD -- app/proyeccion/motor.py` vacío).
- **Decimal en todo el pipeline** (regla 1); montos como string; cero float.
- **Auditoría:** `cfo.consulta` antes de responder, `cfo.respuesta` siempre, fail-soft; catálogo cerrado (+2 vía CR). **RBAC** por dependencia (§4.1), sin over-grant.

## Evidencia local (verde)

- **Suite backend completa: 1009 passed / 95 skipped (requires_real_mongo) / 0 failed** con el módulo presente y el flag apagado (COMPAS idéntico).
- Suite `tests/cfo/`: **74 passed**. Verificador: **24 casos adversariales** (incl. formato wire real + porcentajes).
- `python -m ruff check app/cfo/` limpio. `motor.py` cero diffs.
- **Construido con SDD** (subagente por tarea + review de dos etapas por tarea + review final whole-branch en el modelo más capaz). El review final: *"Ready to merge — With fixes"*, **cero Critical de código**; los 2 Important + 1 Minor se cerraron (porcentajes, doc de huecos residuales, guard cero) y se re-revisaron limpios.

## Alcance declarado (lo que NO hace)

Sin canal (Telegram = inc3), sin memoria de conversación, sin alertas/Comité (inc4), sin escrituras sobre datos financieros, sin el set completo 240+60 de goldens. Alegra = cero. CXC socios / devengado = fuera. `ANTHROPIC_API_KEY` se configura en Render **al arrancar inc3**; en inc2 todo se testea con el cliente Anthropic **mockeado** (CI verde sin key).

## Pregunta al auditor

¿El loop + el verificador son sólidos y seguros para operar (una vez encendido el flag en inc3)? ¿Algún camino por el que una cifra fabricada llegue al usuario con `abstuvo=False`? ¿Algún hueco en la abstención, el aislamiento S1, la auditoría fail-soft o el RBAC que deba cerrarse antes del merge o antes de encender el flag?
