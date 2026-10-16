"""Uniform error-mapping surface -- ported from `03-notification-service`'s
`app/errors.py` (itself ported from `02-review-service`'s), the FastAPI
sibling of the monolith's `common/exceptions.py`. Every error response this
service returns is the same shape the Newman equivalence suite asserts on:

    {"error": "<CODE>", "message": ..., "timestamp": "..."}

`ResourceNotFound` backs `GET /api/payments/{id}` for an unknown id, same
precedent as `02-review-service`'s `GET /api/reviews/{review_id}`. Request
query/body validation failures map to `400 VALIDATION_FAILED`, matching
DRF's generic "status 400 -> VALIDATION_FAILED" rule.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    """Base class for domain exceptions mapped onto the uniform error body."""

    status_code: int = 500
    error_code: str = "ERROR"

    def __init__(self, message: Any):
        super().__init__(str(message))
        self.message = message


class ResourceNotFound(ApiError):
    status_code = 404
    error_code = "NOT_FOUND"


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _error_body(error_code: str, message: Any) -> dict[str, Any]:
    return {"error": error_code, "message": message, "timestamp": _now_iso()}


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code, content=_error_body(exc.error_code, exc.message)
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # FastAPI's own default is 422; the monolith's contract (DRF's
        # generic 400-status-code -> VALIDATION_FAILED rule) uses 400, so
        # this handler both remaps the status code AND the body shape.
        return JSONResponse(status_code=400, content=_error_body("VALIDATION_FAILED", exc.errors()))

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # Catch-all for anything still raised as a plain HTTPException (e.g.
        # an unmatched route's framework-level 404) -- still gets the
        # uniform body rather than Starlette's default {"detail": ...}.
        error_code = "NOT_FOUND" if exc.status_code == 404 else "ERROR"
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(error_code, exc.detail),
            headers=exc.headers,
        )
