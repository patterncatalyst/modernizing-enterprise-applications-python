"""An `httpx`-based async client for Apicurio Registry's **v3 REST API**
(`/apis/registry/v3`) -- DRQ-033's pure-Python lane has no Java-style
`apicurio-registry-serdes`/Quarkus extension to lean on, so this module is
the whole client: create-or-resolve an artifact's first version, attach a
COMPATIBILITY rule, register a new version, and fetch a schema by its
global id.

Every request/response shape below was verified BY HAND against a live
`quay.io/apicurio/apicurio-registry:3.3.3` container (the same tag pinned in
`../../../.env.example`'s `APICURIO_IMAGE_TAG` and this module's own docs
below) -- not guessed from documentation:

- `POST /groups/{group}/artifacts` (first-version create), with
  `ifExists=FIND_OR_CREATE_VERSION`, returns `200` whether the artifact is
  brand new or already exists with byte-identical content -- this is the
  idempotent "auto-register" behavior `register_or_resolve` below relies on,
  the Python-native analogue of the Java sibling's
  `apicurio.registry.auto-register=true`.
- `POST /groups/{group}/artifacts/{id}/rules` (attach a COMPATIBILITY rule)
  returns `204` with an empty body on success.
- `POST /groups/{group}/artifacts/{id}/versions` (register a new version)
  returns `200` with the new version's `globalId`/`contentId` on success.
  On a BACKWARD-rule violation, this PINNED 3.3.3 image answers **`400`**
  with an RFC 7807 problem body whose `"name"` is `"RuleViolationException"`
  -- NOT `409`, which is what an OLDER (pre-3.3) registry answers for the
  identical request (the Java sibling's `SchemaCompatibilityTest` docstring
  records the same 409->400 shift across its own registry-version bump).
  `tests/test_compatibility.py` asserts this ACTUAL, live-observed status,
  not a remembered one.
- `GET /ids/globalIds/{globalId}` returns the raw schema content as the
  response body (no wrapper envelope).
"""

from __future__ import annotations

from dataclasses import dataclass
from types import TracebackType

import httpx

DEFAULT_GROUP_ID = "default"


@dataclass(frozen=True)
class RegisteredVersion:
    """The fields of Apicurio's `version` response object this demo
    actually needs -- `artifactId`/`version`/`globalId`/`contentId`."""

    artifact_id: str
    version: str
    global_id: int
    content_id: int


class ApicurioRegistryError(RuntimeError):
    """Raised when Apicurio rejects a request this client did NOT expect
    could be rejected (e.g. attaching a rule, or a 'register or resolve'
    call that isn't deliberately probing a compatibility violation).
    `register_version` -- the one call this demo DOES expect might be
    rejected -- never raises this; it returns the raw `httpx.Response`
    instead so callers can assert on the actual status/body."""


class RegistryClient:
    """A thin async wrapper around Apicurio's v3 REST API. Use as an async
    context manager (`async with RegistryClient(url) as registry: ...`) so
    the underlying `httpx.AsyncClient` connection pool is always closed."""

    def __init__(
        self, base_url: str, *, group_id: str = DEFAULT_GROUP_ID, timeout: float = 10.0
    ) -> None:
        self._group_id = group_id
        self._http = httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> RegistryClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def register_or_resolve(self, artifact_id: str, schema_json: str) -> RegisteredVersion:
        """Idempotently registers `schema_json` as `artifact_id`'s FIRST
        version, or resolves the existing registration if one with
        byte-identical content already exists -- Apicurio's
        `ifExists=FIND_OR_CREATE_VERSION` semantics. Used by
        `app/producer.py` on every publish (cheap after the first call: the
        registry finds the existing version rather than creating a new
        one) and by `tests/test_compatibility.py` to seed each test's v1."""
        resp = await self._http.post(
            f"/groups/{self._group_id}/artifacts",
            params={"ifExists": "FIND_OR_CREATE_VERSION"},
            json={
                "artifactId": artifact_id,
                "artifactType": "AVRO",
                "firstVersion": {
                    "content": {"content": schema_json, "contentType": "application/json"},
                },
            },
        )
        if resp.status_code != 200:
            raise ApicurioRegistryError(
                f"register_or_resolve({artifact_id!r}) failed: "
                f"{resp.status_code} {resp.text}"
            )
        version = resp.json()["version"]
        return RegisteredVersion(
            artifact_id=version["artifactId"],
            version=version["version"],
            global_id=version["globalId"],
            content_id=version["contentId"],
        )

    async def set_compatibility_rule(self, artifact_id: str, config: str = "BACKWARD") -> None:
        """Attaches (or replaces) a `COMPATIBILITY` rule on `artifact_id`.
        `config` is one of Apicurio's compatibility levels (`BACKWARD`,
        `FORWARD`, `FULL`, ...); this demo only ever uses `BACKWARD`,
        matching the Java sibling's `SchemaCompatibilityTest`."""
        resp = await self._http.post(
            f"/groups/{self._group_id}/artifacts/{artifact_id}/rules",
            json={"ruleType": "COMPATIBILITY", "config": config},
        )
        if resp.status_code != 204:
            raise ApicurioRegistryError(
                f"set_compatibility_rule({artifact_id!r}, {config!r}) failed: "
                f"{resp.status_code} {resp.text}"
            )

    async def register_version(
        self, artifact_id: str, schema_json: str, *, version: str | None = None
    ) -> httpx.Response:
        """Registers a NEW version under an EXISTING artifact and returns
        the raw `httpx.Response` -- deliberately NOT raising on a
        compatibility-rule rejection (unlike every other method on this
        client), since `tests/test_compatibility.py` and
        `app/demo_cli.py` need to assert on the ACTUAL observed
        status/body of a rejection, not have it swallowed into an
        exception."""
        body: dict[str, object] = {
            "content": {"content": schema_json, "contentType": "application/json"}
        }
        if version is not None:
            body["version"] = version
        return await self._http.post(
            f"/groups/{self._group_id}/artifacts/{artifact_id}/versions",
            json=body,
        )

    async def get_schema_by_global_id(self, global_id: int) -> str:
        """Fetches the exact WRITER schema registered under `global_id` --
        used by `app/consumer.py` so decoding never assumes the consumer's
        local schema copy matches whatever the producer actually wrote
        with."""
        resp = await self._http.get(f"/ids/globalIds/{global_id}")
        if resp.status_code != 200:
            raise ApicurioRegistryError(
                f"get_schema_by_global_id({global_id}) failed: {resp.status_code} {resp.text}"
            )
        return resp.text
