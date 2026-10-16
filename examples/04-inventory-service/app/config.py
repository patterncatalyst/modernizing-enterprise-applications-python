"""Centralized settings for inventory-service, resolved from environment
variables at call time (not frozen at import) -- same convention
`03-notification-service`'s `app/config.py` uses, so a fresh
`Settings.from_env()` call per test/app-instance picks up env vars set just
before `create_app()` runs.

Unlike notification-service (one HTTP port), this service binds TWO ports --
HTTP (`:8084`, the read surface) and a separate gRPC server (`:9004`, the
synchronous order<->inventory ACL seam) -- plus the transition-only CDC
consumer's flag and Kafka coordinates.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

_DEFAULT_HTTP_PORT = 8084
_DEFAULT_GRPC_PORT = 9004
_DEFAULT_DATABASE_URL = "postgresql://monolith:monolith@localhost:5432/monolith"
_DEFAULT_KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
_DEFAULT_INVENTORY_CDC_TOPIC = "meap.public.inventory_items"
_DEFAULT_INVENTORY_CDC_GROUP = "inventory-service-cdc"


def _bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    http_port: int
    grpc_port: int
    database_url: str
    kafka_bootstrap_servers: str
    inventory_cdc_enabled: bool
    inventory_cdc_topic: str
    inventory_cdc_group: str

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            http_port=int(os.environ.get("HTTP_PORT", _DEFAULT_HTTP_PORT)),
            grpc_port=int(os.environ.get("GRPC_PORT", _DEFAULT_GRPC_PORT)),
            database_url=os.environ.get("DATABASE_URL", _DEFAULT_DATABASE_URL),
            kafka_bootstrap_servers=os.environ.get(
                "KAFKA_BOOTSTRAP_SERVERS", _DEFAULT_KAFKA_BOOTSTRAP_SERVERS
            ),
            # Transition-only (retired after cutover, see ../CUTOVER.md) --
            # OFF by default: CI and the end-state posture never need it, the
            # service's own Alembic migration seeds its schema directly.
            inventory_cdc_enabled=_bool_env("INVENTORY_CDC_ENABLED", False),
            inventory_cdc_topic=os.environ.get(
                "INVENTORY_CDC_TOPIC", _DEFAULT_INVENTORY_CDC_TOPIC
            ),
            inventory_cdc_group=os.environ.get(
                "INVENTORY_CDC_GROUP", _DEFAULT_INVENTORY_CDC_GROUP
            ),
        )
