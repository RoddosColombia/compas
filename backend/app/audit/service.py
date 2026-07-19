# backend/app/audit/service.py
"""emit_audit — escritura append-only por la conexión DEDICADA de auditoría.

Regla 4 / DoD #6: la inmutabilidad se impone por privilegios de BD. Las escrituras
van por `compas_audit` (rol `audit_writer` = insert+find), una SEGUNDA cadena de
conexión (`MONGODB_URI_AUDIT`) a la MISMA database `compas` — NO una db separada
(dejaría audit_log fuera del dump/restore/archivado). El usuario general de la app
no tiene update/remove sobre `audit_log`.

En la app real, `configure_audit` se llama en el lifespan con el cliente de auditoría;
en tests se inyecta un cliente mongomock."""

from typing import Any

from app.audit.events import AuditEvento
from app.audit.models import AuditLog
from app.core.time import now_utc

_audit_collection: Any = None


def configure_audit(client: Any, db_name: str = "compas") -> None:
    """Fija la colección `audit_log` sobre la conexión dedicada de auditoría."""
    global _audit_collection
    _audit_collection = client[db_name]["audit_log"]


def reset_audit() -> None:
    """Resetea la configuración (para tests)."""
    global _audit_collection
    _audit_collection = None


async def emit_audit(
    evento: AuditEvento | str,
    entidad: str,
    entidad_id: str | None = None,
    actor_id: str | None = None,
    metadata: dict | None = None,
) -> AuditLog:
    """Inserta un evento en `audit_log`. Valida contra el catálogo cerrado (30);
    `AuditEvento(evento)` lanza ValueError si el evento no existe (regla 11).

    Política de fallo ante error de BD (Kimi O1) — `emit_audit` **propaga** la
    excepción (fail-closed por defecto):
      • Operaciones de estado del ciclo (aprobar/cerrar/reabrir/config): el llamador
        NO debe continuar sin audit — sin auditoría no hay operación (principio del
        sistema). Dejar propagar dentro de la transacción multi-documento → rollback.
      • Eventos no críticos (p. ej. lecturas/exportaciones): el llamador envuelve en
        try/except + logger.error + Sentry y continúa.
    `entidad_id` (Kimi O2) se persiste como **str** (forma canónica del id
    referenciado), consistente con el índice forense de audit_log (Spec §2.3)."""
    if _audit_collection is None:
        raise RuntimeError(
            "audit no configurado: llamar configure_audit(client) primero"
        )
    evento = AuditEvento(evento)  # ValueError si no está en el catálogo
    doc = AuditLog(
        evento=evento,
        entidad=entidad,
        entidad_id=entidad_id,
        actor_id=actor_id,
        metadata=metadata or {},
        timestamp=now_utc(),
    )
    payload = doc.model_dump(mode="python", exclude={"id"})
    payload["evento"] = doc.evento.value  # str para BSON, no el enum de Python
    await _audit_collection.insert_one(payload)
    return doc
