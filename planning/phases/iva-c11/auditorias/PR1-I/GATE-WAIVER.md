# GATE-WAIVER — PR1 (#46, E2 backend) · iva-c11

**Fecha:** 2026-07-30 · **Autoriza:** Andrés San Juan (CEO) — instrucción directa "mergea".
**Umbral formal:** AUDITORIA-KIMI ≥ 9.0 (PR crítico: parsers/PDF + RBAC/PII + migración real).

## Situación

Kimi **no** ha emitido veredicto para este PR: el `PAQUETE.pdf` de `PR1-I` está listo para
subir, pero **no hay `RESPUESTA.md`**. El CEO autorizó el merge por GO directo, bajo el
patrón ya establecido en este proyecto (D2 backend #43 se mergeó igual): **con Kimi ausente,
el GO del CEO por fase habilita mergear, registrando el waiver y dejando la auditoría Kimi
como RETROACTIVA.**

**Este documento NO afirma que Kimi aprobó.** Afirma que el CEO decidió mergear sin esperar
el veredicto, asumiendo el riesgo, con auditoría retroactiva pendiente.

## Base sobre la que se mergea (evidencia propia, no Kimi)

- Suite completa **728 passed / 62 skipped / 0 failed**.
- CI verde tras corregir los dos rojos reales (formato ruff + CVE pdfminer.six → pdfplumber
  0.11.9). `pip-audit`: sin vulnerabilidades. `gitleaks`: verde.
- `motor.py` **cero diffs**; `proyeccion/` solo el `_iva_plan` del CR-E2-COMPUERTA.
- **A14 en PRODUCCIÓN** (no solo tests): foto de `GET /api/v1/proyeccion` pre-deploy tomada;
  se compara bit a bit contra la post-deploy (ver `foto_proyeccion_*_deploy.sha256` y el
  reporte del diff). Migración ya corrida en prod (idempotente), compuerta sembrada apagada,
  colección de facturas vacía.

## Pendiente (no bloquea el merge; sí el cierre del gate)

1. Subir `PAQUETE.pdf` a Kimi y pegar el veredicto en `RESPUESTA.md`.
2. Si Kimi < 9.0 o RECHAZO: corregir hacia adelante (el merge fue a `main` = staging;
   producción endurecida es go-live).
3. Anotar el resultado en la hoja 'Gates' del tracker (`docs/COMPAS_Control_Desarrollo.xlsx`).
