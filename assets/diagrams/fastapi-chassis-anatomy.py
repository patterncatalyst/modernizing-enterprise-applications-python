#!/usr/bin/env python3
"""ch.27 figure: fastapi-chassis-anatomy -- the cross-cutting concerns every
standalone FastAPI service in this project wires through its own app/main.py
lifespan, laid out as the path a process actually takes from import to
serving traffic: config resolved once in Settings.from_env(), logging
configured before anything else can log, lifespan wiring up the owned
pieces (db engine, Kafka consumer/relay where the service has one),
request-time concerns (errors.py's uniform mapping, the /health route) on
six of eight services, and the narrow, named exception to each convention
(tenacity in shipping's enrich_client.py; OTel/metrics wired nowhere yet).

Sourced from examples/07-order-service/app/config.py (frozen dataclass,
from_env()), examples/07-order-service/app/main.py (_configure_logging,
lifespan), examples/02-review-service/app/db.py (the pre-dataclass
os.environ.get convention, no config.py at all), examples/07-order-service/
app/errors.py (ApiError uniform JSON body), examples/08-graphql-gateway/
app/main.py (liveness-only /health, no downstream probe), examples/06-
shipping-service/app/enrich_client.py (tenacity retry, the one resilience
wrapper in this system).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1320, 760

band = {"x": 20, "y": 50, "w": 1280, "h": 600, "label": "Inside one FastAPI service, startup to request", "fill": "#fafafa"}

n_entry = node(540, 10, 240, 40, ["uvicorn ASGI entry point"], style="box")

n_config = node(60, 110, 300, 110,
                ["config.py: frozen @dataclass Settings", "Settings.from_env() reads os.environ", "at call time -- 7 of 8 services"], style="accent")

n_logging = node(400, 110, 300, 110,
                 ["_configure_logging()", "stdlib logging.handlers.RotatingFileHandler", "logs/<service>.log + console -- all 8"], style="accent")

n_lifespan = node(740, 110, 300, 110,
                   ["@asynccontextmanager lifespan()", "wires db engine, starts owned", "Kafka consumer(s) + outbox relay"], style="accent")

n_errors = node(60, 300, 290, 110,
                 ["errors.py: ApiError base class", "uniform {error, message, timestamp}", "6 of 8 (absent: proxy, gateway)"], style="user")

n_health = node(390, 300, 290, 110,
                 ["GET /health: liveness only", "process-is-up, no downstream probed", "6 of 8 (absent: proxy, review)"], style="user")

n_container = node(720, 300, 320, 110,
                    ["Containerfile", "UBI-based image build", "8 of 8 -- every service ships one"], style="accent")

n_resilience = node(60, 490, 460, 120,
                     ["tenacity retry + exponential backoff", "examples/06-shipping-service/app/enrich_client.py", "ONE call site, ONE service -- not a shared wrapper"], style="box")

n_deferred = node(560, 490, 480, 120,
                   ["DEFERRED: OpenTelemetry/Prometheus (ch.30 adds 3 services),", "pybreaker circuit breaker, bulkhead isolation,", "a shared chassis library -- named, not built"], style="ghost")

nodes = [n_entry, n_config, n_logging, n_lifespan, n_errors, n_health,
         n_container, n_resilience, n_deferred]

edges = [
    connect(n_entry, n_config),
    connect(n_entry, n_logging),
    connect(n_entry, n_lifespan),
    connect(n_lifespan, n_errors, label="routes registered"),
    connect(n_lifespan, n_health, label="route registered"),
    connect(n_config, n_container, dashed=True, label="baked at build"),
    connect(n_errors, n_resilience, dashed=True, label="only outbound call wrapped"),
    connect(n_resilience, n_deferred, dashed=True, label="not yet justified"),
]

notes = [
    {"x": W / 2, "y": 30, "text": "ch.27 -- the chassis is convention, not a framework feature: every box above is code someone wrote, not a dependency someone added",
     "anchor": "middle", "bold": True, "size": 14},
    {"x": 40, "y": H - 40, "text": "Config and logging are the floor every service shares identically; health, errors, and resilience are opt-in and partial by actual count, not by oversight.",
     "anchor": "start", "size": 11, "color": "#555555"},
    {"x": 40, "y": H - 22, "text": "No service imports a shared chassis package -- each file above is copied and adapted per service, the same convention repeated eight times.",
     "anchor": "start", "size": 11, "color": "#555555"},
]

g.emit(
    "fastapi-chassis-anatomy", W, H,
    bands=[band],
    nodes=nodes,
    edges=edges,
    notes=notes,
)
