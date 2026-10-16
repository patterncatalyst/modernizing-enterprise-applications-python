"""graphql-gateway -- the GRAPHQL-GATEWAY lane's data-less aggregation
read layer, on `:8090`.

A single Strawberry GraphQL endpoint composes reads across FIVE
already-extracted services -- order (REST), payment (REST), shipping
(REST), review (REST), inventory (gRPC) -- into one queryable graph. The
gateway is stateless: it owns no database, no migrations, no write path, and
it is NEVER routed through the strangler proxy (`01-strangler-proxy`) --
this is its own front door, a sibling surface alongside every other
service's own REST API, not a replacement for any of them.

Endpoints:
  GET  /health   -- liveness (process is up; no downstream probed -- see
                     docstring below for why readiness never couples to
                     downstreams)
  GET  /sdl      -- the GraphQL schema as SDL (the gateway's discovery
                     contract)
  /graphql       -- the GraphQL endpoint (GraphiQL UI in a browser in dev)
"""

from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from strawberry.fastapi import GraphQLRouter

from app.config import Settings
from app.schema import build_schema

logger = logging.getLogger("graphql_gateway")


def _configure_logging() -> None:
    """Rotating file log under `logs/graphql-gateway.log` alongside console
    output -- non-negotiable for AI-assisted development (house convention,
    see `lgtm-python`'s `references/logging.md`), identical setup to every
    other standalone service's `app/main.py::_configure_logging` in this
    project."""
    log_dir = Path(os.environ.get("LOG_DIR", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)

    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "graphql-gateway.log", maxBytes=10 * 1024 * 1024, backupCount=5
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
    logging.getLogger("graphql_gateway").setLevel(logging.INFO)


async def get_context(request: Request) -> dict[str, object]:
    """Strawberry's per-request context -- carries this app's `Settings`
    (fixed operator config, see `app/config.py`'s module docstring) so every
    resolver in `app/schema.py` reaches downstream targets via
    `info.context["settings"]` rather than a module-level global, which is
    what lets tests build an app/schema against a stubbed set of targets."""
    return {"settings": request.app.state.settings}


def create_app() -> FastAPI:
    _configure_logging()
    settings = Settings.from_env()
    schema = build_schema(settings)

    app = FastAPI(
        title="graphql-gateway",
        version="0.1.0",
        description=(
            "Data-less Strawberry GraphQL aggregation gateway -- federates "
            "reads across order/payment/shipping/review (REST) and "
            "inventory (gRPC). Owns no database."
        ),
    )
    app.state.settings = settings

    graphql_app = GraphQLRouter(schema, context_getter=get_context)
    app.include_router(graphql_app, prefix="/graphql")

    @app.get("/health", tags=["ops"])
    async def health() -> dict[str, str]:
        """Liveness: the process is up. Deliberately does NOT probe any of
        the five downstream services -- readiness should reflect 'can I
        accept traffic', not 'are my dependencies healthy'. Coupling
        liveness to downstreams would cause cascading unavailability;
        downstream failures already surface per-field, at query time,
        instead (see `app/clients.py`'s module docstring)."""
        return {"status": "ok", "service": "graphql-gateway"}

    @app.get("/sdl", response_class=PlainTextResponse, tags=["ops"])
    async def sdl() -> str:
        """The gateway's GraphQL schema as SDL -- its discovery contract,
        the GraphQL analog of every REST service's OpenAPI document."""
        return schema.as_str()

    logger.info(
        "graphql-gateway started, order=%s payment=%s shipping=%s review=%s "
        "inventory_grpc=%s max_query_depth=%s max_query_tokens=%s",
        settings.order_service_url,
        settings.payment_service_url,
        settings.shipping_service_url,
        settings.review_service_url,
        settings.inventory_grpc_target,
        settings.max_query_depth,
        settings.max_query_tokens,
    )

    return app


app = create_app()
