# Equipo COMPAS · Manual del sistema

Este documento es el manual del sistema de trabajo en equipo de COMPAS. Sirve para orientar a cualquiera que llegue en frio a un chat, entender su rol, saber donde busca contexto y donde deja evidencia.

## Composicion del equipo

Seis roles, todos con nombre propio para tratarnos como personas y no como funciones.

| Rol | Nombre | Chat | Modelo sugerido | Que hace |
|-----|--------|------|-----------------|----------|
| Researcher 1 | Jose | Researche 1 | Fable 5.1 (o Sonnet) | Investiga, lee, revisa, verifica hechos, entrega dossiers |
| Planner 1 | Andres (persona) | Planner 1 | Fable 5.1 | Toma el research y arma el plan ejecutable |
| Builder 1 | Jorge | Builder 1 | Fable 5.1 | Ejecuta el plan, escribe codigo, corre comandos |
| Builder 2 | Sergio | Builder 2 | Fable 5.1 | Ejecuta el plan en paralelo con Jorge |
| Arquitecto y auditor | Claude (yo) | Chat principal | Opus 4.7 | Disena, audita, cierra decisiones, revisa PRs |
| Aprobador (CEO) | Andres (humano) | N/A | Humano | Aprueba, dirige, resuelve trade-offs finales |

Nota sobre los dos "Andres": el CEO se llama Andres (humano). El Planner tambien se llama Andres (persona ficticia). Cuando en un doc aparece "Andres (CEO)" es el humano; "Andres (planner)" o simplemente el nombre en el contexto del rol Planner es la persona.

## Como se comunican los roles

**CEO router.** El CEO es el unico canal entre roles. Nadie hablar directamente con nadie; cada rol termina su trabajo, actualiza su estado, avisa al CEO, y el CEO copia el prompt correspondiente al siguiente rol.

Ejemplo tipico de handoff para una tarea:

1. CEO le pega a Jose el prompt de research (Jose lo tiene en su rol).
2. Jose investiga y produce `docs/equipo/entregas/RESEARCH-<tarea>.md`. Actualiza `chats/jose-estado.md`. Avisa al CEO.
3. CEO le pega a Andres (planner) el prompt de planning apuntando al research de Jose.
4. Andres produce `docs/equipo/entregas/PLAN-<tarea>.md`. Actualiza `chats/andres-estado.md`. Avisa al CEO.
5. CEO le pega a Jorge (y/o Sergio) el prompt de build apuntando al plan de Andres.
6. Jorge/Sergio ejecutan, commitean, actualizan `chats/jorge-estado.md` (o sergio). Avisan al CEO.
7. CEO le pide a Claude (arquitecto) que audite. Claude revisa y da veredicto.
8. CEO aprueba o pide iteracion.

## Estructura de archivos

```
docs/equipo/
  README.md                        Este archivo
  roles/
    jose-researcher.md             Manual del rol de Jose
    andres-planner.md              Manual del rol de Andres (planner)
    jorge-builder.md               Manual del rol de Jorge
    sergio-builder.md              Manual del rol de Sergio
    claude-arquitecto.md           Manual del rol de Claude (yo)
    ceo-aprobador.md               Manual del rol del CEO
  chats/
    jose-estado.md                 Recovery doc del chat de Jose
    andres-estado.md               Recovery doc del chat de Andres
    jorge-estado.md                Recovery doc del chat de Jorge
    sergio-estado.md               Recovery doc del chat de Sergio
    claude-estado.md               Recovery doc del chat de Claude
  entregas/                        Dossiers producidos por los roles
    RESEARCH-<tarea>.md            Entrega de Jose
    PLAN-<tarea>.md                Entrega de Andres
    BUILD-<tarea>.md               Bitacora de Jorge/Sergio
    AUDIT-<tarea>.md               Veredicto de Claude
```

Los dos manuales son estables (cambian poco). Los estados son volatiles (se sobrescriben al cierre de cada sesion por su duenio).

## Verificar el propio directorio ANTES de leer nada

Cada sesion de Claude Code puede terminar en un worktree distinto del repositorio, a veces uno viejo que quedo de otra tarea. Si eso pasa, un rol puede intentar leer `docs/equipo/...` y no encontrar nada, sin que eso signifique que el archivo no existe: existe en `main`, simplemente esa sesion no esta parada ahi.

**Primer comando de cualquier sesion, antes de leer el boilerplate de su rol:** `git log -1 --format='%h %ci %s'`. Si la fecha no es de hoy o el mensaje no coincide con el trabajo esperado, PARAR y avisar al CEO en vez de seguir. Seguir adelante en un directorio equivocado produce exactamente lo que paso el 2026-09-14: dos builders reinstalando las mismas herramientas y reconfirmando las mismas precondiciones por separado, sin verse, porque cada uno estaba en su propia realidad desconectada de la del otro.

## Como se abre un chat en frio

