from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ModelContext(StrictModel):
    position: int = Field(ge=1)
    text: str = Field(max_length=50_000)

    @field_validator("text")
    @classmethod
    def non_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("context text must not be blank")
        return value


class GenerationConfig(StrictModel):
    model: str = Field(min_length=1, max_length=200)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    top_p: float = Field(default=1.0, gt=0.0, le=1.0)
    max_output_tokens: int = Field(default=512, ge=1, le=8192)
    stop: list[str] = Field(default_factory=list, max_length=8)
    seed: int | None = None

    @field_validator("model")
    @classmethod
    def model_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("model must not be blank")
        return value

    @field_validator("stop")
    @classmethod
    def valid_stop_sequences(cls, value: list[str]) -> list[str]:
        if any(not item.strip() or len(item) > 200 for item in value):
            raise ValueError("stop entries must be non-blank and at most 200 characters")
        return value


class ModelRequest(StrictModel):
    question: str = Field(min_length=1, max_length=20_000)
    context: list[ModelContext] = Field(default_factory=list, max_length=100)
    prompt: str = Field(min_length=1, max_length=50_000)
    generation: GenerationConfig

    @field_validator("question", "prompt")
    @classmethod
    def non_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @model_validator(mode="after")
    def ordered_unique_contexts(self) -> ModelRequest:
        positions = [item.position for item in self.context]
        if len(positions) != len(set(positions)):
            raise ValueError("context positions must be unique")
        if positions != sorted(positions):
            raise ValueError("context must be ordered by position")
        return self


class TokenUsage(StrictModel):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)


class ModelResponse(StrictModel):
    answer: str
    actual_model: str | None
    finish_reason: Literal["stop", "length", "content_filter", "tool_call", "other"] | None
    latency_ms: int = Field(ge=0)
    usage: TokenUsage | None
    provider_request_id: str | None
    is_mock: bool


class ModelErrorCode(str, Enum):
    adapter_not_found = "EXECUTION_ADAPTER_NOT_FOUND"
    not_configured = "PROVIDER_NOT_CONFIGURED"
    external_calls_disabled = "EXTERNAL_CALLS_DISABLED"
    capability_unsupported = "PROVIDER_CAPABILITY_UNSUPPORTED"
    authentication_failed = "PROVIDER_AUTHENTICATION_FAILED"
    rate_limited = "PROVIDER_RATE_LIMITED"
    timeout = "PROVIDER_TIMEOUT"
    transport_error = "PROVIDER_TRANSPORT_ERROR"
    server_error = "PROVIDER_SERVER_ERROR"
    response_invalid = "PROVIDER_RESPONSE_INVALID"


class ModelError(Exception):
    def __init__(
        self,
        code: ModelErrorCode,
        message: str,
        *,
        retryable: bool,
        attempts: int = 0,
        provider_request_id: str | None = None,
        retry_after_ms: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.attempts = attempts
        self.provider_request_id = provider_request_id
        self.retry_after_ms = retry_after_ms

    def as_dict(self) -> dict[str, object]:
        return {
            "code": self.code.value,
            "message": self.message,
            "retryable": self.retryable,
            "attempts": self.attempts,
            "provider_request_id": self.provider_request_id,
            "retry_after_ms": self.retry_after_ms,
        }


class AttemptRecord(StrictModel):
    number: int = Field(ge=1)
    status: Literal["succeeded", "failed", "timeout", "cancelled"]
    latency_ms: int = Field(ge=0)
    error_code: ModelErrorCode | None
    retry_delay_ms: int = Field(ge=0)
    started_at: datetime
    finished_at: datetime


class AdapterCapabilities(StrictModel):
    external_network: bool
    supports_seed: bool
    supports_stop: bool
    reports_usage: bool
    reports_request_id: bool


class ModelAdapter(Protocol):
    adapter_id: str
    capabilities: AdapterCapabilities
    last_attempts: list[AttemptRecord]

    def generate(self, request: ModelRequest) -> ModelResponse: ...


class ModelAdapterFactory(Protocol):
    def create(
        self,
        adapter_id: str,
        server_config: object | None = None,
        *,
        test_transport: ModelTransport | None = None,
    ) -> ModelAdapter: ...


class ModelTransportRequest(StrictModel):
    method: Literal["POST"] = "POST"
    url: str
    headers: dict[str, str]
    json_body: dict[str, object]
    timeout_ms: int = Field(ge=1)


class ModelTransportResponse(StrictModel):
    status_code: int = Field(ge=100, le=599)
    headers: dict[str, str] = Field(default_factory=dict)
    body: bytes


class ModelTransport(Protocol):
    def send(self, request: ModelTransportRequest) -> ModelTransportResponse: ...
