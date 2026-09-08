from __future__ import annotations

import hmac
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, Protocol

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.codex_bridge.protocol import CodexAppServerRunner, CodexBridgeError, bridge_error


class BridgeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_token: SecretStr
    sandbox_root: Path
    codex_home: Path
    codex_executable: str = "codex"
    request_timeout_seconds: float = Field(default=180.0, ge=5.0, le=600.0)

    @field_validator("access_token")
    @classmethod
    def strong_access_token(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("bridge access token must contain at least 32 characters")
        return value


class BridgeContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=50_000)


class BridgeGenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = Field(min_length=1, max_length=200)
    prompt: str = Field(min_length=1, max_length=50_000)
    question: str = Field(min_length=1, max_length=20_000)
    context: list[BridgeContext] = Field(default_factory=list, max_length=100)
    reasoning_effort: str | None = Field(default=None, min_length=1, max_length=40)


class Runner(Protocol):
    def inspect(self) -> dict[str, Any]: ...

    def generate(self, request: dict[str, Any]) -> dict[str, Any]: ...


def create_bridge_app(
    config: BridgeConfig,
    *,
    runner_factory: Callable[[], Runner] | None = None,
) -> FastAPI:
    application = FastAPI(
        title="RAGOps Codex ChatGPT Bridge",
        version="1.0.0",
        description="Personal host bridge with a fixed, tool-free evaluation contract.",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    lock = threading.Lock()
    resolved_factory = runner_factory or (
        lambda: CodexAppServerRunner(
            executable=config.codex_executable,
            sandbox_root=config.sandbox_root,
            codex_home=config.codex_home,
            timeout_seconds=config.request_timeout_seconds,
        )
    )

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, _error: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={
                "error": {
                    "code": "CODEX_BRIDGE_INVALID_REQUEST",
                    "message": "The bridge request does not match the fixed contract.",
                    "retryable": False,
                }
            },
        )

    def authenticate(authorization: Annotated[str | None, Header()] = None) -> None:
        expected = f"Bearer {config.access_token.get_secret_value()}"
        if authorization is None or not hmac.compare_digest(authorization, expected):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "BRIDGE_AUTHENTICATION_FAILED"},
            )

    def run_exclusive(operation: Callable[[Runner], dict[str, Any]]) -> dict[str, Any]:
        if not lock.acquire(blocking=False):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={"code": "CODEX_RATE_LIMITED"},
            )
        try:
            return operation(resolved_factory())
        except CodexBridgeError as exc:
            detail: dict[str, Any] = {"code": exc.code, "message": exc.message}
            if exc.reason_code:
                detail["reason_code"] = exc.reason_code
            if exc.diagnostic_id:
                detail["diagnostic_id"] = exc.diagnostic_id
            raise HTTPException(
                status_code=exc.status_code,
                detail=detail,
            ) from None
        except Exception as exc:
            # Do not serialize exception messages: SDK/OS errors may contain secrets.
            failure = bridge_error(
                "CODEX_BRIDGE_INTERNAL_ERROR",
                reason_code="BRIDGE_UNEXPECTED_EXCEPTION",
                diagnostics={"stage": "bridge_operation", "value_type": type(exc).__name__},
            )
            raise HTTPException(
                status_code=500,
                detail={
                    "code": failure.code,
                    "message": failure.message,
                    "reason_code": failure.reason_code,
                    "diagnostic_id": failure.diagnostic_id,
                },
            ) from None
        finally:
            lock.release()

    @application.get("/health/live")
    def liveness() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/v1/status", dependencies=[Depends(authenticate)])
    def codex_status() -> dict[str, Any]:
        return run_exclusive(lambda runner: runner.inspect())

    @application.post("/v1/generate", dependencies=[Depends(authenticate)])
    def generate(payload: BridgeGenerationRequest) -> dict[str, Any]:
        return run_exclusive(lambda runner: runner.generate(payload.model_dump(mode="json")))

    return application