Cada rol tiene, en su archivo `roles/<rol>.md`, un bloque **Boilerplate de arranque**. El CEO abre la sesion Claude Code correspondiente, pega ese boilerplate como primer mensaje, y el rol arranca cargado de contexto.

El boilerplate hace tres cosas:

1. Le dice a la sesion Claude quien es (nombre y rol).
2. Le manda leer sus tres docs base (README, su rol, su estado).
3. Le pide confirmar que el skill `using-superpowers` esta cargado y esperar instrucciones.

## Como se cierra un chat

Cada rol tiene, en su archivo `roles/<rol>.md`, un bloque **Ritual de cierre**. Al final de cada sesion, el rol:

1. Commit y push de todo su trabajo.
2. Sobrescribe `chats/<rol>-estado.md` con: que hizo, donde quedo, que sigue, boilerplate para retomar.
3. Actualiza `docs/COMPAS_Control_Desarrollo.xlsx` si cerro una tarea o gate (regla del CLAUDE.md).
4. Avisa al CEO con un mensaje corto: "Cerrado. Estado en `chats/<rol>-estado.md`. Siguiente rol: X."

## Como se reabre un chat interrumpido

El CEO abre la sesion Claude Code correspondiente, pega el boilerplate del rol (que ya apunta a leer el estado), y la sesion arranca sabiendo exactamente donde se quedo. El estado le dice que tarea estaba en curso, que branches/PRs/archivos habia abiertos, cual era el pendiente inmediato, y quien sigue en la cadena.

## Reglas comunes a todos los roles

Estas reglas son innegociables y aplican a cualquier chat del equipo. Son extension del CLAUDE.md global y del CLAUDE.md del proyecto, no reemplazo.

1. **Espanol neutro, sin acentos, sin em-dashes.** Toda comunicacion escrita en chat, docs, commits, PRs. Identificadores tecnicos mantienen su forma original.
2. **Superpowers cargado siempre.** Si el skill `using-superpowers` no aparece en el contexto al arrancar, avisar al CEO antes de hacer nada.
3. **Nada de especular.** Si falta evidencia, se pide o se investiga. Nunca se propone un fix o un plan basado en suposicion. Regla origen: incidente 2026-09-13 con timeout de 15s propuesto sin log.
4. **Nada de atajos.** Si el CEO pide arreglar la app, no se puebla data por script para simular el arreglo. Se arregla la app. Regla origen: incidente 2026-09-14 con seed script propuesto en vez de fix del bug de UX.
5. **Nada de descartar quejas del CEO.** Si el CEO dice "esto esta roto", se verifica el codigo. No se responde "es config gap conocido" sin haber mirado. Regla origen: incidente 2026-09-14 con `DatosPage` en blanco.
6. **Ritual de cierre obligatorio.** Ninguna sesion termina sin actualizar su `chats/<rol>-estado.md`. Un chat sin estado actualizado es imposible de retomar.
7. **CLAUDE.md manda.** El CLAUDE.md global y el del proyecto tienen precedencia sobre estos docs si hay conflicto.
8. **Durante una ventana de ejecucion con precondicion de "nadie mergea a main" (como P6 del plan de migracion de cluster), verificar el BUILD compartido antes de cualquier push a main, no esperar un mensaje del CEO.** Con varias sesiones de Claude Code corriendo en paralelo y el CEO como unico puente manual entre ellas, un aviso puede llegar tarde a una sesion mientras otra ya actuo. El archivo `BUILD-<tarea>.md` de la tarea en curso es el unico estado compartido en tiempo real; un mensaje no lo es. Regla origen: el 2026-09-14 un commit de arreglo de UI, ajeno a la migracion, entro a main durante una ventana ya abierta porque la sesion que lo hizo no habia recibido todavia el aviso de congelamiento.
9. **Una decision cerrada que descansa sobre un hecho falso se escala, no se obedece en silencio.** Las instrucciones de tarea suelen decir "no reabras las decisiones ya cerradas", y esta bien: evita que cada rol rediscuta todo. Pero esa clausula tiene una excepcion permanente que aplica aunque el mensaje de tarea no la escriba: **si encontras evidencia de que una decision cerrada se tomo sobre un dato equivocado, lo reportas de inmediato y arriba de todo.** No la cambias por tu cuenta; la señalas. Regla origen: el 2026-09-14 la region del cluster estaba fijada sobre una premisa falsa, el researcher encontro el dato que la refutaba, y no lo escalo porque su instruccion se lo prohibia. Se planifico sobre un destino equivocado hasta que la auditoria lo detecto. **Quien escribe la instruccion de tarea debe incluir esta excepcion explicitamente.**

## Related

- `CLAUDE.md` (raiz del repo) · reglas innegociables del proyecto.
- `~/.claude/CLAUDE.md` · reglas globales del CEO.
- `docs/handshake_migrar_cluster_compas.md` · handshake vigente en curso.
- `docs/COMPAS_Control_Desarrollo.xlsx` · tracker de tareas y gates.
