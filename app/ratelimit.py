"""Shared rate limiter with proxy-aware client addressing.

Behind nginx every request's socket peer is the proxy, so slowapi's default
get_remote_address would put ALL users into one shared bucket — one abusive
client would exhaust the login/register limits for every customer at once.
nginx sets X-Forwarded-For (see nginx/nginx.conf); we take its first hop.
The API port is bound to 127.0.0.1 in docker-compose, so the header can't
be forged by connecting to uvicorn directly.
"""
from slowapi import Limiter

from app.config import settings


def client_ip(request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=client_ip, enabled=settings.RATE_LIMIT_ENABLED)
