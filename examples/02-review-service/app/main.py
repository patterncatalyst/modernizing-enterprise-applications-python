"""review-service -- ch.15/DRQ-009 Phase B (final): the review bounded
context extracted from `00-monolith` onto a standalone FastAPI service on
`:8001`. See `../README.md` for the Phase A -> Phase B story and
`../MIGRATION.md` for the measured before/after.
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
from app.errors import install_exception_handlers
from app.routes import router

logger = logging.getLogger("review_service")


def _configure_logging() -> None:
    """Rotating file log under `logs/review-service.log` alongside console
    output -- non-negotiable for AI-assisted development (house convention,
    see `lgtm-python`'s `references/logging.md`): console output alone
    scrolls away and can't be grep'd after a crash or a failed test run."""
    log_dir = Path(os.environ.get("LOG_DIR", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)

    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "review-service.log", maxBytes=10 * 1024 * 1024, backupCount=5
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
    logging.getLogger("review_service").setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    engine = db.create_engine()
    app.state.engine = engine
    app.state.session_factory = db.create_session_factory(engine)
    logger.info("review-service started, DATABASE_URL=%s", db.resolve_database_url())
    try:
        yield
    finally:
        await engine.dispose()
        logger.info("review-service shut down")


def create_app() -> FastAPI:
    _configure_logging()
    app = FastAPI(
        title="review-service",
        version="0.1.0",
        # The monolith's contract (and the ported Newman collection) uses
        # paths with NO trailing slash (`/api/reviews/{id}`, not
        # `/api/reviews/{id}/`) -- disable Starlette's default redirect so a
        # trailing-slash request 404s instead of 307-redirecting (which
        # would turn a POST into a GET on redirect in some clients and break
        # the contract either way).
        redirect_slashes=False,
        lifespan=lifespan,
    )
    install_exception_handlers(app)
    app.include_router(router)
    return app


app = create_app()
