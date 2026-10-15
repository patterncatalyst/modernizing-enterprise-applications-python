import logging

from .models import Notification

logger = logging.getLogger(__name__)


def send_order_confirmation(customer, order) -> Notification:
    """
    SMELL[ch.17]: called SYNCHRONOUSLY, in-process, from
    order.services.place_order() -- inside the SAME transaction.atomic() as
    the rest of checkout. Two problems this plants on purpose: (1) checkout
    latency is coupled to however long "sending" a notification takes, even
    though the customer doesn't need to wait for it; (2) if sending raised, it
    would roll back the whole order along with it. The cure (notification
    extraction) replaces this with a transactional outbox write + an async
    event-driven consumer, decoupling both latency and failure domain.
    """
    message = f"Order #{order.id} confirmed, total ${order.total_cents / 100:.2f}"
    notification = Notification.objects.create(
        customer=customer, order=order, channel="EMAIL", message=message
    )

    # SMELL[ch.17]: DUAL-WRITE HAZARD. The DB write above (the Notification
    # row, committed/rolled back atomically with the rest of checkout) and the
    # "send" below (a stand-in for a call to a real email/SMS provider) are
    # two independent writes to two independent systems with NO shared
    # transaction between them. If the process crashed between the DB commit
    # and the provider call, the customer would never get the email even
    # though the Notification row says it was sent; if the provider call were
    # retried naively, the customer could get duplicate emails. This is the
    # textbook "dual write" problem. The transactional outbox cures it by
    # making the OUTBOX WRITE the only thing inside the local transaction, and
    # letting a relay publish to the real provider at-least-once,
    # independently, with its own retry and idempotency story -- the same
    # pattern the Java sibling's `V3__outbox.sql` migration introduces.
    _dispatch_via_external_provider(notification)
    return notification


def _dispatch_via_external_provider(notification: Notification) -> None:
    """Stand-in for a call to a real transactional email/SMS provider
    (SendGrid, SES, Twilio, ...). Logged rather than actually sent, since this
    is a demo system -- but the hazard it illustrates (SMELL[ch.17] above) is
    real: this call is not part of the database transaction that wrote
    `notification`, and never can be."""
    logger.info(
        "notification.dispatched channel=%s customer_id=%s order_id=%s",
        notification.channel,
        notification.customer_id,
        notification.order_id,
    )


def list_by_customer_id(customer_id):
    return Notification.objects.filter(customer_id=customer_id).order_by("id")
