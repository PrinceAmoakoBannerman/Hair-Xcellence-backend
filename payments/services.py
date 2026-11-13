"""Apply Paystack results to orders (shared by the verify endpoint and the webhook)."""
import logging

from django.db import transaction

from orders.models import Order

from . import paystack

log = logging.getLogger(__name__)


def apply_transaction(tx: dict) -> Order | None:
    """
    Update the order a Paystack transaction belongs to.
    Safe to call more than once for the same transaction (verify + webhook).
    """
    reference = tx.get("reference", "")
    number = (tx.get("metadata") or {}).get("order_number") or reference.rsplit("-", 1)[0]
    with transaction.atomic():
        order = Order.objects.select_for_update().filter(number=number).first()
        if not order:
            log.warning("Paystack transaction %s has no matching order", reference)
            return None
        if order.payment_status == Order.PaymentStatus.PAID:
            return order  # already done

        status = tx.get("status")
        amount_ok = tx.get("amount") == paystack.to_pesewas(order.total) and (tx.get("currency") or "GHS") == "GHS"

        if status == "success" and amount_ok:
            order.payment_status = Order.PaymentStatus.PAID
            order.payment_reference = reference
            order.payment_channel = tx.get("channel") or ""
            order.save()  # sets paid_at
        elif status == "success":  # paid, but not the amount we asked for
            order.note = (order.note + "\n" if order.note else "") + (
                f"Paystack {reference}: received {tx.get('amount')} {tx.get('currency')} pesewas, "
                f"expected {paystack.to_pesewas(order.total)}. Check before shipping."
            )
            order.payment_reference = reference
            order.save(update_fields=["note", "payment_reference", "updated_at"])
        # "abandoned" only means started-but-not-paid yet, so the order stays pending.
        elif status in ("failed", "reversed"):
            order.payment_status = Order.PaymentStatus.FAILED
            order.payment_reference = reference
            order.save()
        return order
