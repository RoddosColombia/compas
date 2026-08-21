# backend/tests/cfo/telegram/fakes.py
"""Cliente Telegram falso para tests (sin red)."""


class ClienteTelegramFake:
    def __init__(self):
        self.enviados: list[tuple[int, str]] = []

    async def enviar(self, chat_id: int, texto: str) -> None:
        self.enviados.append((chat_id, texto))
