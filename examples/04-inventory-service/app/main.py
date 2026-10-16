"""inventory-service -- ch.19/DRQ-039/DRQ-041/DRQ-042/DRQ-044 (r04): the
`inventory` bounded context, extracted onto a standalone FastAPI service
(`:8084`) that ALSO runs a net-new gRPC server (`:9004`) -- the
synchronous order<->inventory anti-corruption-layer contract
(`CheckStock`/`Reserve`/`Release`/`GetStock`). See `../README.md` for the
own-schema + gRPC-ACL story and `../MIGRATION.md` for the two-phase write-up.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import grpc
from fastapi import FastAPI

from app import db
from app.cdc_consumer import InventoryCdcConsumer
from app.config import Settings
from app.errors import install_exception_handlers
from app.grpc_gen import inventory_pb2_grpc
from app.grpc_server import InventoryGrpcServiceServicer
from app.routes import router

logger = logging.getLogger("inventory_service")


def _configure_logging() -> None:
    """Rotating file log under `logs/inventory-service.log` alongside
    console output -- non-negotiable for AI-assisted development (house
    convention, see `lgtm-python`'s `references/logging.md`), identical setup
    to `02-review-service`/`03-notification-service`'s `app/main.py`."""
    log_dir = Path(os.environ.get("LOG_DIR", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)

    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "inventory-service.log", maxBytes=10 * 1024 * 1024, backupCount=5
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
    logging.getLogger("inventory_service").setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings.from_env()
    engine = db.create_engine(settings.database_url)
    session_factory = db.create_session_factory(engine)
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.settings = settings
    app.state.grpc_server_listening = False

    # One engine, two protocol surfaces: the gRPC server shares the SAME
    # async session factory the HTTP routes use (app/db.py::get_session),
    # each RPC opening its own short-lived session
    # (app/grpc_server.py::InventoryGrpcServiceServicer).
    grpc_server = grpc.aio.server()
    inventory_pb2_grpc.add_InventoryGrpcServiceServicer_to_server(
        InventoryGrpcServiceServicer(session_factory), grpc_server
    )
    grpc_server.add_insecure_port(f"[::]:{settings.grpc_port}")
    await grpc_server.start()
    app.state.grpc_server = grpc_server
    app.state.grpc_server_listening = True

    cdc_consumer: InventoryCdcConsumer | None = None
    if settings.inventory_cdc_enabled:
        cdc_consumer = InventoryCdcConsumer(settings, session_factory)
        await cdc_consumer.start()
    app.state.cdc_consumer = cdc_consumer

    logger.info(
        "inventory-service started, DATABASE_URL=%s HTTP=:%s GRPC=:%s "
        "INVENTORY_CDC_ENABLED=%s",
        db.resolve_database_url(settings.database_url),
        settings.http_port,
        settings.grpc_port,
        settings.inventory_cdc_enabled,
    )
    try:
        yield
    finally:
        if cdc_consumer is not None:
            await cdc_consumer.stop()
        await grpc_server.stop(grace=None)
        await engine.dispose()
        logger.info("inventory-service shut down")


def create_app() -> FastAPI:
    _configure_logging()
    app = FastAPI(
        title="inventory-service",
        version="0.1.0",
        # Same contract posture as the other services: the monolith's routes
        # have no trailing slash, so a trailing-slash request should 404
        # rather than 307-redirect.
        redirect_slashes=False,
        lifespan=lifespan,
    )
    install_exception_handlers(app)
    app.include_router(router)

    @app.get("/health")
    async def health() -> dict[str, object]:
        """Reports gRPC server bind status, not just HTTP process
        liveness -- a CI readiness wait can poll this so it doesn't start
        issuing gRPC calls at a service whose gRPC server hasn't finished
        binding its port yet."""
        return {
            "status": "ok",
            "grpcServerListening": app.state.grpc_server_listening,
        }

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = Settings.from_env()
    uvicorn.run(app, host="0.0.0.0", port=settings.http_port)
