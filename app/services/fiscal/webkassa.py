"""Webkassa (Kazakhstan online kassa / ОФД) client — POST /api/v4/Authorize + /api/v4/check.

Built against the real "ИНТЕГРАТОРЫ v4" Postman collection (v2.0.3) shared by
the restaurant owner from their Webkassa test cabinet, not guessed — see the
request/response shapes below for the exact contract.
"""
import logging
from decimal import Decimal

import httpx

logger = logging.getLogger(__name__)

# devkkm.webkassa.kz is the test/sandbox host. Production checks go to a
# different host — confirm with Webkassa support before flipping a venue to
# live keys (this is not something to guess at).
BASE_URL = "https://devkkm.webkassa.kz"
TIMEOUT = 15.0

# 796 = "штука" (piece) in the OKEI unit classifier Webkassa's RefUnits uses —
# the sane default for restaurant menu items sold by the portion.
DEFAULT_UNIT_CODE = 796

_PAYMENT_TYPE = {"cash": 0, "card": 1, "mobile": 4}


class WebkassaError(Exception):
    def __init__(self, code: int | None, message: str):
        self.code = code
        self.message = message
        super().__init__(f"Webkassa error {code}: {message}")


def _raise_for_errors(data: dict) -> None:
    errors = data.get("Errors")
    if errors:
        first = errors[0]
        raise WebkassaError(first.get("Code"), first.get("Text", "Unknown error"))


async def _authorize(api_key: str, login: str, password: str) -> str:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(
            f"{BASE_URL}/api/v4/Authorize",
            headers={"x-api-key": api_key},
            json={"Login": login, "Password": password},
        )
        resp.raise_for_status()
    data = resp.json()
    _raise_for_errors(data)
    token = (data.get("Data") or {}).get("Token")
    if not token:
        raise WebkassaError(-1, "Authorize response had no Token")
    return token


async def issue_check(
    *,
    api_key: str,
    login: str,
    password: str,
    cashbox_number: str,
    external_check_number: str,
    items: list[dict],
    total_amount: Decimal,
    payment_method: str,
) -> dict:
    """items: [{"name": str, "quantity": int, "price": Decimal}].
    Returns {"check_number": str, "ticket_url": str}.
    Raises WebkassaError on any failure (including auth failure)."""
    token = await _authorize(api_key, login, password)

    positions = [
        {
            "Count": item["quantity"],
            "Price": float(item["price"]),
            # No VAT — most small KZ restaurant clients are on a simplified
            # tax regime without VAT. A venue on the general regime would
            # need TaxType=100 + a real TaxPercent; not exposed yet.
            "TaxPercent": 0,
            "Tax": 0,
            "TaxType": 0,
            "PositionName": item["name"][:250],
            "UnitCode": DEFAULT_UNIT_CODE,
        }
        for item in items
    ]

    payload = {
        "Token": token,
        "CashboxUniqueNumber": cashbox_number,
        "OperationType": 2,  # sale
        "Positions": positions,
        "Payments": [
            {"Sum": float(total_amount), "PaymentType": _PAYMENT_TYPE.get(payment_method, 1)}
        ],
        "RoundType": 0,  # round each position to 2 decimals; least surprising default
        # Order id as the idempotency key: retrying a fiscal call for the same
        # order (e.g. after a network timeout) never double-fiscalizes.
        "ExternalCheckNumber": external_check_number,
    }

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(
            f"{BASE_URL}/api/v4/check",
            headers={"x-api-key": api_key},
            json=payload,
        )
        resp.raise_for_status()
    data = resp.json()

    errors = data.get("Errors")
    result = data.get("Data")
    # Code 14 = this ExternalCheckNumber was already fiscalized. Webkassa still
    # returns the original Data alongside the error, so treat it as success —
    # this is exactly the idempotent-retry case ExternalCheckNumber exists for.
    if errors and not (len(errors) == 1 and errors[0].get("Code") == 14):
        _raise_for_errors(data)

    if not result:
        raise WebkassaError(-1, "Empty Data in check response")

    return {
        "check_number": result.get("CheckNumber"),
        "ticket_url": result.get("TicketUrl"),
    }
