"""HTTP client backing the saga's `enrich` step (`app/steps.py::enrich`) --
the ch.25 resilience anchor this service introduces (none of the
choreographed services in this project make an outbound HTTP call; this is
the first one). `GET {MONOLITH_BASE_URL}/api/orders/{orderId}` and reads back
`shippingAddress`, the ADDITIVE field a sibling lane added to the monolith's
`order/serializers.py::OrderSerializer` specifically so this saga can enrich
itself without reaching into the monolith's database directly.

Wrapped in `tenacity` (per this project's resilience-library convention: ch14
pins tenacity for retry in Python services) retrying only the TRANSIENT
failure modes (`httpx.TransportError`/`httpx.TimeoutException` -- connection
refused, DNS failure, a request that blew its own per-call timeout), with a
bounded per-attempt timeout so a hung monolith can never stall a saga step
indefinitely. A non-2xx response, or a response simply missing
`shippingAddress`, is a CONTRACT violation, not a transient blip -- raised
immediately as `EnrichmentError`, not retried.
"""

from __future__ import annotations

import logging

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger("shipping_service.enrich_client")

_RETRYABLE_EXCEPTIONS = (httpx.TransportError, httpx.TimeoutException)
_MAX_ATTEMPTS = 3


class EnrichmentError(Exception):
    """Raised when the order's `shippingAddress` could not be obtained, after
    retries are exhausted for a transient failure, or immediately for a
    non-2xx response / a missing field. Propagates out of
    `app/steps.py::enrich` so `app/orchestrator.py::_advance_one_step` routes
    the saga to `COMPENSATING` exactly like any other step failure."""


@retry(
    retry=retry_if_exception_type(_RETRYABLE_EXCEPTIONS),
    stop=stop_after_attempt(_MAX_ATTEMPTS),
    wait=wait_exponential(multiplier=0.2, min=0.2, max=2),
    reraise=True,
)
async def _get_order(
    client: httpx.AsyncClient, base_url: str, order_id: int, timeout_s: float
) -> dict:
    response = await client.get(f"{base_url}/api/orders/{order_id}", timeout=timeout_s)
    response.raise_for_status()
    return response.json()


async def fetch_shipping_address(*, base_url: str, order_id: int, timeout_s: float) -> str:
    """`app/steps.py::enrich`'s only collaborator. Opens a short-lived
    `httpx.AsyncClient` per call (this is one call per saga step, not a
    hot path needing a shared connection pool across requests)."""
    async with httpx.AsyncClient() as client:
        try:
            body = await _get_order(client, base_url, order_id, timeout_s)
        except httpx.HTTPStatusError as exc:
            raise EnrichmentError(
                f"order {order_id} enrichment failed: {exc.response.status_code} "
                f"response from {base_url}"
            ) from exc
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            raise EnrichmentError(
                f"order {order_id} enrichment failed after {_MAX_ATTEMPTS} attempts: {exc}"
            ) from exc

    address = body.get("shippingAddress")
    if not address:
        raise EnrichmentError(f"order {order_id}'s read surface did not provide a shippingAddress")
    return address
