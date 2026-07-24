# backend/app/auth/permissions.py
"""Config ÚNICO de permisos (RBAC) ≡ matriz Spec §4.1 + autoridad §2.4.

Fuente única de verdad: el navbar del frontend se derivará de aquí (GET
/auth/capabilities), y los endpoints de negocio usan `require_permission(cap)`.
`require_role` queda SOLO para administración de identidad (/users); prohibido en
negocio (Kimi H-1). La §2.4 se codifica como capacidades `ciclo:*` y MANDA sobre
cualquier otra redacción. `ciclo:reabrir` y `ciclo:config` exigirán step-up MFA
(Sprint 0b)."""

from app.auth.roles import Role

_TODOS = frozenset(Role)

PERMISSIONS: dict[str, frozenset[Role]] = {
    # ── Spec §4.1 (matriz permiso × endpoint) ──
    "dashboard:leer": _TODOS,
    "export:reportes": frozenset({Role.financiero, Role.directivo, Role.admin}),
    "archivos:descargar": frozenset({Role.financiero, Role.admin}),
    "cargas:gestionar": frozenset({Role.financiero, Role.admin}),
    "presupuesto:acotar": frozenset({Role.financiero, Role.directivo, Role.admin}),
    "facturas_emitidas:gestionar": frozenset({Role.financiero, Role.admin}),
    "evidencia:ver": frozenset({Role.financiero, Role.admin}),
    "capacidad_pago:ver": frozenset({Role.financiero, Role.directivo, Role.admin}),
    # ── CR-S4 (C1 categorías administrables, GO Kimi PLAN-I 9.2) ──
    "rubros:gestionar": frozenset({Role.financiero, Role.admin}),
    # ── CR-S5 (C3 auto-clasificación, GO Kimi PLAN-I 9.3) ──
    "reglas:gestionar": frozenset({Role.financiero, Role.admin}),
    # ── CR-S6 (C4 ajuste diario de caja, GO Kimi PLAN-I 9.3) ──
    "caja:reportar": frozenset({Role.financiero, Role.admin}),
    # ── CR-S7 (C9 pagos de la semana, GO CEO 2026-07-23) ──
    "pagos:gestionar": frozenset({Role.financiero, Role.admin}),
    # ── CR-COCK (C7 motor de proyección: modelos de moto + parámetros) ──
    "proyeccion:gestionar": frozenset({Role.financiero, Role.admin}),
    # ── Spec §2.4 (autoridad del ciclo mensual — manda sobre §4.1) ──
    "ciclo:abrir": frozenset({Role.financiero, Role.directivo, Role.admin}),
    "ciclo:proponer": frozenset({Role.financiero, Role.directivo, Role.admin}),
    "ciclo:aprobar": frozenset({Role.admin}),  # aprobador formal único
    "ciclo:cierre_operativo": frozenset({Role.financiero, Role.admin}),
    "ciclo:confirmar_cierre": frozenset({Role.admin}),
    "ciclo:reabrir": frozenset({Role.admin}),  # + step-up MFA (0b)
    "ciclo:config": frozenset({Role.admin}),  # + step-up MFA (0b)
}

CAPABILITIES: frozenset[str] = frozenset(PERMISSIONS)


def has_permission(rol: Role, capacidad: str) -> bool:
    return rol in PERMISSIONS.get(capacidad, frozenset())


def capabilities_for(rol: Role) -> list[str]:
    """Capacidades efectivas del rol (ordenadas). Lo consume el navbar (M13.1 #6:
    prohibido mapear rol→ítems en el frontend)."""
    return sorted(cap for cap, roles in PERMISSIONS.items() if rol in roles)
