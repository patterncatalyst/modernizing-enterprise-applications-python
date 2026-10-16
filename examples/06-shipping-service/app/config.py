"""Centralized settings for shipping-service, resolved from environment
variables at call time (not frozen at import) -- same convention every other
standalone service in this project uses (`05-payment-service`'s
`app/config.py`), so a fresh `Settings.from_env()` call per test/app-instance
picks up env vars set just before `create_app()` runs.

shipping-service is the ORCHESTRATED counterpart to payment-service's
choreography: it consumes ONE topic (`payment.captured`, the saga trigger),
produces to its OWN outbox-fed topics (`shipment.dispatched`/
`shipment.failed`), AND reaches out over HTTP to the monolith's `GET
/api/orders/{id}` to enrich a saga's context with the order's shipping
address (`monolith_base_url`) -- a dependency none of the choreographed
services (payment-/notification-/review-service) have.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

_DEFAULT_HTTP_PORT = 8087
_DEFAULT_DATABASE_URL = "postgresql://monolith:monolith@localhost:5432/monolith"
_DEFAULT_KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
_DEFAULT_MONOLITH_BASE_URL = "http://localhost:8000"
_DEFAULT_PAYMENT_CAPTURED_TOPIC = "payment.captured"
_DEFAULT_SHIPMENT_DISPATCHED_TOPIC = "shipment.dispatched"
_DEFAULT_SHIPMENT_FAILED_TOPIC = "shipment.failed"
_DEFAULT_CONSUMER_GROUP = "shipping-service"
_DEFAULT_OUTBOX_POLL_MS = 1000
_DEFAULT_ENRICH_TIMEOUT_S = 5.0


@dataclass(frozen=True)
class Settings:
    http_port: int
    database_url: str
    kafka_bootstrap_servers: str
    monolith_base_url: str
    payment_captured_topic: str
    shipment_dispatched_topic: str
    shipment_failed_topic: str
    consumer_group: str
    outbox_poll_ms: int
    enrich_timeout_s: float

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            http_port=int(os.environ.get("HTTP_PORT", _DEFAULT_HTTP_PORT)),
            database_url=os.environ.get("DATABASE_URL", _DEFAULT_DATABASE_URL),
            kafka_bootstrap_servers=os.environ.get(
                "KAFKA_BOOTSTRAP_SERVERS", _DEFAULT_KAFKA_BOOTSTRAP_SERVERS
            ),
            monolith_base_url=os.environ.get("MONOLITH_BASE_URL", _DEFAULT_MONOLITH_BASE_URL),
            payment_captured_topic=os.environ.get(
                "PAYMENT_CAPTURED_TOPIC", _DEFAULT_PAYMENT_CAPTURED_TOPIC
            ),
            shipment_dispatched_topic=os.environ.get(
                "SHIPMENT_DISPATCHED_TOPIC", _DEFAULT_SHIPMENT_DISPATCHED_TOPIC
            ),
            shipment_failed_topic=os.environ.get(
                "SHIPMENT_FAILED_TOPIC", _DEFAULT_SHIPMENT_FAILED_TOPIC
            ),
            consumer_group=os.environ.get("CONSUMER_GROUP", _DEFAULT_CONSUMER_GROUP),
            outbox_poll_ms=int(os.environ.get("OUTBOX_POLL_MS", _DEFAULT_OUTBOX_POLL_MS)),
            enrich_timeout_s=float(
                os.environ.get("ENRICH_TIMEOUT_S", _DEFAULT_ENRICH_TIMEOUT_S)
            ),
        )
