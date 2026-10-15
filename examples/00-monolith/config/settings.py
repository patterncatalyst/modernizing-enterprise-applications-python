"""Django settings for the r01 walking-skeleton monolith.

This module is the Python sibling of the Java book's `application.yml`: one
Spring Boot module, one shared Postgres schema, six bounded-context apps living
in the same process. See `SMELLS.md` (SMELL[ch.18]) for why that single shared
schema is deliberate, not an oversight.
"""

import os
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Core / security
# ---------------------------------------------------------------------------

# Insecure default is fine for a local demo; override via DJANGO_SECRET_KEY in
# any environment that matters (CI, a real deployment).
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY", "insecure-demo-key-do-not-use-in-production-" + "x" * 20
)

DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() == "true"

ALLOWED_HOSTS = [h for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",") if h]

# ---------------------------------------------------------------------------
# Applications
#
# SMELL[ch.18]: all six bounded contexts (order/inventory/payment/shipping/
# notification/review) are Django apps in ONE project, sharing ONE Postgres
# schema (see DATABASES below) and migrating together. A decomposed system
# gives each context its own service, its own database, and its own
# deployment lifecycle -- see ch.18 (shared data -> owned data) and ch.19 (CDC
# backfill + decommission) for the cure, chapter by chapter, context by
# context.
# ---------------------------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "common.apps.CommonConfig",
    "order.apps.OrderConfig",
    "inventory.apps.InventoryConfig",
    "payment.apps.PaymentConfig",
    "shipping.apps.ShippingConfig",
    "notification.apps.NotificationConfig",
    "review.apps.ReviewConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
            ],
        },
    },
]

# ---------------------------------------------------------------------------
# Database -- single shared Postgres schema for every app (SMELL[ch.18]).
#
# Env-overridable via DATABASE_URL so pytest-django/CI point at their own
# throwaway database without this module ever hard-coding a dependency on the
# INFRA lane's compose stack being up. Defaults match that compose stack
# (infra/compose.yaml): postgresql://monolith:monolith@localhost:5432/monolith.
# ---------------------------------------------------------------------------

_DEFAULT_DATABASE_URL = "postgresql://monolith:monolith@localhost:5432/monolith"
_database_url = os.environ.get("DATABASE_URL", _DEFAULT_DATABASE_URL)
_parsed_db_url = urlparse(_database_url)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": (_parsed_db_url.path or "/monolith").lstrip("/"),
        "USER": _parsed_db_url.username or "monolith",
        "PASSWORD": _parsed_db_url.password or "monolith",
        "HOST": _parsed_db_url.hostname or "localhost",
        "PORT": _parsed_db_url.port or 5432,
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# This API's contract (and the ported Newman collection) uses paths with NO
# trailing slash (`/api/inventory/{sku}`, not `/api/inventory/{sku}/`), so
# each app's urls.py intentionally starts its detail route with "/" against
# a slash-less include() prefix in config/urls.py. That trips Django's
# "routes shouldn't start with /" style check (urls.W002) even though the
# resulting, fully-assembled routes are correct -- silence it rather than
# accepting Django's conventional trailing slash and the 301-redirect/POST
# semantics that would come with it.
SILENCED_SYSTEM_CHECKS = ["urls.W002"]

# ---------------------------------------------------------------------------
# Internationalization (defaults are fine for a demo system)
# ---------------------------------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

# ---------------------------------------------------------------------------
# Django REST Framework + OpenAPI (drf-spectacular)
# ---------------------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    "EXCEPTION_HANDLER": "common.exceptions.api_exception_handler",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Modernizing Enterprise Applications -- Monolith API",
    "DESCRIPTION": (
        "The r01 'before' monolith: six bounded contexts (order, inventory, "
        "payment, shipping, notification, review) in one Django project, one "
        "shared Postgres schema. See SMELLS.md."
    ),
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

# ---------------------------------------------------------------------------
# Structured file logging -- non-negotiable for AI-assisted development (see
# lgtm-python house convention). Console logging alone scrolls away; a
# rotating file under logs/ survives a crash or a failed test run so it can be
# grep'd after the fact.
# ---------------------------------------------------------------------------

LOG_DIR = Path(os.environ.get("LOG_DIR", BASE_DIR / "logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "%(asctime)s %(levelname)-5s [%(name)s] (%(threadName)s) %(message)s",
        },
        "console": {
            "format": "%(asctime)s %(levelname)-5s %(message)s",
        },
    },
    "handlers": {
        "file": {
            "level": "DEBUG",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOG_DIR / "monolith.log"),
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "verbose",
        },
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "console",
        },
    },
    "root": {
        "handlers": ["file", "console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {"handlers": ["file", "console"], "level": "INFO", "propagate": False},
        "order": {"level": "DEBUG", "propagate": True},
        "notification": {"level": "DEBUG", "propagate": True},
    },
}
