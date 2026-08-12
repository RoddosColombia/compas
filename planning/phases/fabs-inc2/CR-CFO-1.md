# CR-CFO-1 — Eventos de auditoría de FABS (agente CFO)

- **Fecha:** 2026-08-11 · **GO:** CEO (gate-waiver inc2; Kimi retroactivo con el paquete de inc2)
- **Regla 11:** el catálogo de eventos es cerrado; este CR lo amplía 62 → 64.

## Eventos nuevos
- `cfo.consulta` — se emite al recibir una pregunta para FABS. `entidad="cfo"`,
  `actor_id`=usuario autenticado real, `metadata={pregunta, canal:"api"}`.
- `cfo.respuesta` — se emite tras responder. `metadata={abstuvo, motivo, conceptos_usados,
  cifras:[{valor,unidad,evidencia}], uso:{modelo,tokens_in,tokens_out,iteraciones}}`.
  La **abstención** es un `cfo.respuesta` con `abstuvo=true` (no hay evento propio).

## Política de fallo (O1)
Una consulta a FABS es **lectura** (no mueve plata). Si la escritura de auditoría falla,
se registra `logger.error`+Sentry y **se continúa** (rama "eventos no críticos" de
`emit_audit`). `cfo.consulta` se emite ANTES de responder (rastro de la pregunta aun si el
loop falla).

## Por qué es crítico / gate
FABS lee y narra cifras de plata para decisiones. El rastro forense de qué preguntó cada
usuario y qué respondió FABS (con qué evidencia) es requisito del sistema.
