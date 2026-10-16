from common.exceptions import PaymentDeclined, ResourceNotFound

from .models import Payment

DECLINE_SENTINEL = "DECLINE"


def charge(order, amount_cents: int, method: str) -> Payment:
    """Simulated payment capture.

    SMELL[ch.22]/[ch.26]: called synchronously, in-process, from
    order.services.place_order(), inside the SAME transaction.atomic() as the
    inventory reservation. A decline raised here rolls back everything
    written so far in that same local transaction -- the "free" ACID rollback
    that a saga has to rebuild explicitly once payment is its own service
    with its own database.

    Demo decline rule: any `method` value containing "DECLINE"
    (case-insensitive) is treated as a declined card, deterministically, so
    the Newman payment-decline scenario doesn't need a real payment gateway.
    """
    if DECLINE_SENTINEL in method.upper():
        raise PaymentDeclined(f"Payment method '{method}' was declined")
    return Payment.objects.create(
        order=order, amount_cents=amount_cents, method=method, status=Payment.Status.CAPTURED
    )


def get_by_id(payment_id: int) -> Payment:
    try:
        return Payment.objects.get(pk=payment_id)
    except Payment.DoesNotExist as exc:
        raise ResourceNotFound(f"No payment with id {payment_id}") from exc


def list_by_order_id(order_id):
    return Payment.objects.filter(order_id=order_id).order_by("id")
