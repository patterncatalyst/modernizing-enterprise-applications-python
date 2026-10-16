"""ASGI entrypoint. Not used by the gunicorn/WSGI container path, kept for parity
with `django-admin startproject` and for anyone who wants to run this under an
ASGI server (uvicorn/daphne) during local development."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_asgi_application()
