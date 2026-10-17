#!/usr/bin/env python3
"""ch.33 figure: openshift-image-delivery -- the podman-on-host -> integrated
-registry -> in-cluster-pull loop `openshift/build-and-push.sh` and
`openshift/install-infra.sh` run, replacing `minikube image load` (DRQ-108).
Python has no `quarkus-openshift`-style S2I path, so the image is built on
the host, not inside the cluster. `--mirror-infra` pulls the upstream
postgres/kafka images and re-pushes them into the same registry namespace,
because the CRC VM has no Docker Hub egress. The monolith image is built
too, but only ever runs as the bootstrap Job's container (DRQ-111), never as
its own Deployment.

Sourced from openshift/build-and-push.sh, openshift/install-infra.sh,
openshift/helm/mea/values.yaml (image.registry, monolith.image), and
openshift/helm/mea/templates/bootstrap-job.yaml.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, os.path.dirname(__file__))
import generate_diagram as g
from _lib import node, connect

g.OUT = os.path.dirname(__file__)

W, H = 1540, 660

band_host = {"x": 30, "y": 40, "w": 560, "h": 580, "fill": "#fafafa",
             "label": "host -- podman (no quarkus-openshift S2I path for Python)"}
band_cluster = {"x": 630, "y": 40, "w": 880, "h": 580, "fill": "#fafafa",
                 "label": "project: mea -- OpenShift Local (CRC)"}

build = node(60, 90, 220, 72,
             ["podman build", "8 service Containerfiles"],
             style="box")
login = node(320, 90, 220, 72,
             ["podman login", "-p $(oc whoami -t), --tls-verify=false"],
             style="box")
push = node(60, 200, 220, 72,
            ["podman push", "build-and-push.sh"],
            style="accent")
monolith = node(320, 200, 220, 72,
                 ["podman build + push", "monolith image (bootstrap Job only)"],
                 style="sub")
mirror = node(60, 310, 480, 110,
              ["--mirror-infra", "pull postgres:18.6-alpine + apache/kafka:4.3.1, re-push",
               "(the CRC VM has no Docker Hub egress)"],
              style="sub")

route = node(670, 90, 280, 72,
             ["registry default Route", "exposed by install-infra.sh"],
             style="box")
imagestream = node(670, 200, 280, 90,
                    ["ImageStream tags", "mea/<svc>:v1 (+ monolith:v1)"],
                    style="accent")
pull = node(670, 330, 280, 100,
            ["Deployment image pull", "image-registry.openshift-image-registry.svc:5000/mea",
             "imagePullPolicy: IfNotPresent"],
            style="box")
job = node(670, 470, 280, 72,
           ["bootstrap Job", "pulls mea/monolith:v1 (DRQ-111)"],
           style="sub")
infra_pull = node(1000, 330, 280, 100,
                   ["postgres / kafka image pull", "same registry, SA mea-infra, nonroot-v2"],
                   style="sub")

nodes = [build, login, push, monolith, mirror, route, imagestream, pull, job, infra_pull]

edges = [
    connect(build, push, amber=True),
    connect(login, push, dashed=True, label="oc whoami / oc whoami -t"),
    connect(monolith, push, amber=True),
    connect(push, route, amber=True, label="podman push --tls-verify=false"),
    connect(mirror, route, dashed=True, label="postgres + kafka re-push"),
    connect(route, imagestream),
    connect(imagestream, pull, dashed=True, label="in-cluster Service DNS, not the push host"),
    connect(imagestream, job, dashed=True),
    connect(imagestream, infra_pull, dashed=True),
]

notes = [
    {"x": W / 2, "y": 24, "text": "ch.33 -- image delivery: podman build+push on the host, pulled in-cluster from the integrated registry",
     "anchor": "middle", "bold": True, "size": 15},
    {"x": 60, "y": H - 36,
     "text": "No in-cluster BuildConfig: 8 host-built Python images push faster and simpler than a Docker-strategy S2I build per service (rejected, _plans/r11-build-plan.md A.3).",
     "anchor": "start", "size": 11, "color": "#555555"},
    {"x": 60, "y": H - 18,
     "text": "On a cluster WITH Docker Hub egress, drop --mirror-infra and point values.yaml's postgres.image / kafka.image at the upstream refs instead.",
     "anchor": "start", "size": 11, "color": "#555555"},
]

g.emit(
    "openshift-image-delivery", W, H,
    bands=[band_host, band_cluster],
    nodes=nodes,
    edges=edges,
    notes=notes,
)
