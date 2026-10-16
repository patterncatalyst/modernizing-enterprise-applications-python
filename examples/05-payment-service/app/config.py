"""Centralized settings for payment-service, resolved from environment
variables at call time (not frozen at import) -- same convention
`03-notification-service`'s `app/config.py` uses, so a fresh
`Settings.from_env()` call per test/app-instance picks up env vars set just
before `create_app()` runs (see `tests/unit/conftest.py`).

payment-service has one more independently-configurable piece than
notification-service: it PUBLISHES two outbox-fed topics
(`payment.captured`/`payment.declined`) in addition to CONSUMING one
(`order.placed`), plus its own outbox relay's poll interval -- collecting all
of it here beats scattering `os.environ.get(...)` calls across
`app/main.py`, `app/consumer.py`, and `app/relay.py`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

_DEFAULT_HTTP_PORT = 8085
_DEFAULT_DATABASE_URL = "postgresql://monolith:monolith@localhost:5432/monolith"
_DEFAULT_KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
_DEFAULT_ORDER_PLACED_TOPIC = "order.placed"
_DEFAULT_PAYMENT_CAPTURED_TOPIC = "payment.captured"
_DEFAULT_PAYMENT_DECLINED_TOPIC = "payment.declined"
_DEFAULT_CONSUMER_GROUP = "payment-service"
_DEFAULT_OUTBOX_POLL_MS = 1000


@dataclass(frozen=True)
class Settings:
    http_port: int
    database_url: str
    kafka_bootstrap_servers: str
    order_placed_topic: str
    payment_captured_topic: str
    payment_declined_topic: str
    consumer_group: str
    outbox_poll_ms: int

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            http_port=int(os.environ.get("HTTP_PORT", _DEFAULT_HTTP_PORT)),
            database_url=os.environ.get("DATABASE_URL", _DEFAULT_DATABASE_URL),
            kafka_bootstrap_servers=os.environ.get(
                "KAFKA_BOOTSTRAP_SERVERS", _DEFAULT_KAFKA_BOOTSTRAP_SERVERS
            ),
            order_placed_topic=os.environ.get("ORDER_PLACED_TOPIC", _DEFAULT_ORDER_PLACED_TOPIC),
            payment_captured_topic=os.environ.get(
                "PAYMENT_CAPTURED_TOPIC", _DEFAULT_PAYMENT_CAPTURED_TOPIC
            ),
            payment_declined_topic=os.environ.get(
                "PAYMENT_DECLINED_TOPIC", _DEFAULT_PAYMENT_DECLINED_TOPIC
            ),
            consumer_group=os.environ.get("CONSUMER_GROUP", _DEFAULT_CONSUMER_GROUP),
            outbox_poll_ms=int(os.environ.get("OUTBOX_POLL_MS", _DEFAULT_OUTBOX_POLL_MS)),
        )
