# Rol · Andres (CEO, Aprobador)

## Mision

Dirigir el equipo. Aprobar o rechazar recomendaciones. Ser el unico canal de comunicacion entre roles. Resolver trade-offs finales. Cortar cuando algo se desvia.

## Que hace

- **Router de handoffs.** Copia el prompt de un rol al siguiente cuando el trabajo esta listo. Sin CEO, nadie habla con nadie.
- **Aprobaciones.** Recibe recomendaciones de Claude (auditorias, veredictos), decisiones planteadas por Andres (planner) o Jose (research), y aprueba, rechaza o pide iteracion.
- **Prioridades.** Decide en que trabaja el equipo, en que orden, con que urgencia.
- **Corte y direccion.** Si un rol se desvia, atajа o especula, el CEO lo corrige de inmediato y actualiza memoria si es un patron.

## Que NO hace

- No escribe codigo ni corre comandos contra sistemas productivos salvo cuando el paso del plan lo asigna explicitamente al CEO (raro).
- No hace research en profundidad (Jose lo hace).
- No planifica en detalle (Andres planner lo hace).
- No audita en detalle (Claude lo hace).

## Con quien se comunica

- Con todos. El CEO es el hub del sistema.

## Rutina tipica de una tarea

1. **CEO tiene una idea o un pedido.** Habla con Claude (arquitecto). Si es idea grande, Claude corre `handshake`. Si es tactica, saltan a research directo.
2. **CEO manda a Jose.** Copia el boilerplate de arranque de Jose (si es chat nuevo) o un mensaje corto (si el chat ya vive) con el pedido de research. Ejemplo: "Investiga X. Contexto: handshake en docs/handshake_X.md. Dossier en docs/equipo/entregas/RESEARCH-X.md. Avisame cuando termines."
3. **Jose entrega.** CEO revisa el dossier. Si es debil, pide iteracion. Si es solido, pasa a Andres (planner).
4. **CEO manda a Andres (planner).** "Aca esta el dossier de Jose en docs/equipo/entregas/RESEARCH-X.md. Armame el plan ejecutable en docs/equipo/entregas/PLAN-X.md. Divide entre Jorge y Sergio si aplica."
5. **Andres entrega el plan.** CEO puede pedirle a Claude que audite el plan antes de ejecutar. Grill opcional.
6. **CEO manda a Jorge y/o Sergio.** "Aca esta el plan en docs/equipo/entregas/PLAN-X.md. Tus pasos son los marcados como owner: Jorge. Ejecuta y deja evidencia en BUILD-X.md."
7. **Jorge/Sergio ejecutan.** Avisan cuando terminan cada paso relevante o al cierre.
8. **CEO manda a Claude para auditar.** "Audita el build de X. Bitacora en docs/equipo/entregas/BUILD-X.md. Veredicto en AUDIT-X.md."
9. **Claude entrega veredicto.** CEO aprueba (o pide fix). Merge/deploy.

## Ritual de cierre del CEO

El CEO no cierra sesion como los demas, porque su sesion no es un chat de Claude. Pero al final de una tarea:

1. Verificar que el tracker `docs/COMPAS_Control_Desarrollo.xlsx` refleja el estado real.
2. Verificar que cada rol involucrado actualizo su `chats/<rol>-estado.md`.
3. Verificar que hay AUDIT si la tarea era critica.

## Boilerplate de arranque

No aplica. El CEO no arranca un chat Claude Code para su rol.
