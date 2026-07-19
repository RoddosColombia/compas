# AUDITORÍA KIMI — sprint0b-dominio-mfa · I-PLAN

**Veredicto:** GO CONDICIONADO para construir — **8.7 / 10** (umbral ≥ 9.0)
**Fecha:** 2026-07-19 · **Nivel:** PLAN (pre-código) · **Auditor:** Kimi (adversarial externo)

## Resumen
Desglose PR-1/PR-2/PR-3 correcto, fiel al baseline y con buena disciplina de scope.
Autoriza construir YA; condición: resolver el mecanismo del Gate G1 **antes de llegar a
G1** (A-01), más 4 precisiones de diseño (M-01..M-04) al PLAN/diseño de cada PR.
Estimación con todo aplicado: **≥ 9.3**.

## Micro-ítems de arrastre — CERRADOS por referencia
- **B-1** cookie en scrubber Sentry (`app/main.py` c34f9c9 + `tests/test_sentry_scrub.py`) ✔
- **P-1** `tz_aware=True` (`app/db/mongo.py:27`) ✔
- **P-2** tests validadores audit (`tests/test_audit_models.py` 5d5ae41) ✔

## A-01 (Alta · decisión de gobernanza) — mecanismo del Gate G1
"Señalada, no bloqueada" no es un mecanismo. Andrés es co-ejecutor → no puede aprobar
solo. Corrección (una de dos, antes de la evaluación de G1 — NO bloquea el arranque):
- **(a) Preferida:** Iván aprueba G1 → hacer **EXT-03** (cuenta de Iván + colaborador
  repo + reviewer de production) prerrequisito duro de G1. Kimi queda como evidencia
  adicional del checklist, no como aprobador.
- **(b) Alternativa:** CR formal que cambia la regla de G1 a "Kimi adversarial
  (evidencia) + CEO Andrés (aprobación)", con justificación explícita reconociendo que
  debilita el segundo-par-humano (mitigación bus-factor). Sin CR, "Kimi + Andrés" NO es
  válido como mecanismo.

## Medias (aplicar al PLAN / diseño de PR)
- **M-01** MFA sin diseño: añadir bloque de 1 pág. en PR-2 con 6 puntos (enrolamiento
  TOTP protegido por contraseña+step-up; semántica "MFA reciente" = claim `mfa_at` +
  ventana; códigos de respaldo bcrypt un-solo-uso; throttle en `/auth/mfa/verify`
  IP+cuenta; protección `mfa_secret` en reposo; reset MFA bump `token_version`). Tests:
  TOTP inválido repetido→throttle; respaldo un-solo-uso; step-up expirado→403.
- **M-02** Semilla rubros: declarar que incluye las ~30 categorías del Excel congelado
  (con `tipo_flujo` y `orden`), o registrar por qué se difiere y dónde se cargan.
- **M-03** `Configuracion.valor` polimórfico: representación tipada por clave
  (`valor_decimal`/`valor_fecha`/`valor_json`); umbrales COP como `Decimal`.
- **M-04** init_beanie: lista explícita de Documents (Rubro, MesControl, Configuracion,
  User, RefreshSession) y `AuditLog` FUERA (conexión dedicada).

## Bajas
- **B-01** Cabeceras: aclarar si PR-3 cubre la SPA (`vercel.json`) o solo la API.
- **B-02** G1 depende de Sesión 3 (pip-audit/gitleaks + mongod real) → prerrequisito duro.
- **B-03** Break-glass: custodio nombrado antes de G1 (S0-07 pendiente).

## Camino
Decisión A-01 (a/b) → aplicar M-01..M-04 + B-01..B-03 al PLAN → construir PR-1 → gate
Kimi → PR-2 → gate → PR-3 → G1. Re-presentar PLAN solo si se elige (b).
