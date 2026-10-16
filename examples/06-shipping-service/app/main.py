"""shipping-service -- an ORCHESTRATED (DB-backed saga, no gRPC) FastAPI
service on `:8087`: a `payment.captured` consumer starts (or idempotently
no-ops on redelivery for) a saga per order, `app/orchestrator.py` drives it
through `enrich -> dispatch -> book_carrier -> emit` (or compensates on
failure), and this service's OWN transactional outbox + relay publish the
saga's terminal outcome (`shipment.dispatched`/`shipment.failed`). Plus a
read surface, `GET /api/shipments[?orderId=]` / `GET /api/shipments/{id}`,
matching the monolith's contract byte-for-byte. See `../README.md` for the
orchestrated-vs-choreographed story, `../EVENTS.md` for the event contracts,
and `../MIGRATION.md` for the two-phase write-up and the crash-resume
durability upgrade over the Java sibling's in-memory saga coordinator.
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
from app.consumer import PaymentCapturedConsumer
from app.errors import install_exception_handlers
from app.orchestrator import resume_running_sagas
from app.relay import OutboxRelay
from app.routes import router

logger = logging.getLogger("shipping_service")


def _configure_logging() -> None:
    """Rotating file log under `logs/shipping-service.log` alongside console
    output -- non-negotiable for AI-assisted development (house convention,
    see `lgtm-python`'s `references/logging.md`), identical setup to every
    other standalone service's `app/main.py::_configure_logging`."""
    log_dir = Path(os.environ.get("LOG_DIR", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)

    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "shipping-service.log", maxBytes=10 * 1024 * 1024, backupCount=5
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
    logging.getLogger("shipping_service").setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings.from_env()
    engine = db.create_engine(settings.database_url)
    session_factory = db.create_session_factory(engine)
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.settings = settings
    app.state.resume_complete = False
    app.state.resumed_saga_count = 0

    consumer = PaymentCapturedConsumer(settings, session_factory)
    app.state.consumer = consumer
    await consumer.start()

    relay = OutboxRelay(settings, session_factory)
    app.state.relay = relay
    await relay.start()

    # Crash-resume scan (`_docs/17-appendix-d-sagas.md`'s "resuming after a
    # crash is trivial"): any saga left RUNNING/COMPENSATING by a prior
    # process gets its engine kicked again BEFORE this instance reports
    # ready, so `/health`'s `resumeComplete` flag only flips once every
    # in-flight saga as of startup has either finished or is making forward
    # progress again.
    resumed = await resume_running_sagas(session_factory, settings)
    app.state.resumed_saga_count = resumed
    app.state.resume_complete = True

    logger.info(
        "shipping-service started, DATABASE_URL=%s KAFKA_BOOTSTRAP_SERVERS=%s "
        "ORDER_BASE_URL=%s (fallback MONOLITH_BASE_URL=%s) payment_captured_topic=%s "
        "dispatched_topic=%s failed_topic=%s group=%s resumed_sagas=%s",
        db.resolve_database_url(settings.database_url),
        settings.kafka_bootstrap_servers,
        settings.order_base_url,
        settings.monolith_base_url,
        settings.payment_captured_topic,
        settings.shipment_dispatched_topic,
        settings.shipment_failed_topic,
        settings.consumer_group,
        resumed,
    )
    try:
        yield
    finally:
        await relay.stop()
        await consumer.stop()
        await engine.dispose()
        logger.info("shipping-service shut down")


def create_app() -> FastAPI:
    _configure_logging()
    app = FastAPI(
        title="shipping-service",
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
        """Reports Kafka consumer-group partition assignment AND whether the
        startup crash-resume scan has finished -- the CI readiness wait polls
        this so it doesn't start firing `payment.captured` events (or
        reading `/api/shipments`) at an instance that is still resuming a
        saga a prior process left mid-flight."""
        consumer: PaymentCapturedConsumer = app.state.consumer
        return {
            "status": "ok",
            "consumerPartitionsAssigned": consumer.partitions_assigned,
            "resumeComplete": app.state.resume_complete,
            "resumedSagaCount": app.state.resumed_saga_count,
        }

    return app


app = create_app()
