"""Centralized settings for order-service, resolved from environment
variables at call time (not frozen at import) -- same convention every other
standalone service in this project uses (`05-payment-service`'s/
`06-shipping-service`'s `app/config.py`), so a fresh `Settings.from_env()`
call per test/app-instance picks up env vars set just before `create_app()`
runs.

order-service is the LAST extraction and sits on every axis at once: it is a
Kafka PRODUCER of `order.placed` (its own outbox, mirroring payment-/
shipping-service's half of the pattern), a Kafka CONSUMER of FOUR topics --
`payment.captured`/`payment.declined`/`shipment.dispatched`/
`shipment.failed`, the exact four topics the monolith's own
`order_saga_listener` subscribes to in one consumer group -- and a gRPC
CLIENT of inventory-service (never a listener; `INVENTORY_GRPC_TARGET`
matches the monolith's own `settings.INVENTORY_GRPC_TARGET` default).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

_DEFAULT_HTTP_PORT = 8088
_DEFAULT_DATABASE_URL = "postgresql://monolith:monolith@localhost:5432/monolith"
_DEFAULT_KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
_DEFAULT_INVENTORY_GRPC_TARGET = "localhost:9004"
_DEFAULT_ORDER_PLACED_TOPIC = "order.placed"
_DEFAULT_PAYMENT_CAPTURED_TOPIC = "payment.captured"
_DEFAULT_PAYMENT_DECLINED_TOPIC = "payment.declined"
_DEFAULT_SHIPMENT_DISPATCHED_TOPIC = "shipment.dispatched"
_DEFAULT_SHIPMENT_FAILED_TOPIC = "shipment.failed"
_DEFAULT_CONSUMER_GROUP = "order-service"
_DEFAULT_OUTBOX_POLL_MS = 1000
_DEFAULT_GRPC_TIMEOUT_S = 5.0


@dataclass(frozen=True)
class Settings:
    http_port: int
    database_url: str
    kafka_bootstrap_servers: str
    inventory_grpc_target: str
    order_placed_topic: str
    payment_captured_topic: str
    payment_declined_topic: str
    shipment_dispatched_topic: str
    shipment_failed_topic: str
    consumer_group: str
    outbox_poll_ms: int
    grpc_timeout_s: float

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            http_port=int(os.environ.get("HTTP_PORT", _DEFAULT_HTTP_PORT)),
            database_url=os.environ.get("DATABASE_URL", _DEFAULT_DATABASE_URL),
            kafka_bootstrap_servers=os.environ.get(
                "KAFKA_BOOTSTRAP_SERVERS", _DEFAULT_KAFKA_BOOTSTRAP_SERVERS
            ),
            inventory_grpc_target=os.environ.get(
                "INVENTORY_GRPC_TARGET", _DEFAULT_INVENTORY_GRPC_TARGET
            ),
            order_placed_topic=os.environ.get(
                "ORDER_PLACED_TOPIC", _DEFAULT_ORDER_PLACED_TOPIC
            ),
            payment_captured_topic=os.environ.get(
                "PAYMENT_CAPTURED_TOPIC", _DEFAULT_PAYMENT_CAPTURED_TOPIC
            ),
            payment_declined_topic=os.environ.get(
                "PAYMENT_DECLINED_TOPIC", _DEFAULT_PAYMENT_DECLINED_TOPIC
            ),
            shipment_dispatched_topic=os.environ.get(
                "SHIPMENT_DISPATCHED_TOPIC", _DEFAULT_SHIPMENT_DISPATCHED_TOPIC
            ),
            shipment_failed_topic=os.environ.get(
                "SHIPMENT_FAILED_TOPIC", _DEFAULT_SHIPMENT_FAILED_TOPIC
            ),
            consumer_group=os.environ.get("CONSUMER_GROUP", _DEFAULT_CONSUMER_GROUP),
            outbox_poll_ms=int(os.environ.get("OUTBOX_POLL_MS", _DEFAULT_OUTBOX_POLL_MS)),
            grpc_timeout_s=float(os.environ.get("GRPC_TIMEOUT_S", _DEFAULT_GRPC_TIMEOUT_S)),
        )
