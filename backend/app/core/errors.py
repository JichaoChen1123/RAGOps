from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class DomainError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int,
        details: dict[str, Any] | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        self.retryable = retryable


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    retryable: bool = False,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
                "request_id": getattr(request.state, "request_id", "unknown"),
                "retryable": retryable,
            }
        },
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        return _error_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
            retryable=exc.retryable,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        errors = []
        response_code = "VALIDATION_ERROR"
        for error in exc.errors():
            location = [part for part in error["loc"] if part != "body"]
            row_index = next((part for part in location if isinstance(part, int)), None)
            sample_id = None
            if row_index is not None and isinstance(exc.body, dict):
                samples = exc.body.get("samples")
                if isinstance(samples, list) and row_index < len(samples):
                    raw_sample = samples[row_index]
                    if isinstance(raw_sample, dict) and isinstance(raw_sample.get("sample_id"), str):
                        sample_id = raw_sample["sample_id"]
            message = error["msg"]
            item_code = "VALIDATION_ERROR"
            if location and location[-1] == "schema_version" and error["type"] == "literal_error":
                item_code = "UNSUPPORTED_SCHEMA_VERSION"
                response_code = item_code
            elif "AMBIGUOUS_EXECUTION_CONFIG" in message:
                response_code = "AMBIGUOUS_EXECUTION_CONFIG"
                item_code = "AMBIGUOUS_EXECUTION_CONFIG"
            elif "AMBIGUOUS_SCHEMA_FIELDS" in message:
                response_code = "AMBIGUOUS_SCHEMA_FIELDS"
                item_code = "AMBIGUOUS_SCHEMA_FIELDS"
            errors.append(
                {
                    "row": row_index + 1 if row_index is not None else None,
                    "sample_id": sample_id,
                    "field": ".".join(str(part) for part in location),
                    "code": item_code,
                    "message": message,
                    "type": error["type"],
                }
            )
        details: dict[str, Any] = {"errors": errors}
        if any(item["code"] == "UNSUPPORTED_SCHEMA_VERSION" for item in errors):
            details["supported_versions"] = ["1.0", "2.0"]
        return _error_response(
            request,
            status_code=422,
            code=response_code,
            message="Request validation failed.",
            details=details,
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "api.request.failed",
            exc_info=exc,
            extra={
                "event": "api.request.failed",
                "request_id": getattr(request.state, "request_id", "unknown"),
            },
        )
        return _error_response(
            request,
            status_code=500,
            code="INTERNAL_ERROR",
            message="The server could not complete the request.",
        )
