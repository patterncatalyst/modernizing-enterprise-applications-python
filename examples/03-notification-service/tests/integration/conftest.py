"""Testcontainers fixtures for the `order.placed` consumer idempotency proof
-- an isolated Kafka + Postgres pair per test session (DOES NOT touch
whatever `DATABASE_URL` the throwaway Postgres used by `tests/unit/` points
at). Requires a reachable Docker daemon (`/var/run/docker.sock`); run with
`uv run pytest -m integration`.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

# `testcontainers.kafka`/`testcontainers.postgres` are deprecated redirects
# in testcontainers 4.15.0 -- import the non-deprecated `community` modules
# directly.
from testcontainers.community.kafka import KafkaContainer
from testcontainers.community.postgres import PostgresContainer

_SERVICE_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:18.6-alpine") as container:
        yield container


@pytest.fixture(scope="session")
def kafka_container() -> Iterator[KafkaContainer]:
    # `.with_kraft()` is required for this image tag: Confluent Platform
    # 8.x's `cp-kafka` image dropped the legacy ZooKeeper boot path entirely
    # (it fails fast with "KAFKA_PROCESS_ROLES is not set" otherwise) --
    # testcontainers' `KafkaContainer` defaults to the ZooKeeper
    # configuration unless this is called explicitly.
    with KafkaContainer("confluentinc/cp-kafka:8.3.2").with_kraft() as container:
        yield container


@pytest.fixture(scope="session")
def database_url(postgres_container: PostgresContainer) -> str:
    # testcontainers' PostgresContainer URL defaults to the psycopg2 driver
    # scheme (`postgresql+psycopg2://`); normalize back to the plain
    # `postgresql://` scheme `app/db.py::resolve_database_url` expects --
    # same convention as `lgtm-python`'s `snippets/conftest-example.py`.
    raw = postgres_container.get_connection_url()
    return raw.replace("postgresql+psycopg2://", "postgresql://")


@pytest.fixture(scope="session")
def kafka_bootstrap_servers(kafka_container: KafkaContainer) -> str:
    return kafka_container.get_bootstrap_server()


@pytest.fixture(scope="session", autouse=True)
def _migrated_schema(database_url: str) -> None:
    """Runs this service's own Alembic migration against the Testcontainers
    Postgres, in-process, before any integration test executes -- the
    sibling of the CI gate's `alembic upgrade head` step. `migrations/env.py`
    reads `DATABASE_URL` from the environment at migration-run time, so it is
    set here for the duration of the test session."""
    os.environ["DATABASE_URL"] = database_url
    config = Config(str(_SERVICE_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_SERVICE_ROOT / "migrations"))
    command.upgrade(config, "head")
