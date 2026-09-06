from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.codex_bridge.models import BridgeStatus, GenerateRequest, GenerateResponse
from app.codex_bridge.service import BridgeError, CodexBridgeService


def validate_bridge_token(token: str) -> str:
    if token != token.strip() or len(token.encode("utf-8")) < 32 or len(set(token)) < 8:
        raise ValueError("RAGOPS_CODEX_BRIDGE_TOKEN must be a random token of at least 32 bytes")
    return token


def create_bridge_app(
    token: str,
    *,
    service: CodexBridgeService | None = None,
) -> FastAPI:
    expected_token = validate_bridge_token(token)
    bridge = service or CodexBridgeService()
    app = FastAPI(
        title="RAGOps Codex Host Bridge",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    async def require_bearer(
        authorization: Annotated[str | None, Header()] = None,
    ) -> None:
        scheme, separator, credential = (authorization or "").partition(" ")
        if (
            not separator
            or scheme.lower() != "bearer"
            or not secrets.compare_digest(credential, expected_token)
        ):
            raise BridgeError(
                "CODEX_BRIDGE_UNAUTHORIZED",
                "A valid bridge bearer token is required.",
                status_code=401,
            )

    authentication = Depends(require_bearer)

    @app.exception_handler(BridgeError)
    async def bridge_error_handler(_request: Request, error: BridgeError) -> JSONResponse:
        headers = {"WWW-Authenticate": "Bearer"} if error.status_code == 401 else None
        return JSONResponse(
            status_code=error.status_code,
            headers=headers,
            content={
                "error": {
                    "code": error.code,
                    "message": error.message,
                    "retryable": False,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request,
        _error: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "CODEX_BRIDGE_INVALID_REQUEST",
                    "message": "The bridge request does not match the fixed contract.",
                    "retryable": False,
                }
            },
        )

    @app.get("/v1/status", response_model=BridgeStatus, dependencies=[authentication])
    async def status() -> BridgeStatus:
        return await bridge.status()

    @app.post("/v1/generate", response_model=GenerateResponse, dependencies=[authentication])
    async def generate(payload: GenerateRequest) -> GenerateResponse:
        return await bridge.generate(payload)

    return app
