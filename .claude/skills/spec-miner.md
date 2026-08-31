---
name: spec-miner
description: Mapa del código antes de proponer diseño. Úsala cuando el CEO pide una feature nueva, un fix no trivial, o cuando el brainstorming necesita evidencia real del repo. Sin mapa no hay diseño.
---

# spec-miner · AND-3 · COMPAS 2.0

**Qué es:** el protocolo que fija cómo Claude explora el código ANTES de proponer
un diseño o escribir tests. Un error del método es proponer basado en intuición
del nombre de una función; el remedio es leer el código real y cruzarlo con las
reglas de `CLAUDE.md`.

## Cuándo se dispara

- El CEO pide una **feature nueva** que toca módulos que Claude no dominó
  todavía esta sesión.
- El CEO pide un **fix no trivial** — típicamente uno que reveló un test
  fallido, una queja del usuario, o un hallazgo de auditoría (Kimi).
- Antes de decidir una **rebanada mínima** grande (patrón usado en RV-V2 r1..r3
  y en FABS inc4 r1..r4).

**No aplica** a: cambios de una línea, renames, docs sin código, o cuando el
mapa ya está fresco en la memoria de la sesión.

## Protocolo (5 pasos, no negociables)

1. **Enuncia el problema en 1 oración** — el propio Claude, no citando al CEO.
   Si no puedes cerrarla, la petición no está clara y el CEO decide antes de
   seguir.

2. **Lista 2–3 enfoques con sus trade-offs** — máximo 3 líneas por enfoque.
   Los enfoques deben ser sustancialmente distintos, no la misma idea con dos
   nombres. Cita reglas de `CLAUDE.md` que aplican a cada uno.

3. **Elige el más simple que resuelva el problema real** — no el más elegante
   ni el más extensible. Regla del CEO: sobre-diseñar es la falla número 1 del
   método.

4. **Mapa del código con evidencia real** — antes de escribir cualquier línea,
   busca (`Grep`/`Read`) las 3–5 piezas del repo que la feature toca. Cita
   `archivo.py:línea` para cada una. Un mapa que dice «probablemente hay algo
   en `service.py`» no cuenta; solo cuenta el que dice «en `service.py:627`
   `_resultado_con` acepta `unidades_extra` desde …».

5. **Solo entonces**, escribe el test (TDD si aplica) y el código mínimo que
   pasa.

## Anti-patrones

- **Adivinar la firma** de una función que existe (siempre `Read`, nunca
  «probablemente recibe …»).
- **Proponer un endpoint nuevo** sin haber leído los existentes del área
  (viola el patrón de contrato).
- **Escribir código antes del mapa** — un fix rápido sin mapa suele reintroducir
  el bug que causó el fix.
- **Saltarse el paso 4 porque «ya sé»** — la memoria de sesión drifta; si el
  código cambió en un merge reciente, el mapa hay que hacerlo de nuevo.

## Composición con otras skills

- Después de spec-miner, casi siempre viene **tdd-guide** (escribir el test
  primero). Ver `.claude/skills/tdd-guide.md`.
- Si la feature toca el motor (`backend/app/proyeccion/motor.py`), spec-miner
  DEBE cerrar con la afirmación explícita «motor cero diffs» o proponer un
  gate `motor-parity-reviewed` (regla vigente desde F0-2).
