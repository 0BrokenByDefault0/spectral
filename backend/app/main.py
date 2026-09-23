"""FastAPI app: CORS, routes, and the shared response envelope.

    uvicorn app.main:app --reload
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import analyze
from app.api.envelope import ApiError, error, handle_api_error, handle_unexpected, ok

#: Comma-separated in the environment; the Next.js dev server by default.
ALLOWED_ORIGINS = os.environ.get(
    "VOXCHAIN_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
).split(",")

app = FastAPI(title="VoxChain", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in ALLOWED_ORIGINS if origin.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(analyze.router)
app.add_exception_handler(ApiError, handle_api_error)
app.add_exception_handler(Exception, handle_unexpected)


@app.exception_handler(StarletteHTTPException)
async def handle_http_exception(request, exc: StarletteHTTPException) -> JSONResponse:
    """Keep FastAPI's own 404s and 405s in the project's envelope."""
    return JSONResponse(status_code=exc.status_code, content=error(str(exc.detail)))


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request, exc: RequestValidationError) -> JSONResponse:
    missing = ", ".join(str(err["loc"][-1]) for err in exc.errors())
    return JSONResponse(status_code=422, content=error(f"missing or invalid: {missing}"))


@app.get("/health")
def health() -> dict:
    return ok({"status": "healthy"})
