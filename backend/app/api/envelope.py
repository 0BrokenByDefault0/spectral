"""The response envelope every endpoint uses.

    {"status": "ok", "data": {...}}
    {"status": "error", "message": "..."}

Keeping it in one place means an error raised deep in a handler comes back in the same
shape as a success, rather than FastAPI's default `{"detail": ...}`.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class ApiError(Exception):
    """An error meant for the client, with the status code to return it under."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def ok(data: Any) -> dict:
    """Wrap a successful payload."""
    if isinstance(data, BaseModel):
        data = data.model_dump(mode="json")
    return {"status": "ok", "data": data}


def error(message: str) -> dict:
    return {"status": "error", "message": message}


async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=error(exc.message))


async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500, content=error("something went wrong analysing that recording")
    )
