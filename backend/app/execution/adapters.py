from __future__ import annotations

import asyncio
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
    GenerationConfig,
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
    ModelErrorCode.codex_not_installed: "Codex CLI is not installed or is not on PATH.",
    ModelErrorCode.not_authenticated: "Codex is not signed in with a ChatGPT account.",
    ModelErrorCode.wrong_auth_mode: "Codex is signed in without ChatGPT authentication.",
    ModelErrorCode.protocol_incompatible: "The installed Codex App Server protocol is incompatible.",
    ModelErrorCode.usage_limited: "The ChatGPT account cannot run Codex because its usage limit was reached.",
    ModelErrorCode.rate_limited: "The model provider rate-limited the request.",
    ModelErrorCode.timeout: "Model provider did not respond before the configured deadline.",
    ModelErrorCode.cancelled: "Model provider execution was cancelled.",
    ModelErrorCode.isolation_violation: "Codex could not satisfy the evaluation isolation policy.",
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


class CodexChatGPTConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bridge_url: str
    access_token: SecretStr
    default_model: str | None = None


class HttpxModelTransport:
    """Small production transport. Construction and health/status calls never perform I/O."""

    def send(self, request: ModelTransportRequest) -> ModelTransportResponse:
        return asyncio.run(self._send_with_deadline(request))

    async def _send_with_deadline(self, request: ModelTransportRequest) -> ModelTransportResponse:
        async def perform() -> httpx.Response:
            async with httpx.AsyncClient(timeout=request.timeout_ms / 1000) as client:
                if request.method == "GET":
                    return await client.get(request.url, headers=request.headers)
                return await client.post(
                    request.url,
                    headers=request.headers,
                    json=request.json_body,
                )

        try:
            # Phase timeouts alone permit slow streaming; cancel the whole attempt.
            response = await asyncio.wait_for(perform(), timeout=request.timeout_ms / 1000)
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
        independent_session_per_sample=True,
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
        independent_session_per_sample=True,
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
                if (
                    attempt_elapsed_ms > timeout_ms
                    or total_elapsed_ms > self.settings.model_total_timeout_ms
                ):
                    raise TimeoutError
                parsed = self._parse_response(response, started=invocation_started)
            except TimeoutError:
                last_error = _error(ModelErrorCode.timeout, attempts=attempt_number)
            except asyncio.CancelledError:
                last_error = _error(ModelErrorCode.cancelled, attempts=attempt_number)
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
                        "timeout"
                        if last_error.code == ModelErrorCode.timeout
                        else (
                            "cancelled" if last_error.code == ModelErrorCode.cancelled else "failed"
                        )
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
            context = "\n\n".join(f"[{item.position}]\n{item.text}" for item in request.context)
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
        except (ValueError, KeyError, IndexError, TypeError):
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


