"""Proves Apicurio's BACKWARD compatibility rule against the v1/v2/v3
fixtures under `tests/resources/` -- the pure-Python sibling of the Java
`SchemaCompatibilityTest`. v1 registers cleanly, v2 (adds `giftMessage` WITH
a default) is ACCEPTED, and v3 (retypes `totalCents` long -> string) is
REJECTED.

Talks to Apicurio's v3 REST API directly via `app/registry_client.py`
(plain HTTP, no SDK) against the SAME Testcontainers-provisioned registry
(`tests/conftest.py`) `tests/test_roundtrip.py` uses. Every status code
asserted below was LIVE-VERIFIED by hand against
`quay.io/apicurio/apicurio-registry:3.3.3` before being encoded here -- see
`app/registry_client.py`'s module docstring for the 400-vs-409 history
across registry versions this test deliberately does NOT assume away.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from app.registry_client import RegistryClient

_SCHEMAS_DIR = Path(__file__).resolve().parents[1] / "schemas"
_RESOURCES_DIR = Path(__file__).resolve().parent / "resources"

_V1_SCHEMA = (_SCHEMAS_DIR / "order-placed-v1.avsc").read_text()
_V2_SCHEMA = (_RESOURCES_DIR / "order-placed-v2-backward-compatible.avsc").read_text()
_V3_SCHEMA = (_RESOURCES_DIR / "order-placed-v3-incompatible.avsc").read_text()


@pytest.mark.asyncio
async def test_v1_registers_and_v2_is_backward_compatible_but_v3_is_rejected(
    registry_base_url: str,
) -> None:
    # A per-test-run artifact id: this fixture's Apicurio container is
    # session-scoped, so a fixed artifact id would collide across repeated
    # local `pytest -k` re-runs within the same session.
    artifact_id = f"order-placed-compat-test-{uuid.uuid4().hex[:8]}"

    async with RegistryClient(registry_base_url) as registry:
        # 1. Register v1 as a brand-new artifact.
        v1 = await registry.register_or_resolve(artifact_id, _V1_SCHEMA)
        assert v1.version == "1"
        assert v1.artifact_id == artifact_id

        # 2. Apply the BACKWARD compatibility rule to this artifact.
        await registry.set_compatibility_rule(artifact_id, config="BACKWARD")

        # 3. v2 (adds giftMessage WITH a default) MUST be accepted.
        v2_response = await registry.register_version(artifact_id, _V2_SCHEMA, version="2")
        assert v2_response.status_code == 200
        assert v2_response.json()["version"] == "2"

        # 4. v3 (retypes totalCents long -> string) MUST be rejected: 400 +
        # RuleViolationException on the pinned 3.3.3 image (409 on registry
        # versions before 3.3 -- see app/registry_client.py's docstring).
        v3_response = await registry.register_version(artifact_id, _V3_SCHEMA, version="3")
        assert v3_response.status_code == 400
        assert v3_response.json()["name"] == "RuleViolationException"
