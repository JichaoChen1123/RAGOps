from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import install_error_handlers
from app.core.ids import uuid7_str
from app.core.logging import configure_logging
from app.persistence.db import Database
from app.schemas.common import ErrorResponse

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    database = Database(resolved_settings.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        configure_logging(resolved_settings.log_level)
        if resolved_settings.auto_create_schema:
            database.create_all()
        yield
        database.dispose()

    application = FastAPI(
        title="RAGOps API",
        version="0.1.0",
        description="Persistent MVP API for dataset and RAG evaluation orchestration.",
        lifespan=lifespan,
        responses={
            404: {"model": ErrorResponse, "description": "Resource not found"},
            409: {"model": ErrorResponse, "description": "Domain state conflict"},
            422: {"model": ErrorResponse, "description": "Request validation failed"},
        },
    )
    application.state.settings = resolved_settings
    application.state.database = database

    @application.middleware("http")
    async def request_context(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("X-Request-ID") or f"req_{uuid7_str()}"
        request.state.request_id = request_id
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "api.request.completed",
            extra={
                "event": "api.request.completed",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            },
        )
        return response

    install_error_handlers(application)
    application.include_router(api_router, prefix="/api/v1")

    @application.get(
        "/health/live",
        tags=["health"],
        summary="Process liveness",
        responses={200: {"content": {"application/json": {"example": {"status": "ok"}}}}},
    )
    def liveness() -> dict[str, str]:
        return {"status": "ok"}

    @application.get(
        "/health/ready",
        tags=["health"],
        summary="Database readiness",
        responses={200: {"content": {"application/json": {"example": {"status": "ready"}}}}},
    )
    def readiness() -> JSONResponse:
        try:
            with database.session() as session:
                session.execute(text("SELECT 1"))
        except Exception:
            logger.exception("health.readiness.failed", extra={"event": "health.readiness.failed"})
            return JSONResponse(status_code=503, content={"status": "not_ready"})
        return JSONResponse(content={"status": "ready"})

    return application


app = create_app()
