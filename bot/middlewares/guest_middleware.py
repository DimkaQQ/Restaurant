import logging
from typing import Any, Awaitable, Callable

import httpx
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

logger = logging.getLogger(__name__)


class GuestMiddleware(BaseMiddleware):
    def __init__(self, api_url: str, network_id: str):
        self.api_url = api_url
        self.network_id = network_id

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
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        f"{self.api_url}/api/guests/",
                        json={
                            "network_id": self.network_id,
                            "telegram_id": user.id,
                            "name": user.full_name,
                        },
                        timeout=5.0,
                    )
                    if resp.status_code in (200, 201):
                        data["guest"] = resp.json()
                    else:
                        data["guest"] = None
            except Exception as e:
                logger.error("Guest middleware error: %s", e)
                data["guest"] = None
        else:
            data["guest"] = None

        return await handler(event, data)
