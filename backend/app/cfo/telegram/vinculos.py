# backend/app/cfo/telegram/vinculos.py
"""FABS · lógica de la allowlist (alta/baja/resolución) con auditoría CR-CFO-2.

vincular/desvincular son operaciones de estado (admin), no lecturas: emit_audit
NO se envuelve en fail-soft aquí — si la auditoría falla, el error propaga (a
diferencia del Q&A, que sí es fail-soft, en el servicio)."""

from app.audit.events import AuditEvento
from app.audit.service import emit_audit
from app.cfo.telegram import repositorio
from app.cfo.telegram.modelos import VinculoTelegram
from app.core.time import now_utc


async def vincular(telegram_id: int, user_id: str, admin_id: str) -> None:
    v = VinculoTelegram(
        telegram_id=telegram_id,
        user_id=user_id,
        creado_por=admin_id,
        creado_at=now_utc(),
    )
    await repositorio.crear_vinculo(v)  # DuplicateKeyError si ya existe (uno-a-uno)
    await emit_audit(
        AuditEvento.cfo_vinculo_creado,
        entidad="cfo",
        actor_id=admin_id,
        metadata={"telegram_id": telegram_id, "user_id": user_id},
    )


async def desvincular(telegram_id: int, admin_id: str) -> bool:
    ok = await repositorio.eliminar_vinculo(telegram_id)
    if ok:
        await emit_audit(
            AuditEvento.cfo_vinculo_eliminado,
            entidad="cfo",
            actor_id=admin_id,
            metadata={"telegram_id": telegram_id},
        )
    return ok


async def resolver(telegram_id: int) -> str | None:
    return await repositorio.resolver_usuario(telegram_id)
