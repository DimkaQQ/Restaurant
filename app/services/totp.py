"""Minimal RFC 6238 TOTP (SHA-1, 30s step, 6 digits) — the exact profile
Google Authenticator / 1Password / Aegis use. Implemented on the stdlib so
2FA doesn't pull in a dependency."""
import base64
import hashlib
import hmac
import secrets
import struct
import time


def generate_secret() -> str:
    """160-bit base32 secret, the standard authenticator-app size."""
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def provisioning_uri(secret: str, account: str, issuer: str = "RestOS") -> str:
    from urllib.parse import quote
    return (
        f"otpauth://totp/{quote(issuer)}:{quote(account)}"
        f"?secret={secret}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30"
    )


def _code_at(secret: str, counter: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return f"{number % 1_000_000:06d}"


def verify_code(secret: str, code: str, window: int = 1) -> bool:
    """Accept the current 30s step ± `window` steps (clock drift)."""
    code = (code or "").strip().replace(" ", "")
    if not code.isdigit() or len(code) != 6:
        return False
    counter = int(time.time()) // 30
    return any(
        hmac.compare_digest(_code_at(secret, counter + off), code)
        for off in range(-window, window + 1)
    )
