import logging
from typing import Any, Awaitable, Callable

import httpx
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

logger = logging.getLogger(__name__)


class GuestMiddleware(BaseMiddleware):
    def __init__(self, api_url: str, network_id: str, bot_api_secret: str = ""):
        self.api_url = api_url
        self.network_id = network_id
        self._headers = {"X-Bot-Secret": bot_api_secret} if bot_api_secret else {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = None
        if isinstance(event, Update):
            if event.message and event.message.from_user:
                user = event.message.from_user
            elif event.callback_query and event.callback_query.from_user:
                user = event.callback_query.from_user

        if user:
            tg_id = user.id
            try:
                async with httpx.AsyncClient(timeout=5.0, headers=self._headers) as client:
                    # Fetch guest (read-only — creation happens only in registration flow)
                    guest_resp = await client.get(
                        f"{self.api_url}/api/bot/guest/{tg_id}", params={"network_id": self.network_id}
                    )
                    if guest_resp.status_code == 200:
                        guest = guest_resp.json()
                        data["guest"] = guest
                        data["lang"] = guest.get("language") or "ru"
                    else:
                        data["guest"] = None
                        data["lang"] = "ru"

                    # Check if this Telegram account belongs to a staff user
                    staff_resp = await client.get(
                        f"{self.api_url}/api/bot/staff/{tg_id}", params={"network_id": self.network_id}
                    )
                    data["staff_user"] = staff_resp.json() if staff_resp.status_code == 200 else None

            except Exception as e:
                logger.error("Guest middleware error: %s", e)
                data["guest"] = None
                data["lang"] = "ru"
                data["staff_user"] = None
        else:
            data["guest"] = None
            data["lang"] = "ru"
            data["staff_user"] = None

        return await handler(event, data)
