"""Uniform error-mapping surface shared by all six contexts' views -- the
Python sibling of the Java monolith's `GlobalExceptionHandler` +
`ApiError`."""

from datetime import UTC, datetime

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


class ApiError(Exception):
    """Base class for domain exceptions mapped to the uniform error body
    `{"error": ..., "message": ..., "timestamp": ...}`."""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code = "INTERNAL_ERROR"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ResourceNotFound(ApiError):
    status_code = status.HTTP_404_NOT_FOUND
    error_code = "NOT_FOUND"


class InsufficientStock(ApiError):
    """Raised BEFORE any writes happen for a checkout line that exceeds
    quantity on hand -- contrast with PaymentDeclined/ShippingFailed, which
    ARE raised mid-transaction and rely on the single
    `transaction.atomic()` to undo earlier writes (SMELL[ch.22])."""

    status_code = status.HTTP_409_CONFLICT
    error_code = "OUT_OF_STOCK"


class PaymentDeclined(ApiError):
    """Raised when the checkout's paymentMethod simulates a decline. Because
    order.services.place_order() wraps inventory reservation + order
    persistence + payment + shipment + notification in ONE
    transaction.atomic() (SMELL[ch.22]), raising this mid-call rolls back
    everything already written in this request -- including the inventory
    reservation."""

    status_code = status.HTTP_402_PAYMENT_REQUIRED
    error_code = "PAYMENT_DECLINED"


class ShippingFailed(ApiError):
    """Raised when the checkout's shippingAddress contains the SHIP-FAIL
    sentinel. Same SMELL[ch.22] rollback story as PaymentDeclined: this is
    raised deep inside the one shared transaction, so it unwinds the
    inventory reservation, the order row, and the payment capture too."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "SHIPPING_FAILED"


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def api_exception_handler(exc, context):
    """DRF `EXCEPTION_HANDLER`: maps this module's `ApiError` subclasses (and
    DRF's own validation/auth exceptions) onto one uniform error body, the
    shape the Newman collection asserts on."""
    if isinstance(exc, ApiError):
        body = {"error": exc.error_code, "message": exc.message, "timestamp": _now_iso()}
        return Response(body, status=exc.status_code)

    response = drf_exception_handler(exc, context)
    if response is not None:
        error_code = "VALIDATION_FAILED" if response.status_code == 400 else "ERROR"
        response.data = {"error": error_code, "message": response.data, "timestamp": _now_iso()}
    return response
