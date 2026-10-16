"""Operator-configured settings for the strangler proxy.

Every target this proxy forwards to comes from here -- environment variables
read once at process startup -- and NEVER from anything carried on the
inbound request (header, query string, path segment). A dynamic/attacker- or
caller-influenced upstream URL is a classic SSRF vector; pinning the target
set to operator configuration closes it by construction.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    """Strangler proxy configuration, read once from the environment."""

    port: int = 8888
    review_enabled: bool = False
    monolith_base_url: str = "http://localhost:8000"
    review_base_url: str = "http://localhost:8001"
    notification_enabled: bool = False
    notification_base_url: str = "http://localhost:8002"

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            port=int(os.environ.get("STRANGLER_PORT", "8888")),
            review_enabled=_env_bool("STRANGLER_REVIEW_ENABLED", False),
            monolith_base_url=os.environ.get(
                "STRANGLER_MONOLITH_BASE_URL", "http://localhost:8000"
            ),
            review_base_url=os.environ.get("STRANGLER_REVIEW_BASE_URL", "http://localhost:8001"),
            notification_enabled=_env_bool("STRANGLER_NOTIFICATION_ENABLED", False),
            notification_base_url=os.environ.get(
                "STRANGLER_NOTIFICATION_BASE_URL", "http://localhost:8002"
            ),
        )


settings = Settings.from_env()
