# CR-003 — Mecanismo de aprobación del Gate G1 (aprobador = CEO + evidencia Kimi)

- **Solicitante:** CEO (Andrés San Juan)
- **Fecha:** 2026-07-19
- **Estado:** Aprobado por el CEO (autoridad única del proyecto)
- **Sprint destino:** Sprint 0b (Gate G1) · re-baseline v1.1.3
- **Origen:** Hallazgo A-01 de la Auditoría Kimi I-PLAN de Sprint 0b (8.7/10 GO CONDICIONADO).

## Contexto
El baseline certificado (PLAN v1.1.2 §4, RUNBOOK-INFRA §0) define el **Gate G1** (fin de
Sprint 0b, BLOQUEANTE) con un **aprobador distinto del ejecutor**, asignado nominalmente a
**Iván Echeverri** como "par revisor / required reviewer de producción" (mitigación de
bus-factor F-48).

En la realidad operativa de RODDOS, **Iván no revisa ni aprueba nada**: la única autoridad
que autoriza, instruye y aprueba en COMPAS es el **CEO (Andrés)**. Andrés es además
co-ejecutor del desarrollo, por lo que "aprobador ≠ ejecutor" no puede satisfacerse con un
segundo revisor humano.

## Cambio
Se modifica la regla de aprobación del **Gate G1** (y, por extensión, de los gates que el
baseline asignaba a "par revisor humano ≠ ejecutor"):

> **Aprobación de G1 = CEO Andrés (decisión) + Auditoría adversarial Kimi ≥ 9.0 (evidencia
> independiente).** El auditor externo Kimi actúa como el control independiente del ejecutor
> (no escribe código; ver `procedimiento-kimi`); el CEO firma el gate con esa evidencia.

- El rol de Iván como aprobador/required reviewer queda **derogado** (era nominal).
- Se mantiene el resto del checklist de G1 sin cambios (auth endurecida, audit inmutable en
  CI, MFA activo, cabeceras, CI con pip-audit/gitleaks + mongod real, break-glass).

## Impacto declarado
- **Riesgo reconocido:** debilita la mitigación de bus-factor (segundo par humano). Se acepta
  explícitamente por decisión del CEO; el control adversarial Kimi lo compensa parcialmente.
- **Costo/plazo:** ninguno.
- **Docs a reconciliar en re-baseline v1.1.3:** PLAN §4 (Gates), RUNBOOK-INFRA §0/§9.
- **Tracker:** hoja Gates, fila G1 — Aprobador pasa de "Iván (≠ ejecutor)" a
  "CEO Andrés + Kimi (evidencia)".
