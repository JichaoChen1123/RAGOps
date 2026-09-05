from __future__ import annotations

import json
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, SecretStr

from app.core.config import Settings
from app.execution.model import (
    AdapterCapabilities,
    AttemptRecord,
    ModelAdapter,
    ModelError,
    ModelErrorCode,
    ModelRequest,
    ModelResponse,
    ModelTransport,
    ModelTransportRequest,
    ModelTransportResponse,
    TokenUsage,
)


SAFE_MESSAGES: dict[ModelErrorCode, str] = {
    ModelErrorCode.adapter_not_found: "The requested model execution adapter is not available.",
    ModelErrorCode.not_configured: "The selected model provider is not configured.",
    ModelErrorCode.external_calls_disabled: "External model calls are disabled by server policy.",
    ModelErrorCode.capability_unsupported: "The selected provider does not support this request.",
    ModelErrorCode.authentication_failed: "Model provider authentication failed.",
    ModelErrorCode.rate_limited: "The model provider rate-limited the request.",
    ModelErrorCode.timeout: "Model provider did not respond before the configured deadline.",
    ModelErrorCode.transport_error: "The model provider could not be reached.",
    ModelErrorCode.server_error: "The model provider reported a server error.",
    ModelErrorCode.response_invalid: "The model provider returned an invalid response.",
}


class OpenAICompatibleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str
    auth_mode: Literal["bearer", "none"] = "bearer"
    api_key: SecretStr | None = None
    default_model: str


class HttpxModelTransport:
    """Small production transport. Construction and health/status calls never perform I/O."""

    def send(self, request: ModelTransportRequest) -> ModelTransportResponse:
        try:
            response = httpx.post(
                request.url,
                headers=request.headers,
                json=request.json_body,
                timeout=request.timeout_ms / 1000,
            )
        except httpx.TimeoutException as exc:
            raise TimeoutError from exc
        except httpx.TransportError as exc:
            raise ConnectionError from exc
        return ModelTransportResponse(
            status_code=response.status_code,
            headers={
                key.lower(): value
                for key, value in response.headers.items()
                if key.lower() in {"x-request-id", "retry-after"}
            },
            body=response.content,
        )


class MockModelAdapter:
    adapter_id = "mock"
    capabilities = AdapterCapabilities(
        external_network=False,
        supports_seed=True,
        supports_stop=True,
        reports_usage=False,
        reports_request_id=False,
    )

    def __init__(self) -> None:
        self.last_attempts: list[AttemptRecord] = []

    def generate(self, request: ModelRequest) -> ModelResponse:
        if request.generation.model != "mock-ragops-v1":
            raise _error(ModelErrorCode.capability_unsupported)
        started_at = datetime.now(UTC)
        started = time.perf_counter()
        if request.context:
            answer = f"[mock] {request.context[0].text[:500]}"
        else:
            answer = f"[mock] Insufficient context for: {request.question}"
        latency_ms = max(0, round((time.perf_counter() - started) * 1000))
        finished_at = datetime.now(UTC)
        self.last_attempts = [
            AttemptRecord(
                number=1,
                status="succeeded",
                latency_ms=latency_ms,
                error_code=None,
                retry_delay_ms=0,
                started_at=started_at,
                finished_at=finished_at,
            )
        ]
        return ModelResponse(
            answer=answer,
            actual_model="mock-ragops-v1",
            finish_reason="stop",
            latency_ms=latency_ms,
            usage=None,
            provider_request_id=None,
            is_mock=True,
        )


