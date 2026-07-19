# `planning/` — Auditoría adversarial con Kimi (COMPAS)

Esta carpeta contiene los artefactos del **procedimiento de auditoría adversarial con Kimi**,
portado de SISMO-V3. Es el *estado ejecutable* del gate de auditoría; el **contrato del
proyecto sigue viviendo en `docs/`** (PRD, Spec, STACK, PLAN de trabajo) + el tracker
`docs/COMPAS_Control_Desarrollo.xlsx`. No duplicamos aquí el PRD ni el roadmap.

## Qué es y qué no es

- **Kimi = auditor adversarial externo.** Revisa ANTES de todo merge crítico. **NO genera código.**
- No reemplaza al par revisor humano (Iván) ni al CI. Es una capa adicional.
- Regla canónica y umbral: ver `CLAUDE.md` → sección *«Auditoría adversarial con Kimi»*.

## Estructura — UNA carpeta por ronda, autocontenida

```
planning/
├── README.md                     # este archivo
├── TEMPLATES/
│   ├── SOLICITUD-AUDITORIA.md     # plantilla que escribe Claude
│   └── AUDITORIA-KIMI.md          # plantilla de la respuesta de Kimi
└── phases/
    └── <fase>/                    # una carpeta por sprint/sesión crítica
        ├── PLAN.md                # plan de la fase (se audita primero)
        └── auditorias/
            └── <TARGET>-<RONDA>/  # p. ej. PLAN-I, PLAN-R, PR1-I, PR1-R, PR2-I…
                ├── SOLICITUD.md   # la escribe Claude
                ├── EVIDENCIA.md   # solo en PRs de código (diff + tests reales)
                ├── PAQUETE.pdf    # lo genera Claude → ES EL QUE SE SUBE A KIMI
                ├── RESPUESTA.md   # Andrés pega aquí la respuesta de Kimi
                └── CERTIFICADO.md # opcional: cierre/GO aparte
```

- **TARGET:** `PLAN` | `PR1` | `PR2` | `PR3`. **RONDA:** `I` (inicial) → `R` (re-auditoría) → `R2`…
- Todo lo de un intercambio con Kimi vive en la MISMA carpeta: no hay que buscar en dos sitios.

## Ciclo de una auditoría

1. Claude construye (con TDD) o redacta el PLAN.
2. Claude escribe `<carpeta-ronda>/SOLICITUD.md` (+ `EVIDENCIA.md` si es PR) **con evidencia**
   (tests/ruff/build verdes, valores verificados "al peso", puntos a auditar con lupa).
3. Claude genera el paquete:
   `python scripts/generate_kimi_audit_pdf.py <carpeta-ronda>/SOLICITUD.md [<carpeta-ronda>/EVIDENCIA.md]`
   → escribe `<carpeta-ronda>/PAQUETE.pdf`.
4. **Andrés** sube `PAQUETE.pdf` al chat de Kimi y pega la respuesta en `RESPUESTA.md` de esa carpeta.
5. Si nota **≥ 9.0** y sin RECHAZO → merge (con autorización del CEO); se anota en la
   hoja 'Gates' del tracker. Si no → Claude resuelve y abre ronda `R` (nueva subcarpeta).

## Nota

No corremos la suite GSD de Claude Code automáticamente; `planning/` aquí es solo el
soporte del gate de auditoría, no un framework de gestión.
