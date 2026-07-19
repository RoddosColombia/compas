# `planning/` — Auditoría adversarial con Kimi (COMPAS)

Esta carpeta contiene los artefactos del **procedimiento de auditoría adversarial con Kimi**,
portado de SISMO-V3. Es el *estado ejecutable* del gate de auditoría; el **contrato del
proyecto sigue viviendo en `docs/`** (PRD, Spec, STACK, PLAN de trabajo) + el tracker
`docs/COMPAS_Control_Desarrollo.xlsx`. No duplicamos aquí el PRD ni el roadmap.

## Qué es y qué no es

- **Kimi = auditor adversarial externo.** Revisa ANTES de todo merge crítico. **NO genera código.**
- No reemplaza al par revisor humano (Iván) ni al CI. Es una capa adicional.
- Regla canónica y umbral: ver `CLAUDE.md` → sección *«Auditoría adversarial con Kimi»*.

## Estructura

```
planning/
├── README.md                     # este archivo
├── TEMPLATES/
│   ├── SOLICITUD-AUDITORIA.md     # plantilla que escribe Claude
│   └── AUDITORIA-KIMI.md          # plantilla donde Andrés pega la respuesta de Kimi
└── phases/
    └── <fase>/                    # una carpeta por sprint/sesión crítica
        ├── PLAN.md                        # plan de la fase (se audita primero)
        ├── SOLICITUD-AUDITORIA-<ronda>[-PR<N>].md
        └── AUDITORIA-KIMI-<ronda>[-PR<N>].md
```

- **Rondas:** `I` (inicial) → `R` (re-auditoría tras resolver) → `R…B` si hace falta otra vuelta.
- **Niveles:** auditoría de **PLAN** (antes de construir) y de **PR** (implementación).

## Ciclo de una auditoría

1. Claude construye (con TDD) o redacta el PLAN.
2. Claude escribe `SOLICITUD-AUDITORIA-*.md` **con evidencia** (tests/ruff/build verdes,
   valores verificados "al peso", puntos a auditar con lupa).
3. Claude genera el PDF: `python scripts/generate_kimi_audit_pdf.py <ruta-solicitud>`
   → `docs/audits/<nombre>.pdf`.
4. **Andrés** sube el PDF al chat de Kimi y pega la respuesta en `AUDITORIA-KIMI-*.md`.
5. Si nota **≥ 9.0** y sin RECHAZO → merge (con autorización del CEO); se anota en la
   hoja 'Gates' del tracker. Si no → Claude resuelve y abre ronda `R`.

## Nota

No corremos la suite GSD de Claude Code automáticamente; `planning/` aquí es solo el
soporte del gate de auditoría, no un framework de gestión.
