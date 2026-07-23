# backend/tests/test_rbac_permissions.py
"""Config único de permisos ≡ matriz Spec §4.1 + autoridad §2.4 (PR-3).

Test de completitud TRIPLE (Kimi M-10):
(a) toda capacidad usada tiene roles no vacíos; (b) el config ≡ la matriz canónica
congelada aquí; (c) sin capacidades huérfanas ni roles que no aparezcan en ninguna."""

from app.auth import permissions as perms
from app.auth.roles import Role

# Matriz canónica CONGELADA (Spec §4.1 + §2.4). Si el código cambia, este test cae:
# es la fuente de verdad del test contra el config de la app.
CANONICA: dict[str, set[Role]] = {
    # §4.1
    "dashboard:leer": {Role.consulta, Role.financiero, Role.directivo, Role.admin},
    "export:reportes": {Role.financiero, Role.directivo, Role.admin},
    "archivos:descargar": {Role.financiero, Role.admin},
    "cargas:gestionar": {Role.financiero, Role.admin},
    "presupuesto:acotar": {Role.financiero, Role.directivo, Role.admin},
    "facturas_emitidas:gestionar": {Role.financiero, Role.admin},
    "evidencia:ver": {Role.financiero, Role.admin},
    "capacidad_pago:ver": {Role.financiero, Role.directivo, Role.admin},
    # CR-S4 (C1 categorías administrables): gestión del catálogo de rubros
    "rubros:gestionar": {Role.financiero, Role.admin},
    # CR-S5 (C3 auto-clasificación): gestión de reglas de clasificación
    "reglas:gestionar": {Role.financiero, Role.admin},
    # §2.4 — autoridad del ciclo (manda sobre §4.1)
    "ciclo:abrir": {Role.financiero, Role.directivo, Role.admin},
    "ciclo:proponer": {Role.financiero, Role.directivo, Role.admin},
    "ciclo:aprobar": {Role.admin},
    "ciclo:cierre_operativo": {Role.financiero, Role.admin},
    "ciclo:confirmar_cierre": {Role.admin},
    "ciclo:reabrir": {Role.admin},  # + step-up MFA (Sprint 0b)
    "ciclo:config": {Role.admin},  # + step-up MFA (Sprint 0b)
}


def test_config_igual_a_la_matriz_canonica():
    # (b)
    actual = {cap: set(roles) for cap, roles in perms.PERMISSIONS.items()}
    assert actual == CANONICA


def test_ninguna_capacidad_sin_roles():
    # (a)
    for cap, roles in perms.PERMISSIONS.items():
        assert roles, f"capacidad huérfana sin roles: {cap}"


def test_todos_los_roles_aparecen():
    # (c)
    cubiertos = {r for roles in perms.PERMISSIONS.values() for r in roles}
    assert cubiertos == set(Role)


def test_consulta_no_puede_exportar():
    # DoD #1: export denegado a Consulta.
    assert not perms.has_permission(Role.consulta, "export:reportes")
    assert perms.has_permission(Role.financiero, "export:reportes")


def test_aprobar_solo_admin():
    # §2.4: solo Admin aprueba (Directivo acota, no aprueba).
    assert perms.has_permission(Role.admin, "ciclo:aprobar")
    assert not perms.has_permission(Role.directivo, "ciclo:aprobar")
    assert not perms.has_permission(Role.financiero, "ciclo:aprobar")


def test_capabilities_for_consulta_solo_lectura():
    caps = perms.capabilities_for(Role.consulta)
    assert caps == ["dashboard:leer"]


def test_capacidad_desconocida_es_falsa():
    assert not perms.has_permission(Role.admin, "capacidad.inventada")


def test_toda_capacidad_usada_en_decoradores_existe_en_config():
    # (a) guardián: ninguna require_permission("X") con X fuera del config (drift).
    import pathlib
    import re

    app_dir = pathlib.Path(__file__).resolve().parents[1] / "app"
    usados: set[str] = set()
    for py in app_dir.rglob("*.py"):
        texto = py.read_text(encoding="utf-8")
        usados.update(re.findall(r'require_permission\(\s*["\']([^"\']+)["\']', texto))
    faltan = usados - set(perms.CAPABILITIES)
    assert not faltan, f"capacidades usadas sin definir en el config: {faltan}"
