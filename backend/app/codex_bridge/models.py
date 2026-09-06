from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class BridgeContext(StrictModel):
    position: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=50_000)

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("context text must not be blank")
        return value


class GenerateRequest(StrictModel):
    """The complete and deliberately small Docker-to-host request contract."""

    question: str = Field(min_length=1, max_length=20_000)
    context: list[BridgeContext] = Field(default_factory=list, max_length=100)
    prompt: str = Field(min_length=1, max_length=50_000)
    model: str = Field(min_length=1, max_length=200)

    @field_validator("question", "prompt", "model")
    @classmethod
    def text_fields_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @model_validator(mode="after")
    def contexts_are_ordered_and_unique(self) -> GenerateRequest:
        positions = [item.position for item in self.context]
        if positions != sorted(positions) or len(positions) != len(set(positions)):
            raise ValueError("context positions must be ordered and unique")
        return self


class TokenUsage(StrictModel):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)


class GenerateResponse(StrictModel):
    answer: str
    actual_model: str | None
    finish_reason: Literal["stop"] | None = None
    latency_ms: int = Field(ge=0)
    usage: TokenUsage | None
    provider_request_id: None = None
    is_mock: Literal[False] = False


class AccountStatus(StrictModel):
    authenticated: bool
    account_type: str | None
    plan_type: str | None


class ModelStatus(StrictModel):
    id: str
    display_name: str
    is_default: bool
    reasoning_efforts: list[str]


class RateLimitWindow(StrictModel):
    used_percent: int
    window_duration_minutes: int | None
    resets_at: int | None


class RateLimitStatus(StrictModel):
    primary: RateLimitWindow | None
    secondary: RateLimitWindow | None
    reached_type: str | None


class BridgeStatus(StrictModel):
    status: Literal["ready", "not_authenticated", "degraded"]
    account: AccountStatus
    models: list[ModelStatus]
    rate_limits: RateLimitStatus | None
