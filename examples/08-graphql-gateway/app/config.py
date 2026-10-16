"""Centralized settings for graphql-gateway, resolved from environment
variables at call time (not frozen at import) -- same convention every other
standalone service in this project uses (`05-payment-service`'s/
`06-shipping-service`'s/`07-order-service`'s `app/config.py`), so a fresh
`Settings.from_env()` call per test/request picks up env vars set just
before the call.

This gateway is stateless: it owns no database, no Kafka topic, no write
path -- every setting here is either this service's own HTTP port or a
downstream target it federates reads from. Every downstream target is FIXED
operator config, never derived from the incoming GraphQL request -- letting a
client redirect a downstream call would turn an aggregation gateway into an
SSRF/amplification vector. Query depth/complexity limits live here too, for
the same secure-by-design reason: operator-controlled, not request-derived.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

_DEFAULT_HTTP_PORT = 8090

# Downstream REST targets -- the four already-extracted services whose own
# read surfaces this gateway calls directly, over the same REST contract
# their other consumers use. Defaults target local `uv run uvicorn`/compose
# processes; the helm chart (if/when this gateway gets one) would override
# these via env, same as every other service's own `*_SERVICE_URL` vars.
_DEFAULT_ORDER_SERVICE_URL = "http://localhost:8088"
_DEFAULT_PAYMENT_SERVICE_URL = "http://localhost:8085"
_DEFAULT_SHIPPING_SERVICE_URL = "http://localhost:8087"
_DEFAULT_REVIEW_SERVICE_URL = "http://localhost:8001"

# Downstream gRPC target -- inventory-service's `GetStock` RPC, the exact
# same host/port convention `07-order-service`'s `AsyncInventoryClient` uses.
_DEFAULT_INVENTORY_GRPC_TARGET = "localhost:9004"

_DEFAULT_REST_TIMEOUT_S = 5.0
_DEFAULT_GRPC_TIMEOUT_S = 3.0

# Secure-by-design (DRQ-069 analog): bound query depth/complexity so this
# aggregation gateway can't be turned into a request-controlled fan-out/
# amplification vector. The deepest legitimate query this schema supports is
# order -> items -> stock|reviews (depth 3); 10 leaves headroom for aliases/
# fragments in a contract test suite while still rejecting a deliberately
# recursive/padded query. The token budget bounds the total number of parsed
# query tokens (Strawberry's `MaxTokensLimiter`), catching a query padded
# with many aliased copies of the same expensive subtree even if it stays
# within the depth bound.
_DEFAULT_MAX_QUERY_DEPTH = 10
_DEFAULT_MAX_QUERY_TOKENS = 1000


@dataclass(frozen=True)
class Settings:
    http_port: int
    order_service_url: str
    payment_service_url: str
    shipping_service_url: str
    review_service_url: str
    inventory_grpc_target: str
    rest_timeout_s: float
    grpc_timeout_s: float
    max_query_depth: int
    max_query_tokens: int

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            http_port=int(os.environ.get("HTTP_PORT", _DEFAULT_HTTP_PORT)),
            order_service_url=os.environ.get("ORDER_SERVICE_URL", _DEFAULT_ORDER_SERVICE_URL),
            payment_service_url=os.environ.get(
                "PAYMENT_SERVICE_URL", _DEFAULT_PAYMENT_SERVICE_URL
            ),
            shipping_service_url=os.environ.get(
                "SHIPPING_SERVICE_URL", _DEFAULT_SHIPPING_SERVICE_URL
            ),
            review_service_url=os.environ.get("REVIEW_SERVICE_URL", _DEFAULT_REVIEW_SERVICE_URL),
            inventory_grpc_target=os.environ.get(
                "INVENTORY_GRPC_TARGET", _DEFAULT_INVENTORY_GRPC_TARGET
            ),
            rest_timeout_s=float(os.environ.get("REST_TIMEOUT_S", _DEFAULT_REST_TIMEOUT_S)),
            grpc_timeout_s=float(os.environ.get("GRPC_TIMEOUT_S", _DEFAULT_GRPC_TIMEOUT_S)),
            max_query_depth=int(os.environ.get("MAX_QUERY_DEPTH", _DEFAULT_MAX_QUERY_DEPTH)),
            max_query_tokens=int(
                os.environ.get("MAX_QUERY_TOKENS", _DEFAULT_MAX_QUERY_TOKENS)
            ),
        )
