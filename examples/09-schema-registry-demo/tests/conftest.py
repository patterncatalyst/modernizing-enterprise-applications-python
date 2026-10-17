"""Testcontainers fixtures for this module's pytest suite: an isolated
Kafka + Apicurio pair per test session -- this demo's own pure-Python
analogue of the Java sibling's Quarkus Dev Services (Kafka + Apicurio
Registry Testcontainers), auto-started for every test here rather than only
for a `%test` profile. Requires a reachable Docker daemon.

There is no `testcontainers.apicurio` module upstream, so `_ApicurioContainer`
below is a small `DockerContainer` subclass -- the generic/manual shape
`testcontainers-python` itself recommends for infra it doesn't ship a
dedicated wrapper for.
"""

from __future__ import annotations

import time
from collections.abc import Iterator

import httpx
import pytest
from testcontainers.community.kafka import KafkaContainer
from testcontainers.core.container import DockerContainer

APICURIO_IMAGE = "quay.io/apicurio/apicurio-registry:3.3.3"


class _ApicurioContainer(DockerContainer):
    """A minimal, in-memory (H2) Apicurio Registry container -- the SAME
    image/tag and storage config as `../../../compose.yaml`'s `apicurio`
    service, just started per test SESSION instead of via compose."""

    def __init__(self, image: str = APICURIO_IMAGE) -> None:
        super().__init__(image)
        self.with_exposed_ports(8080)
        self.with_env("APICURIO_STORAGE_KIND", "sql")
        self.with_env("APICURIO_STORAGE_SQL_KIND", "h2")

    def registry_url(self) -> str:
        host = self.get_container_host_ip()
        port = self.get_exposed_port(8080)
        return f"http://{host}:{port}/apis/registry/v3"

    def wait_until_ready(self, timeout: float = 60.0) -> None:
        """Polls `/apis/registry/v3/system/info` (the same endpoint this
        demo's `demos/demo-schema-registry.sh` waits on) rather than the
        management-port `/health/ready` endpoint `compose.yaml`'s
        healthcheck uses -- the management port (9000) isn't exposed here,
        and `system/info` only answers once the registry is actually
        serving its API."""
        deadline = time.monotonic() + timeout
        url = f"{self.registry_url()}/system/info"
        last_exc: Exception | None = None
        while time.monotonic() < deadline:
            try:
                if httpx.get(url, timeout=2.0).status_code == 200:
                    return
            except httpx.HTTPError as exc:
                last_exc = exc
            time.sleep(1)
        raise RuntimeError(f"Apicurio never became ready at {url}") from last_exc


@pytest.fixture(scope="session")
def kafka_container() -> Iterator[KafkaContainer]:
    # `.with_kraft()` is required for this image tag -- same convention as
    # every other service's `tests/integration/conftest.py` in this project
    # (e.g. `../../07-order-service/tests/integration/conftest.py`).
    with KafkaContainer("confluentinc/cp-kafka:8.3.2").with_kraft() as container:
        yield container


@pytest.fixture(scope="session")
def kafka_bootstrap_servers(kafka_container: KafkaContainer) -> str:
    return kafka_container.get_bootstrap_server()


@pytest.fixture(scope="session")
def apicurio_container() -> Iterator[_ApicurioContainer]:
    container = _ApicurioContainer()
    container.start()
    container.wait_until_ready()
    try:
        yield container
    finally:
        container.stop()


@pytest.fixture(scope="session")
def registry_base_url(apicurio_container: _ApicurioContainer) -> str:
    return apicurio_container.registry_url()
