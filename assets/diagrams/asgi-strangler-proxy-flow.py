#!/usr/bin/env python3
"""ch.06 figure: asgi-strangler-proxy-flow -- the Python analog of an
integration-framework content-based router, built from first principles:
`examples/01-strangler-proxy/app/main.py`'s one catch-all Starlette route
and its `proxy_handler`/`_select_backend` functions.

THE FLOW (left to right): a client request hits the one registered route,
`Route("/{path:path}", proxy_handler)`, mounted at the application root.
`_select_backend` matches `request.url.path` -- the FULL path the client
sent -- against six fixed prefixes (`/api/reviews`, `/api/notifications`,
`/api/inventory`, `/api/payments`, `/api/shipments`, `/api/orders`), each
mapped to one operator-configured backend base URL; no match returns
`None`, which `proxy_handler` turns into a real 404. The matched request is
rebuilt: hop-by-hop headers (Host, Content-Length, Transfer-Encoding,
Connection) are stripped, the body is buffered (`await request.body()`) so
`httpx` computes a correct outbound `Content-Length` rather than falling
back to chunked encoding, and `client.send(..., stream=True)` forwards it.
A reachable backend's response -- status code, headers (hop-by-hop
stripped again), and body -- streams back to the client verbatim; an
unreachable backend becomes a real 502, never a swallowed 200.

THE TRAP, named explicitly (see `app/main.py`'s own module docstring and
`CUTOVER.md`): `request.url.path` is the full path; `request.path_params
["path"]` is the route-pattern-relative value with no leading slash. A
future refactor that mounts this route under a prefix and switches the
predicate to the relative value would silently stop matching -- the same
shape of bug a content-based router's path-matching predicate can hide
behind in any framework, just louder here since r07 has no monolith
fallback left to mask it: a real, visible 404.

Sourced from `examples/01-strangler-proxy/app/main.py` (module docstring,
`_select_backend`, `proxy_handler`, the hop-by-hop header comment) and
`examples/01-strangler-proxy/CUTOVER.md`. No codenames; generic/public
names only.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1560, 820

client = node(40, 280, 180, 90, ["Client", "HTTP request"], style="box")
route = node(280, 280, 220, 90,
             ["Starlette catch-all route", 'Route("/{path:path}")', "mounted at app root"], style="accent")
select = node(560, 230, 260, 160,
              ["_select_backend(settings, path)", "matches request.url.path (FULL path)",
               "against 6 fixed prefixes", "no match -> None"], style="accent")

prefixes = [
    ("/api/reviews*", 60),
    ("/api/notifications*", 140),
    ("/api/inventory*", 220),
    ("/api/payments*", 300),
    ("/api/shipments*", 380),
    ("/api/orders*", 460),
]
prefix_nodes = []
PFX_X, PFX_Y0, PFX_W, PFX_H = 880, 40, 220, 56
for label, y in prefixes:
    prefix_nodes.append(node(PFX_X, PFX_Y0 + y, PFX_W, PFX_H, [label, "-> owning backend base URL"], style="box"))

not_found = node(880, 540, 220, 70, ["no match", "-> 404 (no fallback, r07)"], style="ghost")

forward = node(1160, 300, 200, 150,
               ["Forward request", "strip hop-by-hop headers,", "buffer body for correct", "Content-Length, httpx.send()"], style="accent")

upstream_ok = node(1390, 230, 150, 90, ["Backend answers", "stream status/headers/", "body back verbatim"], style="box")
upstream_down = node(1390, 440, 150, 90, ["Backend unreachable", "httpx.HTTPError"], style="ghost")
resp_502 = node(1160, 560, 220, 70, ["502 bridge", "never a swallowed 200"], style="box")

nodes = [client, route, select, not_found, forward, upstream_ok, upstream_down, resp_502] + prefix_nodes

edges = [
    connect(client, route),
    connect(route, select),
] + [connect(select, p) for p in prefix_nodes] + [
    connect(select, not_found, dashed=True, label="None"),
] + [connect(p, forward) for p in prefix_nodes] + [
    connect(forward, upstream_ok),
    connect(forward, upstream_down, dashed=True),
    connect(upstream_down, resp_502, amber=True),
]

trap_band = {"x": 40, "y": 700, "w": 900, "h": 100, "fill": "#fafafa"}
trap = node(60, 712, 860, 80,
            ["THE TRAP: request.path_params[\"path\"] is route-relative, no leading slash --",
             "always match request.url.path (the FULL path), or a future prefix/sub-app mount silently stops matching"],
            style="accent")

notes = [
    {"x": W / 2, "y": 32,
     "text": "ch.06 -- the ASGI strangler proxy's content-based routing, start to finish",
     "anchor": "middle", "bold": True, "size": 16.5},
    {"x": W / 2, "y": 56,
     "text": "one Starlette catch-all route, six fixed full-path prefixes, httpx forwarding -- the Python analog of a content-based router",
     "anchor": "middle", "size": 12, "color": "#555555"},

    {"x": 40, "y": H - 16,
     "text": "Sourced from examples/01-strangler-proxy/app/main.py (_select_backend, proxy_handler) and CUTOVER.md.",
     "anchor": "start", "size": 10, "color": "#777777"},
]

g.emit(
    "asgi-strangler-proxy-flow", W, H,
    bands=[trap_band],
    nodes=nodes + [trap],
    edges=edges,
    notes=notes,
)
