"""Fiscal check dispatch: routes to whichever provider a venue is configured
for. Best-effort by design — a tax-authority network hiccup should never
block staff from closing an order, so this never raises. It just sets
order.fiscal_status/fiscal_check_number/fiscal_ticket_url/fiscal_error and
lets the caller commit alongside everything else."""
import logging

from app.models.order import Order
from app.models.venue import Venue
from app.services.fiscal import webkassa

logger = logging.getLogger(__name__)


async def issue_fiscal_check(order: Order, venue: Venue) -> None:
    if not venue.fiscal_provider:
        return  # fiscalization not enabled for this venue — nothing to do

    if not order.payment_method:
        order.fiscal_status = "failed"
        order.fiscal_error = "Не указан способ оплаты"
        return

    order.fiscal_status = "pending"

    if venue.fiscal_provider == "webkassa":
        if not all([venue.fiscal_api_key, venue.fiscal_login, venue.fiscal_password, venue.fiscal_cashbox_number]):
            order.fiscal_status = "failed"
            order.fiscal_error = "Фискализация не настроена для этого заведения"
            return
        try:
            result = await webkassa.issue_check(
                api_key=venue.fiscal_api_key,
                login=venue.fiscal_login,
                password=venue.fiscal_password,
                cashbox_number=venue.fiscal_cashbox_number,
                external_check_number=str(order.id),
                items=[{"name": i.name, "quantity": i.quantity, "price": i.price} for i in order.items],
                total_amount=order.total_amount,
                payment_method=order.payment_method,
            )
        except Exception as e:
            logger.error("Fiscal check failed for order %s: %s", order.id, e)
            order.fiscal_status = "failed"
            order.fiscal_error = str(e)
            return
        order.fiscal_status = "issued"
        order.fiscal_check_number = result["check_number"]
        order.fiscal_ticket_url = result["ticket_url"]
        order.fiscal_error = None
    else:
        order.fiscal_status = "failed"
        order.fiscal_error = f"Неизвестный провайдер фискализации: {venue.fiscal_provider}"
