# r01 walking-skeleton monolith -- UBI 10, multi-stage, non-root.
#
# UBI 10 publishes only the `-minimal` Python 3.14 image (no full/dev variant
# with a package manager), so both stages use it. That's fine here: every
# dependency in pyproject.toml ships a prebuilt (often manylinux) wheel --
# psycopg[binary] included -- so `uv sync` never needs a C compiler. The `uv`
# binary itself is copied in from its official distroless image rather than
# installed via a shell script, since the minimal image has no curl/microdnf.
#
# Exact tag verified with `skopeo list-tags
# docker://registry.access.redhat.com/ubi10/python-314-minimal` (newest
# non-source tag as of 2026-10-15). Re-verify before bumping.
ARG UBI_PYTHON_IMAGE=registry.access.redhat.com/ubi10/python-314-minimal:10.2-1791928506
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.13.1

FROM ${UV_IMAGE} AS uv

FROM ${UBI_PYTHON_IMAGE} AS builder
COPY --from=uv /uv /uvx /usr/local/bin/

WORKDIR /app

# Resolve dependencies first so dependency installs cache independently of
# application code changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project --no-dev

COPY . .
RUN uv sync --locked --no-dev

FROM ${UBI_PYTHON_IMAGE}

WORKDIR /app
COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings

# Non-root, OpenShift/arbitrary-UID compatible: run as a fixed non-root UID
# with GID 0, and make the app directory group-writable (matches the Red Hat
# "support arbitrary user IDs" convention) instead of creating a user with
# useradd, which the minimal image doesn't ship shadow-utils for. The base
# image already defaults to UID 1001, so switch to root just long enough to
# fix ownership/permissions on the files copied in from the builder stage.
USER root
RUN chgrp -R 0 /app && chmod -R g=u /app
USER 1001:0

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
