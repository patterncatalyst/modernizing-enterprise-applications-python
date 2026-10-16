"""payment-service -- a choreographed (no orchestrator) FastAPI service on
`:8085`: an idempotent `aiokafka` consumer captures payment off the
`order.placed` event and emits `payment.captured`/`payment.declined` via this
service's OWN transactional outbox, into this service's OWN `payment`
Postgres schema. Plus a read surface, `GET /api/payments[?orderId=]` /
`GET /api/payments/{id}`, matching the monolith's contract byte-for-byte. See
`../README.md` for the own-schema/choreography story, `../EVENTS.md` for the
event contracts, and `../MIGRATION.md` for the two-phase write-up.
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
from app.consumer import OrderPlacedConsumer
from app.errors import install_exception_handlers
from app.relay import OutboxRelay
from app.routes import router

logger = logging.getLogger("payment_service")


def _configure_logging() -> None:
    """Rotating file log under `logs/payment-service.log` alongside console
    output -- non-negotiable for AI-assisted development (house convention,
    see `lgtm-python`'s `references/logging.md`), identical setup to
    `03-notification-service`'s `app/main.py::_configure_logging`."""
    log_dir = Path(os.environ.get("LOG_DIR", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)

    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "payment-service.log", maxBytes=10 * 1024 * 1024, backupCount=5
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
    logging.getLogger("payment_service").setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings.from_env()
    engine = db.create_engine(settings.database_url)
    session_factory = db.create_session_factory(engine)
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.settings = settings

    consumer = OrderPlacedConsumer(settings, session_factory)
    app.state.consumer = consumer
    await consumer.start()

    relay = OutboxRelay(settings, session_factory)
    app.state.relay = relay
    await relay.start()

    logger.info(
        "payment-service started, DATABASE_URL=%s KAFKA_BOOTSTRAP_SERVERS=%s "
        "order_placed_topic=%s captured_topic=%s declined_topic=%s group=%s",
        db.resolve_database_url(settings.database_url),
        settings.kafka_bootstrap_servers,
        settings.order_placed_topic,
        settings.payment_captured_topic,
        settings.payment_declined_topic,
        settings.consumer_group,
    )
    try:
        yield
    finally:
        await relay.stop()
        await consumer.stop()
        await engine.dispose()
        logger.info("payment-service shut down")


def create_app() -> FastAPI:
    _configure_logging()
    app = FastAPI(
        title="payment-service",
        version="0.1.0",
        # Same contract posture as notification-/review-service: the
        # monolith's routes have no trailing slash, so a trailing-slash
        # request should 404 rather than 307-redirect.
        redirect_slashes=False,
        lifespan=lifespan,
    )
    install_exception_handlers(app)
    app.include_router(router)

    @app.get("/health")
    async def health() -> dict[str, object]:
        """Reports Kafka consumer-group partition assignment, not just
        process liveness -- the CI readiness wait polls this so it doesn't
        start firing requests at a service whose consumer hasn't finished
        its group-join/rebalance yet (a request that would otherwise see an
        empty result even after a matching `order.placed` event has been
        published)."""
        consumer: OrderPlacedConsumer = app.state.consumer
        return {
            "status": "ok",
            "consumerPartitionsAssigned": consumer.partitions_assigned,
        }

    return app


app = create_app()
