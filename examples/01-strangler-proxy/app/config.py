"""Operator-configured settings for the strangler proxy.

Every target this proxy forwards to comes from here -- environment variables
read once at process startup -- and NEVER from anything carried on the
inbound request (header, query string, path segment). A dynamic/attacker- or
caller-influenced upstream URL is a classic SSRF vector; pinning the target
set to operator configuration closes it by construction.

r07 DECOMMISSION: this is now a FLAGLESS edge router. Every `*_enabled` flag
and the `monolith_base_url` fallback that this module carried through
r02-r07's reversible cutover window are gone -- there is no more monolith to
fall back to (see `examples/00-monolith/README.md`'s frozen-status section).
Each of the six bounded contexts this proxy ever fronted now has exactly one
owning backend, unconditionally; `app/main.py::_select_backend` returns
`None` for anything that matches no known context, and the caller turns that
into a real `404`, never a silent pass-through. The LAST state this module
carried a flag in is preserved for the historical record in
`examples/01-strangler-proxy/CUTOVER.md` (the order cutover's reversibility
proof) -- not reintroduced here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    """Strangler proxy configuration, read once from the environment. Every
    field below is a fixed, operator-configured backend base URL -- there is
    no boolean flag left to gate any of them; each owning service is always
    the destination for its own path prefix."""

    port: int = 8888
    review_base_url: str = "http://localhost:8001"
    notification_base_url: str = "http://localhost:8002"
    inventory_base_url: str = "http://localhost:8084"
    payment_base_url: str = "http://localhost:8085"
    shipping_base_url: str = "http://localhost:8087"
    order_base_url: str = "http://localhost:8088"

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            port=int(os.environ.get("STRANGLER_PORT", "8888")),
            review_base_url=os.environ.get("STRANGLER_REVIEW_BASE_URL", "http://localhost:8001"),
            notification_base_url=os.environ.get(
                "STRANGLER_NOTIFICATION_BASE_URL", "http://localhost:8002"
            ),
            inventory_base_url=os.environ.get(
                "STRANGLER_INVENTORY_BASE_URL", "http://localhost:8084"
            ),
            payment_base_url=os.environ.get("STRANGLER_PAYMENT_BASE_URL", "http://localhost:8085"),
            shipping_base_url=os.environ.get(
                "STRANGLER_SHIPPING_BASE_URL", "http://localhost:8087"
            ),
            order_base_url=os.environ.get("STRANGLER_ORDER_BASE_URL", "http://localhost:8088"),
        )


settings = Settings.from_env()
