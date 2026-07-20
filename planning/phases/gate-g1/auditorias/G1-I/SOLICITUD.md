# SOLICITUD DE AUDITORÍA — Gate G1 (final de Sprint 0) · G1-I

**Para:** Kimi · **Umbral:** ≥ 9.0 · **Fecha:** _(al disparar)_
**Ámbito:** Gate G1 BLOQUEANTE — checklist de seguridad completo de cierre del Sprint 0.
**Aprobación (CR-003):** CEO Andrés (decisión) + esta auditoría adversarial Kimi (evidencia).
**Checklist con evidencias:** `planning/phases/gate-g1/G1-CHECKLIST.md`
**Docs:** RUNBOOK §9/§0 · PLAN §Gate G1 · DoD #6/#8/#11/#12 · CR-003.

## Qué se somete
El cierre de seguridad de Fase 0–1, acumulado y ya auditado por partes:
- **Auth + RBAC + audit** (Sesión 2): 3/3 PRs GO (PR-1 9.2, PR-2 9.3, PR-3 9.5).
- **MFA** (Sprint 0b PR-2): R-PR2 GO → **DoD #11**.
- **Cabeceras** (Sprint 0b PR-3): 9.2 GO → **DoD #12**.
- **CI/CD** (Sesión 3, PR #6): PLAN 9.1 GO; código con `backend-real-mongo` bloqueante
  (inmutabilidad de `audit_log` real, DoD #6), pip-audit, gitleaks, Dependabot → **DoD #8**.
- **Gobernanza:** CR-003 (aprobador ≠ ejecutor), break-glass y acceso a secretos nombrados (§0).

## Puntos a auditar con lupa (cierre del Sprint 0)
1. ¿El conjunto satisface el checklist de G1 sin huecos (auth endurecida, audit inmutable
   verificado en CI real, MFA, cabeceras, escaneo bloqueante)?
2. ¿La evidencia operacional (bloque C: staging arriba, bloqueo de prod, PR-con-secreto
   rechazado, cabeceras vivas, CRR) es suficiente y real?
3. ¿La resolución de A-01 vía CR-003 (CEO + Kimi) es un mecanismo válido y está registrada?
4. ¿Queda algún control de Fase 0–1 sin cerrar que NO deba diferirse (k6/Playwright sí se difieren)?

## Evidencia (se adjunta al disparar)
- `G1-CHECKLIST.md` con cada ítem A/B/C mapeado a su gate/commit/tracker.
- **Run verde de GitHub Actions** del PR #6 (los 5 jobs, incl. `backend-real-mongo`).
- Certificados Kimi previos (RESPUESTA de cada ronda) y hoja 'Gates' del tracker.
- Evidencia operacional del bloque C (capturas/salidas que aporta el CEO).

## Estado al momento de redactar (pre-disparo)
Bloque A: A1–A4, A7 ✅ · A5/A6 🟡 (pendiente run verde de Actions — incidente GitHub en curso).
Bloque B ✅. Bloque C ⏳ (operacional del CEO). **No disparar hasta A5/A6 verdes + bloque C con evidencia.**

## Pregunta al auditor
¿El Sprint 0 cierra con la seguridad de Fase 0–1 completa y verificada (no solo declarada),
apto para GO del Gate G1 y para avanzar a Sprint 1 (parsers/cargas)?
