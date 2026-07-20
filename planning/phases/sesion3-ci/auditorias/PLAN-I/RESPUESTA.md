# RESPUESTA KIMI — sesion3-ci · PLAN-I

**Auditoría I-PLAN · Sesión 3: CI (prerrequisito duro del Gate G1)**
**GO — 9.1 / 10** (umbral ≥ 9.0), con 2 precisiones incorporadas al plan · 2026-07-19

Plan de CI correcto y estándar; cubre lo que exige G1 (audit inmutable en CI + escaneo) y
difiere bien k6 (DoD #9) y Playwright. A-01 resuelta por CR-003. **Construir ya.**

## Precisiones incorporadas al PLAN
- **P-1 — implementar (no solo ejecutar) los `@requires_real_mongo`.** Añadida §1.b con la
  lista exacta: 3 inmutabilidad audit (negativo update/remove + positivo insert/find), 1 índices
  auth, 1 concurrencia; los 3 de dominio ya son reales (PR-1). **Dedup parcial (Sprint 1):
  se EXCLUYE del job** (placeholder → `skip` marcado, no fallo) hasta que exista `Transaccion`.
- **P-2 — required checks explícitos** en RUNBOOK §9: `backend`, **`backend-real-mongo`**
  (bloqueante), `frontend`, `pip-audit`, `gitleaks`.

## Recomendaciones menores (incorporadas §4)
Actions pineadas a SHA · pip-audit con proceso de excepciones · cobertura solo-reporte ·
`COMPAS_TEST_MONGO_URI` construido en el job · `wait-for-mongo` antes del script de rol.

## Puntos de lupa — respuestas de Kimi
Inmutabilidad en CI: enfoque correcto (mongo:7 + auth + `create_audit_role.py` + test negativo
y positivo); Atlas free / memory-server son peores. Cobertura de los marker: completa con P-1.
gitleaks: bien si la allowlist son huellas de fixtures anonimizados (no rutas amplias). k6/PW:
correcto diferirlos (no son de G1).

**Siguiente:** construir el PR de CI → su gate de código (Kimi ≥ 9) → paquete del Gate G1.