class CodexChatGPTAdapter:
    adapter_id = "codex_chatgpt"
    capabilities = AdapterCapabilities(
        external_network=True,
        supports_seed=False,
        supports_stop=False,
        supports_temperature=False,
        supports_top_p=False,
        supports_max_output_tokens=False,
        supports_reasoning_effort=True,
        independent_session_per_sample=True,
        reports_usage=True,
        reports_request_id=True,
    )

    def __init__(
        self,
        config: CodexChatGPTConfig,
        settings: Settings,
        *,
        transport: ModelTransport,
        transport_is_mock: bool,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config
        self.settings = settings
        self.transport = transport
        self.transport_is_mock = transport_is_mock
        self.monotonic = monotonic
        self.last_attempts: list[AttemptRecord] = []

    def inspect(self) -> dict[str, object]:
        """Explicit bridge probe. Status reads elsewhere never call this method."""
        self._assert_external_calls_enabled()
        try:
            response = self._send(method="GET", path="/v1/status", body=None)
        except TimeoutError:
            raise _error(ModelErrorCode.timeout, attempts=1) from None
        except asyncio.CancelledError:
            raise _error(ModelErrorCode.cancelled, attempts=1) from None
        except (ConnectionError, OSError):
            raise _error(ModelErrorCode.transport_error, attempts=1) from None
        return self._parse_object(response)

    def generate(self, request: ModelRequest) -> ModelResponse:
        self._assert_external_calls_enabled()
        self._validate_generation(request.generation)
        started_at = datetime.now(UTC)
        started = self.monotonic()
        self.last_attempts = []
        try:
            response = self._send(
                method="POST",
                path="/v1/generate",
                body={
                    "model": request.generation.model,
                    "prompt": request.prompt,
                    "question": request.question,
                    "context": [item.model_dump(mode="json") for item in request.context],
                    "reasoning_effort": request.generation.reasoning_effort,
                },
            )
            body = self._parse_object(response)
            answer = body.get("answer")
            if not isinstance(answer, str) or not answer.strip():
                raise _error(ModelErrorCode.response_invalid)
            result = ModelResponse(
                answer=answer,
                actual_model=(
                    body.get("actual_model") if isinstance(body.get("actual_model"), str) else None
                ),
                finish_reason=_finish_reason(body.get("finish_reason")),
                latency_ms=(
                    body["latency_ms"]
                    if isinstance(body.get("latency_ms"), int)
                    and not isinstance(body.get("latency_ms"), bool)
                    and body["latency_ms"] >= 0
                    else _elapsed_ms(self.monotonic, started)
                ),
                usage=_bridge_usage(body.get("usage")),
                provider_request_id=(
                    body.get("provider_request_id")
                    if isinstance(body.get("provider_request_id"), str)
                    else None
                ),
                is_mock=self.transport_is_mock,
            )
        except TimeoutError:
            error = _error(ModelErrorCode.timeout, attempts=1)
        except asyncio.CancelledError:
            error = _error(ModelErrorCode.cancelled, attempts=1)
        except (ConnectionError, OSError):
            error = _error(ModelErrorCode.transport_error, attempts=1)
        except ModelError as exc:
            exc.attempts = 1
            error = exc
        else:
            self.last_attempts.append(
                AttemptRecord(
                    number=1,
                    status="succeeded",
                    latency_ms=_elapsed_ms(self.monotonic, started),
                    error_code=None,
                    retry_delay_ms=0,
                    started_at=started_at,
                    finished_at=datetime.now(UTC),
                )
            )
            return result

        self.last_attempts.append(
            AttemptRecord(
                number=1,
                status="timeout"
                if error.code == ModelErrorCode.timeout
                else ("cancelled" if error.code == ModelErrorCode.cancelled else "failed"),
                latency_ms=_elapsed_ms(self.monotonic, started),
                error_code=error.code,
                retry_delay_ms=0,
                started_at=started_at,
                finished_at=datetime.now(UTC),
            )
        )
        raise error

    def _send(
        self,
        *,
        method: Literal["GET", "POST"],
        path: str,
        body: dict[str, object] | None,
    ) -> ModelTransportResponse:
        return self.transport.send(
            ModelTransportRequest(
                method=method,
                url=f"{self.config.bridge_url}{path}",
                headers={
                    "accept": "application/json",
                    "content-type": "application/json",
                    "authorization": (f"Bearer {self.config.access_token.get_secret_value()}"),
                },
                json_body=body,
                timeout_ms=self.settings.model_total_timeout_ms,
            )
        )

    def _parse_object(self, response: ModelTransportResponse) -> dict[str, object]:
        request_id = _header(response.headers, "x-request-id")
        if response.status_code < 200 or response.status_code >= 300:
            raise _bridge_error(response, provider_request_id=request_id)
        try:
            body = json.loads(response.body)
        except (UnicodeDecodeError, ValueError):
            raise _error(ModelErrorCode.response_invalid) from None
        if not isinstance(body, dict):
            raise _error(ModelErrorCode.response_invalid)
        return body

    def _assert_external_calls_enabled(self) -> None:
        if not self.transport_is_mock and not self.settings.model_external_calls_enabled:
            raise _error(ModelErrorCode.external_calls_disabled)

    @staticmethod
    def _validate_generation(generation: GenerationConfig) -> None:
        if (
            generation.temperature != 0.0
            or generation.top_p != 1.0
            or generation.max_output_tokens != 512
            or generation.stop
            or generation.seed is not None
        ):
            raise _error(ModelErrorCode.capability_unsupported)


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
        if adapter_id == "codex_chatgpt":
            if isinstance(server_config, CodexChatGPTConfig):
                codex_config = server_config
            else:
                codex_config = CodexChatGPTConfig(
                    bridge_url=self.settings.codex_bridge_url
                    or ("https://test.invalid" if test_transport is not None else ""),
                    access_token=(
                        self.settings.codex_bridge_token.get_secret_value()
                        if self.settings.codex_bridge_token
                        else ("t" * 32 if test_transport is not None else "")
                    ),
                    default_model=self.settings.codex_default_model,
                )
            complete = bool(
                codex_config.bridge_url
                and len(codex_config.access_token.get_secret_value().strip()) >= 32
            )
            if test_transport is None and not complete:
                raise _error(ModelErrorCode.not_configured)
            if test_transport is None and not self.settings.model_external_calls_enabled:
                raise _error(ModelErrorCode.external_calls_disabled)
            return CodexChatGPTAdapter(
                codex_config,
                self.settings,
                transport=test_transport or HttpxModelTransport(),
                transport_is_mock=test_transport is not None,
            )
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
    reason_code: str | None = None,
    diagnostic_id: str | None = None,
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
        reason_code=reason_code,
        diagnostic_id=diagnostic_id,
    )


