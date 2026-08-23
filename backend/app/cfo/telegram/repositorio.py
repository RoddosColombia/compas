# backend/app/cfo/telegram/repositorio.py
"""FABS · única puerta de escritura/lectura del canal Telegram. SOLO colecciones
cfo_* (S1: ninguna otra subruta de cfo/telegram toca el driver de Mongo)."""

from pymongo.errors import DuplicateKeyError

from app.cfo.telegram.modelos import HiloCFO, VinculoTelegram


class VinculoDuplicado(Exception):
    """telegram_id o user_id ya vinculado (índice único uno-a-uno, B-3).

    Traduce el DuplicateKeyError del driver a una excepción de DOMINIO en la
    frontera del repositorio (S1: este módulo es el único que conoce pymongo).
    Así el router (capa HTTP) puede atrapar SOLO esto — nunca `except
    Exception` — y un fallo real ajeno (p. ej. de auditoría, posterior a un
    insert que sí tuvo éxito) no se enmascara como un 409 falso."""


async def crear_vinculo(v: VinculoTelegram) -> None:
    try:
        await v.insert()
    except DuplicateKeyError as e:
        raise VinculoDuplicado("telegram_id o user_id ya vinculado") from e


async def eliminar_vinculo(telegram_id: int) -> bool:
    v = await VinculoTelegram.find_one(VinculoTelegram.telegram_id == telegram_id)
    if v is None:
        return False
    await v.delete()
    return True


async def resolver_usuario(telegram_id: int) -> str | None:
    v = await VinculoTelegram.find_one(VinculoTelegram.telegram_id == telegram_id)
    return v.user_id if v is not None else None


async def listar_vinculos() -> list[VinculoTelegram]:
    return await VinculoTelegram.find_all().to_list()


async def obtener_hilo(user_id: str) -> HiloCFO | None:
    return await HiloCFO.find_one(HiloCFO.user_id == user_id)


async def guardar_hilo(h: HiloCFO) -> None:
    existe = await HiloCFO.find_one(HiloCFO.user_id == h.user_id)
    if existe is None:
        await h.insert()
    else:
        existe.turnos = h.turnos
        existe.ultimo_update_id = h.ultimo_update_id
        existe.ultimo_envio = h.ultimo_envio
        existe.actualizado_at = h.actualizado_at
        await existe.save()
