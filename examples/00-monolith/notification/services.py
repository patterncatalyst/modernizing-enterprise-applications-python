import logging

from django.db import IntegrityError, transaction

from .models import Notification

logger = logging.getLogger(__name__)


def record_order_placed(event: dict) -> Notification | None:
    """Handler for the `order.placed` event (frozen contract: camelCase
    `orderId`/`customerId`/`customerEmail`/`totalCents`/`confirmationMessage`/
    `placedAt`), invoked by `notification.management.commands
    .order_placed_consumer`.

    SMELL[ch.17] CURED (r03, smells #5/#6): this replaces the old
    `send_order_confirmation()`, which was called SYNCHRONOUSLY, in-process,
    from `order.services.place_order()` inside checkout's own
    `transaction.atomic()` -- coupling checkout latency to "sending" a
    notification (smell #5) and dual-writing to the DB and a stand-in
    provider with no shared transaction between them (smell #6). Now
    `place_order()` writes only an outbox row in its own transaction; a relay
    (`common.management.commands.outbox_relay`) publishes it to Kafka
    at-least-once; THIS consumer repopulates the `Notification` read model
    from the event, fully decoupled from checkout's transaction and failure
    domain.

    Idempotent by construction: at-least-once delivery means this can run
    more than once for the same order (a relay crash between publish and
    stamping `published_at` re-sends; a consumer re-processing after a crash
    before its offset commit re-delivers). Check-then-create is the fast
    path; `Notification`'s partial unique constraint on `order`
    (`uniq_notification_per_order`) is the DB-level backstop against the
    race between the check and the create.
    """
    order_id = event["orderId"]
    existing = Notification.objects.filter(order_id=order_id).first()
    if existing is not None:
        logger.info("notification.duplicate order_id=%s -- skipping", order_id)
        return existing

    try:
        with transaction.atomic():
            return Notification.objects.create(
                customer_id=event["customerId"],
                order_id=order_id,
                channel="EMAIL",
                message=event["confirmationMessage"],
            )
    except IntegrityError:
        # Lost the race against another delivery of the same event -- the
        # partial unique constraint caught it. Fetch what the winner wrote.
        logger.info("notification.duplicate order_id=%s -- lost race", order_id)
        return Notification.objects.filter(order_id=order_id).first()


def list_by_customer_id(customer_id):
    return Notification.objects.filter(customer_id=customer_id).order_by("id")