def _bridge_error(
    response: ModelTransportResponse,
    *,
    provider_request_id: str | None,
) -> ModelError:
    provider_code = None
    reason_code = None
    diagnostic_id = None
    try:
        body = json.loads(response.body)
        if isinstance(body, dict):
            detail = body.get("detail")
            error = body.get("error")
            if isinstance(detail, dict):
                provider_code = detail.get("code")
                reason_code = detail.get("reason_code")
                diagnostic_id = detail.get("diagnostic_id")
            elif isinstance(error, dict):
                provider_code = error.get("code")
    except (UnicodeDecodeError, ValueError):
        pass
    code_map = {
        "CODEX_NOT_INSTALLED": ModelErrorCode.codex_not_installed,
        "CODEX_NOT_AUTHENTICATED": ModelErrorCode.not_authenticated,
        "CODEX_WRONG_AUTH_MODE": ModelErrorCode.wrong_auth_mode,
        "CODEX_LOGIN_EXPIRED": ModelErrorCode.authentication_failed,
        "CODEX_USAGE_LIMITED": ModelErrorCode.usage_limited,
        "CODEX_RATE_LIMITED": ModelErrorCode.rate_limited,
        "CODEX_TIMEOUT": ModelErrorCode.timeout,
        "CODEX_CANCELLED": ModelErrorCode.cancelled,
        "CODEX_ISOLATION_VIOLATION": ModelErrorCode.isolation_violation,
        "CODEX_PROTOCOL_INCOMPATIBLE": ModelErrorCode.protocol_incompatible,
        "CODEX_RESPONSE_INVALID": ModelErrorCode.response_invalid,
        "CODEX_CONNECTION_FAILED": ModelErrorCode.transport_error,
        "CODEX_BRIDGE_INTERNAL_ERROR": ModelErrorCode.server_error,
    }
    code = code_map.get(provider_code)
    if code is None:
        if response.status_code in {401, 403}:
            code = ModelErrorCode.authentication_failed
        elif response.status_code == 429:
            code = ModelErrorCode.rate_limited
        elif response.status_code in {408, 504}:
            code = ModelErrorCode.timeout
        elif 500 <= response.status_code <= 599:
            code = ModelErrorCode.server_error
        else:
            code = ModelErrorCode.response_invalid
    return _error(
        code,
        provider_request_id=provider_request_id,
        reason_code=reason_code if isinstance(reason_code, str) else None,
        diagnostic_id=diagnostic_id if isinstance(diagnostic_id, str) else None,
    )


def _bridge_usage(value: object) -> TokenUsage | None:
    if not isinstance(value, dict):
        return None
    parsed = [value.get(key) for key in ("input_tokens", "output_tokens", "total_tokens")]
    if any(not isinstance(item, int) or isinstance(item, bool) or item < 0 for item in parsed):
        return None
    return TokenUsage(
        input_tokens=parsed[0],
        output_tokens=parsed[1],
        total_tokens=parsed[2],
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
    except (ValueError, OverflowError):
        return None


def _finish_reason(value: object) -> str | None:
    if not isinstance(value, str):
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
