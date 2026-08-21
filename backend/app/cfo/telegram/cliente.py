# backend/app/cfo/telegram/cliente.py
"""FABS · cliente Telegram SALIENTE (sendMessage). httpx con import PEREZOSO; sin
TELEGRAM_BOT_TOKEN ⇒ crear_cliente_telegram()=None. Los errores se loguean, no
revientan el webhook (una respuesta que no sale no debe tumbar el 200 a Telegram)."""

import logging
from typing import Protocol

from app.cfo import config

logger = logging.getLogger(__name__)

_API = "https://api.telegram.org/bot{token}/sendMessage"


class ClienteTelegramProto(Protocol):
    async def enviar(self, chat_id: int, texto: str) -> None: ...


class ClienteTelegram:
    def __init__(self, token: str, timeout_s: float = 10.0):
        self._token = token
        self._timeout = timeout_s

    async def enviar(self, chat_id: int, texto: str) -> None:
        import httpx  # import perezoso

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as c:
                r = await c.post(
                    _API.format(token=self._token),
                    json={"chat_id": chat_id, "text": texto},
                )
                r.raise_for_status()
        except Exception:  # noqa: BLE001 — no reventar el webhook
            logger.exception("fallo al enviar a Telegram chat=%s", chat_id)


def crear_cliente_telegram() -> ClienteTelegramProto | None:
    token = config.telegram_bot_token()
    return ClienteTelegram(token) if token else None
