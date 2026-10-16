"""order-service -- the FINALE extraction: a CQRS FastAPI service on `:8088`.
A command side (`POST /api/orders` -> gRPC reserve, then aggregate + outbox
+ `order_view` in one transaction) and a read side (`GET /api/orders[/{id}]`,
served from `order_view` only). An idempotent `aiokafka` consumer reacts to
FOUR saga-outcome topics (`payment.captured`/`payment.declined`/
`shipment.dispatched`/`shipment.failed`) to drive the order to its terminal
status; this service's OWN transactional outbox + relay produces
`order.placed`. A gRPC CLIENT of inventory-service (never a listener). See
`../README.md` for the CQRS/own-schema story, `../EVENTS.md` for the event
contracts, and `../MIGRATION.md` for the lift-and-reshape write-up.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app import db
from app.config import Settings
from app.consumer import OrderSagaConsumer
from app.errors import install_exception_handlers
from app.relay import OutboxRelay
from app.routes import router

logger = logging.getLogger("order_service")


def _configure_logging() -> None:
    """Rotating file log under `logs/order-service.log` alongside console
    output -- non-negotiable for AI-assisted development (house convention),
    identical setup to every other standalone service's `app/main.py`."""
    log_dir = Path(os.environ.get("LOG_DIR", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)

    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "order-service.log", maxBytes=10 * 1024 * 1024, backupCount=5
    )
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-5s [%(name)s] %(message)s")
    )
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-5s %(message)s"))

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(file_handler)
    root.addHandler(console_handler)
    logging.getLogger("order_service").setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings.from_env()
    engine = db.create_engine(settings.database_url)
    session_factory = db.create_session_factory(engine)
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.settings = settings

    consumer = OrderSagaConsumer(settings, session_factory)
    app.state.consumer = consumer
    await consumer.start()

    relay = OutboxRelay(settings, session_factory)
    app.state.relay = relay
    await relay.start()

    logger.info(
        "order-service started, DATABASE_URL=%s KAFKA_BOOTSTRAP_SERVERS=%s "
        "INVENTORY_GRPC_TARGET=%s order_placed_topic=%s consumer_group=%s",
        db.resolve_database_url(settings.database_url),
        settings.kafka_bootstrap_servers,
        settings.inventory_grpc_target,
        settings.order_placed_topic,
        settings.consumer_group,
    )
    try:
        yield
    finally:
        await relay.stop()
        await consumer.stop()
        await engine.dispose()
        logger.info("order-service shut down")


def create_app() -> FastAPI:
    _configure_logging()
    app = FastAPI(
        title="order-service",
        version="0.1.0",
        # Same contract posture as every other standalone service: the
        # monolith's routes have no trailing slash, so a trailing-slash
        # request should 404 rather than 307-redirect.
        redirect_slashes=False,
        lifespan=lifespan,
    )
    install_exception_handlers(app)
    app.include_router(router)

    @app.get("/health")
    async def health() -> dict[str, object]:
        """Reports the saga consumer's Kafka partition assignment -- the CI
        readiness wait polls this so it doesn't start firing requests (or
        publishing saga-outcome events) at a service whose consumer hasn't
        finished its group-join/rebalance yet."""
        consumer: OrderSagaConsumer = app.state.consumer
        return {
            "status": "ok",
            "consumerPartitionsAssigned": consumer.partitions_assigned,
        }

    return app


app = create_app()
