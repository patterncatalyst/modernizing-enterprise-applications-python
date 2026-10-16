"""HTTP Basic auth for `POST /api/reviews` only (Option B, SMELL[ch.15]) --
`GET /api/reviews` and `GET /api/reviews/{id}` stay fully open, with no auth
dependency wired onto them at all, exactly like the monolith's
`get_permissions()` per-view gate.

Verifies the submitted username/password against the SAME shared
`django.contrib.auth` `auth_user` table the monolith seeds (`reviewer` /
`review-pw-r02` -- see `common/management/commands/seed.py`), using Django's
own `pbkdf2_sha256$<iterations>$<salt>$<hash>` hash format. We verify it with
passlib's `django_pbkdf2_sha256` scheme rather than hand-rolling PBKDF2:
getting the iteration count, salt encoding, or comparison out of a
hand-rolled implementation wrong is a real, easy-to-make mistake (CWE-327
territory), and passlib's scheme is purpose-built to match Django's hasher
byte-for-byte and compares in constant time.
"""

from __future__ import annotations

from fastapi import Depends
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.errors import Unauthorized
from app.repository import get_auth_user_by_username

_password_context = CryptContext(schemes=["django_pbkdf2_sha256"])

# A fixed, never-matching hash to verify against when the username doesn't
# exist, so a lookup miss costs roughly the same wall-clock time as a wrong
# password -- cheap insurance against using response timing to enumerate
# valid usernames.
_DUMMY_HASH = _password_context.hash("not-a-real-password")

# `auto_error=False`: FastAPI's `HTTPBasic` default raises its own 401 with
# Starlette's `{"detail": ...}` body on missing/malformed credentials, before
# this dependency's body ever runs. Disabling that lets us raise `Unauthorized`
# ourselves instead, so a missing `Authorization` header gets the SAME uniform
# error body (via `app/errors.py`) as a wrong password would.
_security = HTTPBasic(auto_error=False)


async def require_basic_auth(
    credentials: HTTPBasicCredentials | None = Depends(_security),
    session: AsyncSession = Depends(get_session),
) -> str:
    """FastAPI dependency: raises `Unauthorized` (-> 401, uniform body) on
    missing/invalid credentials, otherwise returns the authenticated
    username. Wire this onto `POST /api/reviews` only."""
    if credentials is None:
        raise Unauthorized("Authentication credentials were not provided.")

    user = await get_auth_user_by_username(session, credentials.username)
    if user is None:
        _password_context.verify(credentials.password, _DUMMY_HASH)
        raise Unauthorized("Invalid username/password.")

    if not user.is_active or not _password_context.verify(credentials.password, user.password):
        raise Unauthorized("Invalid username/password.")

    return credentials.username
