"""Shared httpx client factory that injects the bot API secret header."""
import os
import httpx

_BOT_API_SECRET = os.getenv("BOT_API_SECRET", "")


def bot_client(timeout: float = 5.0, **kwargs) -> httpx.AsyncClient:
    """Return an AsyncClient pre-configured with X-Bot-Secret if set."""
    headers = dict(kwargs.pop("headers", {}))
    if _BOT_API_SECRET:
        headers["X-Bot-Secret"] = _BOT_API_SECRET
    return httpx.AsyncClient(headers=headers, timeout=timeout, **kwargs)
