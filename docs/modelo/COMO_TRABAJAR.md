# CÓMO TRABAJAR COMPAS (proceso reproducible)

> Una página. Sirve para que cualquier sesión de Claude Code arranque bien, sin
> depender de la memoria de nadie. Si algo se siente perdido, volver aquí.

## 0. Qué es COMPAS (en una línea)
Sistema **predictivo** de presupuesto y caja para **decidir** (NO contable). Detalle:
`docs/COMPAS_NORTE.md`. Regla de oro: *¿esto reproduce su hoja del Excel y apunta a
predecir/decidir?* Si no, hay deriva.

## 1. Al iniciar CADA sesión — leer en este orden
1. `CLAUDE.md` (se carga solo; contiene las reglas innegociables y los punteros).
2. `docs/COMPAS_NORTE.md` — el norte (qué ES y qué NO).
3. `.planning/PROJECT.md` — modelo de datos + capacidades **C1–C11** con estado real.
4. `docs/modelo/MODELO.md` y `docs/modelo/PROYECCIONES.md` — el Excel destilado a contrato.
5. `.planning/codebase/` — arquitectura real (STACK, ARCHITECTURE, CONVENTIONS, CONCERNS…).
6. La memoria (se inyecta sola) + el tracker `docs/COMPAS_Control_Desarrollo.xlsx`.

## 2. Dónde estamos
El estado vivo está en `.planning/PROJECT.md` (tabla de capacidades) y en la hoja
`Tareas`/`Gates` del tracker. Construido: ciclo presupuestal (sugerido→acotar→aprobar),
cierre+conciliación, Vista Control. En curso / pendiente: **C1** categorías administrables,
**C3** auto-clasificación, **C4** ajuste de caja, **C7** motor de proyección (ventas/recaudo,
modelos administrables), **C9** pagos pendientes→caja final proyectada, C10 proveedores, C11 IVA.

## 3. Cómo se construye (ciclo por capacidad)
1. **Brainstorm** el diseño (superpowers:brainstorming) — nunca código sin diseño aprobado.
2. Si toca innegociables (dinero, RBAC, catálogo de eventos, cierre, migración) o es merge
   crítico → **PLAN → gate Kimi ANTES de construir**. Si no, TDD directo.
3. **TDD:** test primero (mongomock para lógica; `@requires_real_mongo` para transacciones
   multi-doc). Código mínimo. `ruff`/`biome` limpios. Greps del protocolo en 0.
4. **PR** + CI verde (incl. `backend-real-mongo`) → **gate de código Kimi** en merges críticos.
5. **Merge a main** solo con nota Kimi ≥ 9.0 + OK del CEO. Push = deploy (Render/Vercel).

## 4. Cómo pedir un gate a Kimi (loop manual)
1. Claude escribe `SOLICITUD.md` (+ `EVIDENCIA.md` en gates de código: diff + salidas de tests)
   en `planning/phases/<fase>/auditorias/<PLAN|PR1>-<I|R>/`.
2. Claude genera el PDF: `python scripts/generate_kimi_audit_pdf.py <carpeta>/SOLICITUD.md [<carpeta>/EVIDENCIA.md]`.
3. El CEO sube ese `PAQUETE.pdf` a Kimi y pega la respuesta en el chat (o en `RESPUESTA.md`).
4. Claude registra el resultado en la hoja `Gates` del tracker. GO ≥9.0 → construir/mergear.

## 5. Cómo cerrar la sesión
- Actualizar el tracker (`Tareas`: Estado/Fecha/Evidencia; `Gates` si aplica).
- Commit del código + tracker + docs juntos (Conventional Commits).
- Si algo no-obvio y durable se decidió → guardar en memoria y/o en el doc que corresponda.

## 6. Datos y persistencia
- Toda la data en **MongoDB Atlas** (cluster SISMO-V3, base `compas`). Nada efímero.
- Datos reales (montos/nombres) NO van al repo (Ley 1581): el repo guarda el **modelo**, no los datos.
- Migración: **abril-2026 en adelante** (Global66 operativa; Bancolombia se centraliza en sep-2026).