class OpenAICompatibleAdapter:
    adapter_id = "openai_compatible"
    capabilities = AdapterCapabilities(
        external_network=True,
        supports_seed=True,
        supports_stop=True,
        reports_usage=True,
        reports_request_id=True,
    )

    def __init__(
        self,
        config: OpenAICompatibleConfig,
        settings: Settings,
        *,
        transport: ModelTransport,
        transport_is_mock: bool,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config
        self.settings = settings
        self.transport = transport
        self.transport_is_mock = transport_is_mock
        self.sleeper = sleeper
        self.monotonic = monotonic
        self.last_attempts: list[AttemptRecord] = []

    def generate(self, request: ModelRequest) -> ModelResponse:
        if not self.transport_is_mock and not self.settings.model_external_calls_enabled:
            raise _error(ModelErrorCode.external_calls_disabled)

        payload = self._payload(request)
        headers = {"content-type": "application/json"}
        if self.config.auth_mode == "bearer" and self.config.api_key:
            headers["authorization"] = f"Bearer {self.config.api_key.get_secret_value()}"

        self.last_attempts = []
        invocation_started = self.monotonic()
        last_error: ModelError | None = None
        for attempt_number in range(1, self.settings.model_max_attempts + 1):
            if not self.transport_is_mock and not self.settings.model_external_calls_enabled:
                raise _error(
                    ModelErrorCode.external_calls_disabled,
                    attempts=len(self.last_attempts),
                )
            elapsed_ms = round((self.monotonic() - invocation_started) * 1000)
            remaining_ms = self.settings.model_total_timeout_ms - elapsed_ms
            if remaining_ms <= 0:
                raise _error(
                    ModelErrorCode.timeout,
                    attempts=len(self.last_attempts),
                )
            timeout_ms = min(self.settings.model_request_timeout_ms, remaining_ms)
            started_at = datetime.now(UTC)
            attempt_started = self.monotonic()
            try:
                response = self.transport.send(
                    ModelTransportRequest(
                        url=f"{self.config.base_url}/chat/completions",
                        headers=headers,
                        json_body=payload,
                        timeout_ms=timeout_ms,
                    )
                )
                attempt_elapsed_ms = _elapsed_ms(self.monotonic, attempt_started)
                total_elapsed_ms = _elapsed_ms(self.monotonic, invocation_started)
                if attempt_elapsed_ms > timeout_ms or total_elapsed_ms > self.settings.model_total_timeout_ms:
                    raise TimeoutError
                parsed = self._parse_response(response, started=invocation_started)
            except TimeoutError:
                last_error = _error(ModelErrorCode.timeout, attempts=attempt_number)
            except (ConnectionError, OSError):
                last_error = _error(ModelErrorCode.transport_error, attempts=attempt_number)
            except ModelError as exc:
                exc.attempts = attempt_number
                last_error = exc
            else:
                finished_at = datetime.now(UTC)
                self.last_attempts.append(
                    AttemptRecord(
                        number=attempt_number,
                        status="succeeded",
                        latency_ms=_elapsed_ms(self.monotonic, attempt_started),
                        error_code=None,
                        retry_delay_ms=0,
                        started_at=started_at,
                        finished_at=finished_at,
                    )
                )
                return parsed

            assert last_error is not None
            delay_ms = self._retry_delay(last_error, attempt_number)
            may_retry = last_error.retryable and attempt_number < self.settings.model_max_attempts
            projected_ms = round((self.monotonic() - invocation_started) * 1000) + delay_ms
            if not may_retry or projected_ms >= self.settings.model_total_timeout_ms:
                delay_ms = 0
                may_retry = False
            self.last_attempts.append(
                AttemptRecord(
                    number=attempt_number,
                    status=(
                        "timeout" if last_error.code == ModelErrorCode.timeout else "failed"
                    ),
                    latency_ms=_elapsed_ms(self.monotonic, attempt_started),
                    error_code=last_error.code,
                    retry_delay_ms=delay_ms,
                    started_at=started_at,
                    finished_at=datetime.now(UTC),
                )
            )
            if not may_retry:
                last_error.attempts = attempt_number
                raise last_error
            if delay_ms:
                self.sleeper(delay_ms / 1000)

        raise last_error or _error(ModelErrorCode.transport_error)

    def _payload(self, request: ModelRequest) -> dict[str, object]:
        if request.context:
            context = "\n\n".join(
                f"[{item.position}]\n{item.text}" for item in request.context
            )
        else:
            context = "(none)"
        payload: dict[str, object] = {
            "model": request.generation.model,
            "messages": [
                {"role": "system", "content": request.prompt},
                {
                    "role": "user",
                    "content": f"Question:\n{request.question}\n\nContext:\n{context}",
                },
            ],
            "temperature": request.generation.temperature,
            "top_p": request.generation.top_p,
            "max_tokens": request.generation.max_output_tokens,
        }
        if request.generation.stop:
            payload["stop"] = request.generation.stop
        if request.generation.seed is not None:
            payload["seed"] = request.generation.seed
        return payload

    def _parse_response(
        self,
        response: ModelTransportResponse,
        *,
        started: float,
    ) -> ModelResponse:
        request_id = _header(response.headers, "x-request-id")
        if response.status_code in {401, 403}:
            raise _error(
                ModelErrorCode.authentication_failed,
                provider_request_id=request_id,
            )
        if response.status_code == 429:
            raise _error(
                ModelErrorCode.rate_limited,
                provider_request_id=request_id,
                retry_after_ms=_retry_after_ms(response.headers),
            )
        if 500 <= response.status_code <= 599:
            raise _error(ModelErrorCode.server_error, provider_request_id=request_id)
        if response.status_code < 200 or response.status_code >= 300 or not response.body:
            raise _error(ModelErrorCode.response_invalid, provider_request_id=request_id)
        try:
            body = json.loads(response.body)
            if not isinstance(body, dict):
                raise TypeError
            choice = body["choices"][0]
            answer = choice["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            raise _error(ModelErrorCode.response_invalid, provider_request_id=request_id) from None
        if not isinstance(answer, str) or not answer.strip():
            raise _error(ModelErrorCode.response_invalid, provider_request_id=request_id)
        return ModelResponse(
            answer=answer,
            actual_model=body.get("model") if isinstance(body.get("model"), str) else None,
            finish_reason=_finish_reason(choice.get("finish_reason")),
            latency_ms=_elapsed_ms(self.monotonic, started),
            usage=_usage(body.get("usage")),
            provider_request_id=request_id,
            is_mock=self.transport_is_mock,
        )

    def _retry_delay(self, error: ModelError, attempt_number: int) -> int:
        if error.retry_after_ms is not None:
            return min(error.retry_after_ms, 5_000)
        return min(
            self.settings.model_retry_base_ms * 2 ** (attempt_number - 1),
            self.settings.model_retry_max_delay_ms,
        )


class DefaultModelAdapterFactory:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def create(
        self,
        adapter_id: str,
        server_config: object | None = None,
        *,
        test_transport: ModelTransport | None = None,
    ) -> ModelAdapter:
        if adapter_id == "mock":
            return MockModelAdapter()
        if adapter_id != "openai_compatible":
            raise _error(ModelErrorCode.adapter_not_found)

        if isinstance(server_config, OpenAICompatibleConfig):
            config = server_config
        else:
            config = OpenAICompatibleConfig(
                base_url=self.settings.openai_compat_base_url
                or ("https://test.invalid" if test_transport is not None else ""),
                auth_mode=self.settings.openai_compat_auth_mode,
                api_key=(
                    self.settings.openai_compat_api_key.get_secret_value()
                    if self.settings.openai_compat_api_key
                    else None
                ),
                default_model=self.settings.openai_compat_default_model
                or ("test-model" if test_transport is not None else ""),
            )
        complete = bool(
            config.base_url
            and config.default_model
            and (
                config.auth_mode == "none"
                or (config.api_key and config.api_key.get_secret_value().strip())
            )
        )
        if test_transport is None and not complete:
            raise _error(ModelErrorCode.not_configured)
        if test_transport is None and not self.settings.model_external_calls_enabled:
            raise _error(ModelErrorCode.external_calls_disabled)
        return OpenAICompatibleAdapter(
            config,
            self.settings,
            transport=test_transport or HttpxModelTransport(),
            transport_is_mock=test_transport is not None,
        )


def _error(
    code: ModelErrorCode,
    *,
    attempts: int = 0,
    provider_request_id: str | None = None,
    retry_after_ms: int | None = None,
) -> ModelError:
    retryable = code in {
        ModelErrorCode.rate_limited,
        ModelErrorCode.timeout,
        ModelErrorCode.transport_error,
        ModelErrorCode.server_error,
    }
    return ModelError(
        code,
        SAFE_MESSAGES[code],
        retryable=retryable,
        attempts=attempts,
        provider_request_id=provider_request_id,
        retry_after_ms=retry_after_ms,
    )


def _header(headers: dict[str, str], name: str) -> str | None:
    for key, value in headers.items():
        if key.lower() == name:
            return value[:300]
    return None


def _retry_after_ms(headers: dict[str, str]) -> int | None:
    value = _header(headers, "retry-after")
    if value is None:
        return None
    try:
        return min(max(round(float(value) * 1000), 0), 5_000)
    except ValueError:
        return None


def _finish_reason(value: object) -> str | None:
    if value is None:
        return None
    if value in {"stop", "length", "content_filter"}:
        return str(value)
    if value in {"tool_call", "tool_calls"}:
        return "tool_call"
    return "other" if isinstance(value, str) else None


def _usage(value: object) -> TokenUsage | None:
    if not isinstance(value, dict):
        return None
    fields = ("prompt_tokens", "completion_tokens", "total_tokens")
    parsed = [value.get(field) for field in fields]
    if any(not isinstance(item, int) or isinstance(item, bool) or item < 0 for item in parsed):
        return None
    return TokenUsage(
        input_tokens=parsed[0],
        output_tokens=parsed[1],
        total_tokens=parsed[2],
    )


def _elapsed_ms(clock: Callable[[], float], started: float) -> int:
    return max(0, round((clock() - started) * 1000))
