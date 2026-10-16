"""Centralized settings for notification-service, resolved from environment
variables at call time (not frozen at import) -- same convention
`02-review-service`'s `app/db.py::resolve_database_url` uses, so a fresh
`Settings.from_env()` call per test/app-instance picks up env vars set just
before `create_app()` runs (see `tests/conftest.py`).

Unlike review-service (one env var, read directly in `app/db.py`), this
service has enough independently-configurable pieces -- HTTP port, Kafka
bootstrap servers, topic, consumer group -- that collecting them in one place
beats scattering `os.environ.get(...)` calls across `app/main.py` and
`app/consumer.py`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

_DEFAULT_PORT = 8002
_DEFAULT_DATABASE_URL = "postgresql://monolith:monolith@localhost:5432/monolith"
_DEFAULT_KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
_DEFAULT_ORDER_PLACED_TOPIC = "order.placed"
_DEFAULT_CONSUMER_GROUP = "notification-service"


@dataclass(frozen=True)
class Settings:
    port: int
    database_url: str
    kafka_bootstrap_servers: str
    order_placed_topic: str
    consumer_group: str

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            port=int(os.environ.get("PORT", _DEFAULT_PORT)),
            database_url=os.environ.get("DATABASE_URL", _DEFAULT_DATABASE_URL),
            kafka_bootstrap_servers=os.environ.get(
                "KAFKA_BOOTSTRAP_SERVERS", _DEFAULT_KAFKA_BOOTSTRAP_SERVERS
            ),
            order_placed_topic=os.environ.get("ORDER_PLACED_TOPIC", _DEFAULT_ORDER_PLACED_TOPIC),
            consumer_group=os.environ.get("CONSUMER_GROUP", _DEFAULT_CONSUMER_GROUP),
        )
