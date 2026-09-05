from __future__ import annotations

from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RAGOPS_", extra="ignore")

    app_name: str = "ragops-api"
    environment: str = "local"
    database_url: str = "sqlite:///./ragops.db"
    log_level: str = "INFO"
    auto_create_schema: bool = True
    model_execution_adapter: Literal["mock", "openai_compatible"] = "mock"
    model_external_calls_enabled: bool = False
    model_request_timeout_ms: int = Field(default=10_000, ge=100, le=30_000)
    model_total_timeout_ms: int = Field(default=25_000, ge=100, le=60_000)
    model_max_attempts: int = Field(default=3, ge=1, le=3)
    model_retry_base_ms: int = Field(default=250, ge=0, le=2_000)
    model_retry_max_delay_ms: int = Field(default=2_000, ge=0, le=5_000)
    openai_compat_base_url: str | None = None
    openai_compat_auth_mode: Literal["bearer", "none"] = "bearer"
    openai_compat_api_key: SecretStr | None = None
    openai_compat_default_model: str | None = None

    @field_validator("openai_compat_base_url", "openai_compat_default_model", mode="before")
    @classmethod
    def blank_optional_strings_are_missing(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("openai_compat_base_url")
    @classmethod
    def valid_provider_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("OpenAI-compatible base URL must be an absolute HTTP(S) URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("OpenAI-compatible base URL must not contain user info, query, or fragment")
        return value.rstrip("/")

    @model_validator(mode="after")
    def total_timeout_covers_one_attempt(self) -> Settings:
        if self.model_total_timeout_ms < self.model_request_timeout_ms:
            raise ValueError("model_total_timeout_ms must be at least model_request_timeout_ms")
        return self

    @property
    def openai_credential_configured(self) -> bool:
        return bool(
            self.openai_compat_api_key
            and self.openai_compat_api_key.get_secret_value().strip()
        )

    @property
    def openai_configuration_complete(self) -> bool:
        credential_ready = (
            self.openai_compat_auth_mode == "none" or self.openai_credential_configured
        )
        return bool(
            self.openai_compat_base_url
            and self.openai_compat_default_model
            and credential_ready
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
