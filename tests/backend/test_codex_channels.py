from __future__ import annotations

import asyncio
import io
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.codex_bridge.app import BridgeConfig, create_bridge_app
from app.codex_bridge.protocol import (
    DISABLED_FEATURES,
    CodexAppServerRunner,
    CodexBridgeError,
    JsonRpcProcess,
)
from app.cli import MINIMUM_CODEX_VERSION, read_codex_version
from app.core.config import Settings
from app.execution.adapters import (
    CodexChatGPTAdapter,
    CodexChatGPTConfig,
    DefaultModelAdapterFactory,
    OpenAICompatibleAdapter,
    OpenAICompatibleConfig,
)
from app.execution.model import (
    GenerationConfig,
    ModelContext,
    ModelError,
    ModelErrorCode,
    ModelRequest,
    ModelTransportRequest,
    ModelTransportResponse,
)
from app.main import create_app


class MemoryTransport:
    def __init__(self, scripted: list[ModelTransportResponse | BaseException]) -> None:
        self.scripted = list(scripted)
        self.requests: list[ModelTransportRequest] = []

    def send(self, request: ModelTransportRequest) -> ModelTransportResponse:
        self.requests.append(request)
        item = self.scripted.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "test",
        "database_url": "sqlite://",
        "model_external_calls_enabled": True,
        "model_request_timeout_ms": 100,
        "model_total_timeout_ms": 1_000,
        "model_max_attempts": 3,
        "model_retry_base_ms": 0,
        "model_retry_max_delay_ms": 0,
    }
    values.update(overrides)
    return Settings(**values)


def _response(status_code: int, body: object) -> ModelTransportResponse:
    return ModelTransportResponse(
        status_code=status_code,
        headers={"x-request-id": "safe-request-id"},
        body=json.dumps(body).encode(),
    )


def _request() -> ModelRequest:
    return ModelRequest(
        question="Safe question",
        context=[ModelContext(position=1, text="Safe context")],
        prompt="Use only context.",
        generation=GenerationConfig(model="account-model", reasoning_effort="low"),
    )


def _bridge_payload() -> dict[str, Any]:
    return {
        "model": "account-model",
        "prompt": "Use only context.",
        "question": "Safe question",
        "context": [{"position": 1, "text": "Safe context"}],
        "reasoning_effort": "low",
    }


def _adapter(transport: MemoryTransport, *, real_transport: bool = False) -> CodexChatGPTAdapter:
    return CodexChatGPTAdapter(
        CodexChatGPTConfig(
            bridge_url="http://host.docker.internal:8765",
            access_token="x" * 32,
        ),
        _settings(model_external_calls_enabled=not real_transport),
        transport=transport,
        transport_is_mock=not real_transport,
    )


def test_codex_adapter_maps_only_allowed_fields_and_optional_response_values() -> None:
    transport = MemoryTransport(
        [
            _response(
                200,
                {
                    "answer": "final answer",
                    "actual_model": "actual-account-model",
                    "finish_reason": "stop",
                    "latency_ms": 23,
                    "usage": None,
                    "provider_request_id": "turn-1",
                },
            )
        ]
    )

    result = _adapter(transport).generate(_request())

    sent = transport.requests[0]
    assert sent.method == "POST"
    assert sent.url == "http://host.docker.internal:8765/v1/generate"
    assert sent.headers["authorization"] == f"Bearer {'x' * 32}"
    assert sent.json_body == {
        "model": "account-model",
        "prompt": "Use only context.",
        "question": "Safe question",
        "context": [{"position": 1, "text": "Safe context"}],
        "reasoning_effort": "low",
    }
    assert result.answer == "final answer"
    assert result.actual_model == "actual-account-model"
    assert result.usage is None
    assert result.provider_request_id == "turn-1"
    assert result.is_mock is True


@pytest.mark.parametrize(
    ("bridge_code", "expected"),
    [
        ("CODEX_NOT_INSTALLED", ModelErrorCode.codex_not_installed),
        ("CODEX_NOT_AUTHENTICATED", ModelErrorCode.not_authenticated),
        ("CODEX_WRONG_AUTH_MODE", ModelErrorCode.wrong_auth_mode),
        ("CODEX_LOGIN_EXPIRED", ModelErrorCode.authentication_failed),
        ("CODEX_USAGE_LIMITED", ModelErrorCode.usage_limited),
        ("CODEX_RATE_LIMITED", ModelErrorCode.rate_limited),
        ("CODEX_TIMEOUT", ModelErrorCode.timeout),
        ("CODEX_CANCELLED", ModelErrorCode.cancelled),
        ("CODEX_ISOLATION_VIOLATION", ModelErrorCode.isolation_violation),
        ("CODEX_PROTOCOL_INCOMPATIBLE", ModelErrorCode.protocol_incompatible),
        ("CODEX_RESPONSE_INVALID", ModelErrorCode.response_invalid),
    ],
)
def test_codex_errors_are_safe_and_never_retried(
    bridge_code: str, expected: ModelErrorCode
) -> None:
    transport = MemoryTransport(
        [
            _response(
                429 if "LIMIT" in bridge_code or "RATE" in bridge_code else 409,
                {"detail": {"code": bridge_code, "message": "PRIVATE BRIDGE DETAIL"}},
            )
        ]
    )
    adapter = _adapter(transport)

    with pytest.raises(ModelError) as caught:
        adapter.generate(_request())

    assert caught.value.code == expected
    assert caught.value.attempts == 1
    assert "PRIVATE BRIDGE DETAIL" not in caught.value.message
    assert len(transport.requests) == 1


@pytest.mark.parametrize(
    ("failure", "expected"),
    [(TimeoutError(), ModelErrorCode.timeout), (ConnectionError(), ModelErrorCode.transport_error)],
)
def test_codex_status_transport_errors_are_normalized(
    failure: Exception, expected: ModelErrorCode
) -> None:
    adapter = _adapter(MemoryTransport([failure]))
    with pytest.raises(ModelError) as caught:
        adapter.inspect()
    assert caught.value.code == expected
    assert caught.value.attempts == 1


def test_codex_external_gate_rejects_before_transport() -> None:
    transport = MemoryTransport([_response(200, {})])
    adapter = _adapter(transport, real_transport=True)
    with pytest.raises(ModelError) as caught:
        adapter.generate(_request())
    assert caught.value.code == ModelErrorCode.external_calls_disabled
    assert transport.requests == []


def test_codex_runtime_cancellation_is_normalized_without_retry() -> None:
    transport = MemoryTransport([asyncio.CancelledError()])
    adapter = _adapter(transport)

    with pytest.raises(ModelError) as caught:
        adapter.generate(_request())

    assert caught.value.code == ModelErrorCode.cancelled
    assert caught.value.attempts == 1
    assert len(transport.requests) == 1


def test_openai_runtime_cancellation_is_normalized_without_retry() -> None:
    transport = MemoryTransport([asyncio.CancelledError()])
    adapter = OpenAICompatibleAdapter(
        OpenAICompatibleConfig(
            base_url="https://provider.invalid/v1",
            api_key="secret",
            default_model="provider-model",
        ),
        _settings(),
        transport=transport,
        transport_is_mock=True,
        sleeper=lambda _: None,
    )

    with pytest.raises(ModelError) as caught:
        adapter.generate(
            ModelRequest(
                question="Safe question",
                context=[],
                prompt="Safe prompt",
                generation=GenerationConfig(model="provider-model"),
            )
        )

    assert caught.value.code == ModelErrorCode.cancelled
    assert caught.value.attempts == 1
    assert len(transport.requests) == 1


def test_short_codex_bridge_token_is_not_treated_as_configured() -> None:
    settings = _settings(codex_bridge_url="http://bridge.test", codex_bridge_token="short")
    assert settings.codex_configuration_complete is False
    with pytest.raises(ModelError) as caught:
        DefaultModelAdapterFactory(settings).create("codex_chatgpt")
    assert caught.value.code == ModelErrorCode.not_configured


class RunnerSpy:
    def __init__(self) -> None:
        self.generated: list[dict[str, Any]] = []

    def inspect(self) -> dict[str, Any]:
        return {"authentication_status": "authenticated", "models": []}

    def generate(self, request: dict[str, Any]) -> dict[str, Any]:
        self.generated.append(request)
        return {
            "answer": "bridge answer",
            "actual_model": None,
            "finish_reason": "stop",
            "latency_ms": 1,
            "usage": None,
            "provider_request_id": None,
        }


def test_bridge_requires_auth_and_rejects_arbitrary_execution_fields(tmp_path: Path) -> None:
    runner = RunnerSpy()
    config = BridgeConfig(access_token="b" * 32, sandbox_root=tmp_path)
    with TestClient(create_bridge_app(config, runner_factory=lambda: runner)) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/v1/status").status_code == 401
        headers = {"authorization": f"Bearer {'b' * 32}"}
        assert client.get("/v1/status", headers=headers).status_code == 200
        invalid = client.post(
            "/v1/generate",
            headers=headers,
            json={
                "model": "m",
                "prompt": "p",
                "question": "q",
                "context": [],
                "reasoning_effort": "low",
                "cwd": "C:/private",
                "command": "whoami",
            },
        )
        valid = client.post(
            "/v1/generate",
            headers=headers,
            json={
                "model": "m",
                "prompt": "p",
                "question": "q",
                "context": [{"position": 1, "text": "c"}],
                "reasoning_effort": "low",
            },
        )

    assert invalid.status_code == 422
    assert invalid.json() == {
        "error": {
            "code": "CODEX_BRIDGE_INVALID_REQUEST",
            "message": "The bridge request does not match the fixed contract.",
            "retryable": False,
        }
    }
    assert "whoami" not in invalid.text
    assert valid.status_code == 200
    assert runner.generated == [
        {
            "model": "m",
            "prompt": "p",
            "question": "q",
            "context": [{"position": 1, "text": "c"}],
            "reasoning_effort": "low",
        }
    ]


class FakeRpc:
    def __init__(self, serial: int, cwd: Path, *, tool_event: bool = False) -> None:
        self.serial = serial
        self.cwd = cwd
        self.thread_id = f"thread-{serial}"
        self.turn_id = f"turn-{serial}"
        self.tool_event = tool_event
        self.requests: list[tuple[str, dict[str, Any] | None]] = []
        self.interrupted = False
        item = (
            {"type": "commandExecution", "command": "forbidden"}
            if tool_event
            else {
                "id": f"message-{serial}",
                "type": "agentMessage",
                "phase": "final_answer",
                "text": '{"answer":"isolated answer"}',
            }
        )
        self.notifications = [
            {
                "method": "model/rerouted",
                "params": {
                    "threadId": self.thread_id,
                    "turnId": self.turn_id,
                    "fromModel": "actual-account-model",
                    "toModel": "routed-account-model",
                },
            },
            {
                "method": "item/completed",
                "params": {
                    "threadId": self.thread_id,
                    "turnId": self.turn_id,
                    "item": item,
                },
            },
            {
                "method": "thread/tokenUsage/updated",
                "params": {
                    "threadId": self.thread_id,
                    "turnId": self.turn_id,
                    "tokenUsage": {
                        "last": {"inputTokens": 7, "outputTokens": 3, "totalTokens": 10}
                    },
                },
            },
            {
                "method": "turn/completed",
                "params": {
                    "threadId": self.thread_id,
                    "turn": {"id": self.turn_id, "status": "completed"},
                },
            },
        ]

    def __enter__(self) -> FakeRpc:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def initialize(self, timeout_seconds: float) -> dict[str, Any]:
        return {"userAgent": "codex-cli/0.test"}

    def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        self.requests.append((method, params))
        if method == "account/read":
            return {
                "account": {
                    "type": "chatgpt",
                    "planType": "plus",
                    "email": "must-not-leak@example.test",
                }
            }
        if method == "model/list":
            return {
                "data": [
                    {
                        "model": "account-model",
                        "displayName": "Account model",
                        "isDefault": True,
                        "supportedReasoningEfforts": [
                            {"reasoningEffort": "low"},
                            {"reasoningEffort": "high"},
                        ],
                    }
                ]
            }
        if method == "account/rateLimits/read":
            return {"rateLimits": {"primary": {"usedPercent": 12}}}
        if method == "thread/start":
            return {
                "thread": {
                    "id": self.thread_id,
                    "cwd": str(self.cwd),
                    "ephemeral": True,
                },
                "cwd": str(self.cwd),
                "model": "account-model",
                "approvalPolicy": "never",
                "sandbox": {"type": "readOnly", "networkAccess": False},
                "instructionSources": [],
            }
        if method == "turn/start":
            return {"turn": {"id": self.turn_id}}
        raise AssertionError(f"Unexpected RPC method: {method}")

    def next_notification(self, deadline: float) -> dict[str, Any]:
        return self.notifications.pop(0)

    def interrupt(self, thread_id: str, turn_id: str) -> None:
        assert (thread_id, turn_id) == (self.thread_id, self.turn_id)
        self.interrupted = True


class FakeConnectionFactory:
    def __init__(self, *, tool_event: bool = False) -> None:
        self.tool_event = tool_event
        self.instances: list[FakeRpc] = []

    def __call__(self, **kwargs: object) -> FakeRpc:
        rpc = FakeRpc(
            len(self.instances) + 1,
            Path(str(kwargs["cwd"])),
            tool_event=self.tool_event,
        )
        self.instances.append(rpc)
        return rpc


def _runner(tmp_path: Path, factory: FakeConnectionFactory) -> CodexAppServerRunner:
    return CodexAppServerRunner(
        executable="codex",
        sandbox_root=tmp_path / "empty-codex-root",
        timeout_seconds=1,
        connection_factory=factory,
    )


def test_protocol_inspection_is_safe_and_generation_uses_fresh_restricted_threads(
    tmp_path: Path,
) -> None:
    factory = FakeConnectionFactory()
    runner = _runner(tmp_path, factory)

    status = runner.inspect()
    first = runner.generate(_bridge_payload())
    second = runner.generate(_bridge_payload())

    assert status["authentication_status"] == "authenticated"
    assert status["models"][0]["id"] == "account-model"
    assert status["rate_limits"]["primary"]["used_percent"] == 12
    assert "must-not-leak" not in json.dumps(status)
    assert first["answer"] == second["answer"] == "isolated answer"
    assert first["provider_request_id"] != second["provider_request_id"]
    assert first["actual_model"] == second["actual_model"] == "routed-account-model"
    assert first["usage"] == {"input_tokens": 7, "output_tokens": 3, "total_tokens": 10}

    generation_instances = factory.instances[1:]
    assert [item.thread_id for item in generation_instances] == ["thread-2", "thread-3"]
    assert generation_instances[0].cwd != generation_instances[1].cwd
    assert all(not item.cwd.exists() for item in generation_instances)
    for rpc in generation_instances:
        thread_params = next(params for method, params in rpc.requests if method == "thread/start")
        turn_params = next(params for method, params in rpc.requests if method == "turn/start")
        assert thread_params is not None and turn_params is not None
        assert thread_params["ephemeral"] is True
        assert thread_params["approvalPolicy"] == "never"
        assert thread_params["sandbox"] == "read-only"
        assert thread_params["allowProviderModelFallback"] is False
        assert thread_params["dynamicTools"] == []
        assert thread_params["environments"] == []
        assert thread_params["config"] == {"mcp_servers": {}, "web_search": "disabled"}
        assert turn_params["sandboxPolicy"] == {"type": "readOnly", "networkAccess": False}
        serialized_turn = json.dumps(turn_params)
        assert "reference_answer" not in serialized_turn
        assert "labels" not in serialized_turn


def test_protocol_rejects_tool_activity_and_interrupts_turn(tmp_path: Path) -> None:
    factory = FakeConnectionFactory(tool_event=True)
    runner = _runner(tmp_path, factory)

    with pytest.raises(CodexBridgeError) as caught:
        runner.generate(_bridge_payload())

    assert caught.value.code == "CODEX_ISOLATION_VIOLATION"
    assert factory.instances[0].interrupted is True


def test_codex_cli_version_parser_uses_the_supported_minimum(monkeypatch) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, "codex-cli 0.153.4\n", ""
        ),
    )
    assert MINIMUM_CODEX_VERSION == (0, 153, 4)
    assert read_codex_version() == (0, 153, 4)


def test_codex_process_disables_features_and_removes_model_credentials(
    monkeypatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    class FakeProcess:
        stdin = io.StringIO()
        stdout = io.StringIO()
        stderr = io.StringIO()

        @staticmethod
        def poll() -> int:
            return 0

    def process_factory(command: list[str], **kwargs: object) -> FakeProcess:
        captured["command"] = command
        captured["environment"] = kwargs["env"]
        return FakeProcess()

    monkeypatch.setenv("RAGOPS_CODEX_BRIDGE_TOKEN", "must-not-reach-codex")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-reach-codex")
    monkeypatch.setenv("SAFE_BRIDGE_TEST_VALUE", "retained")

    with JsonRpcProcess(
        executable="codex",
        cwd=tmp_path,
        process_factory=process_factory,
    ):
        pass

    command = captured["command"]
    environment = captured["environment"]
    assert isinstance(command, list)
    assert isinstance(environment, dict)
    assert command[:4] == ["codex", "app-server", "--stdio", "--strict-config"]
    assert 'web_search="disabled"' in command
    assert "mcp_servers={}" in command
    for feature in DISABLED_FEATURES:
        assert ["--disable", feature] == command[
            command.index(feature) - 1 : command.index(feature) + 1
        ]
    assert "RAGOPS_CODEX_BRIDGE_TOKEN" not in environment
    assert "OPENAI_API_KEY" not in environment
    assert environment["SAFE_BRIDGE_TEST_VALUE"] == "retained"


def test_status_read_is_local_and_verification_failure_remains_visible(monkeypatch) -> None:
    transport = MemoryTransport(
        [_response(429, {"detail": {"code": "CODEX_USAGE_LIMITED"}})]
    )
    adapter = CodexChatGPTAdapter(
        CodexChatGPTConfig(bridge_url="http://bridge.test", access_token="z" * 32),
        _settings(),
        transport=transport,
        transport_is_mock=True,
    )
    monkeypatch.setattr(
        DefaultModelAdapterFactory,
        "create",
        lambda self, adapter_id, **kwargs: adapter,
    )
    settings = _settings(
        model_execution_adapter="codex_chatgpt",
        codex_bridge_url="http://bridge.test",
        codex_bridge_token="z" * 32,
    )
    with TestClient(create_app(settings)) as client:
        before = client.get("/api/v1/model-execution/status")
        assert transport.requests == []
        failed = client.post(
            "/api/v1/model-execution/providers/codex_chatgpt:verify",
            json={"perform_generation": False},
        )
        after = client.get("/api/v1/model-execution/status")

    assert before.status_code == 200
    assert failed.status_code == 429
    provider = next(
        item for item in after.json()["providers"] if item["provider_id"] == "codex_chatgpt"
    )
    assert provider["verification_status"] == "failed"
    assert provider["authentication_status"] == "usage_limited"
    assert provider["generation_verified"] is False
    assert provider["verification_error_code"] == "CODEX_CHATGPT_USAGE_LIMITED"


def test_codex_authentication_and_generation_verification_are_separate(monkeypatch) -> None:
    transport = MemoryTransport(
        [
            _response(
                200,
                {
                    "authentication_status": "authenticated",
                    "models": [
                        {
                            "id": "account-model",
                            "display_name": "Account model",
                            "is_default": True,
                            "reasoning_efforts": ["low"],
                        }
                    ],
                    "rate_limits": None,
                    "codex_version": "codex-cli/0.test",
                    "protocol_compatible": True,
                },
            ),
            _response(
                200,
                {
                    "answer": "OK",
                    "actual_model": None,
                    "finish_reason": "stop",
                    "latency_ms": 1,
                    "usage": None,
                    "provider_request_id": "turn-verify",
                },
            ),
        ]
    )
    adapter = CodexChatGPTAdapter(
        CodexChatGPTConfig(bridge_url="http://bridge.test", access_token="z" * 32),
        _settings(),
        transport=transport,
        transport_is_mock=True,
    )
    monkeypatch.setattr(
        DefaultModelAdapterFactory,
        "create",
        lambda self, adapter_id, **kwargs: adapter,
    )
    settings = _settings(
        model_execution_adapter="codex_chatgpt",
        codex_bridge_url="http://bridge.test",
        codex_bridge_token="z" * 32,
    )
    with TestClient(create_app(settings)) as client:
        verified = client.post(
            "/api/v1/model-execution/providers/codex_chatgpt:verify",
            json={"model": "account-model", "perform_generation": True},
        )
        status_response = client.get("/api/v1/model-execution/status")

    assert verified.status_code == 200
    assert verified.json()["authentication_status"] == "authenticated"
    assert verified.json()["generation_verified"] is True
    assert verified.json()["configuration_status"] == "verified"
    assert [item.method for item in transport.requests] == ["GET", "POST"]
    provider = next(
        item
        for item in status_response.json()["providers"]
        if item["provider_id"] == "codex_chatgpt"
    )
    assert provider["verification_status"] == "succeeded"
    assert provider["generation_verified"] is True
    assert provider["rate_limits"] is None


def test_provider_base_urls_are_explicit_roots() -> None:
    with pytest.raises(ValidationError, match="not /chat/completions"):
        _settings(openai_compat_base_url="https://provider.test/v1/chat/completions")
    with pytest.raises(ValidationError, match="must not include the /v1 suffix"):
        _settings(codex_bridge_url="http://127.0.0.1:8765/v1")


def test_openai_connection_test_requires_explicit_charge_confirmation() -> None:
    settings = _settings(
        model_execution_adapter="openai_compatible",
        openai_compat_base_url="https://provider.invalid/v1",
        openai_compat_api_key="secret",
        openai_compat_default_model="provider-model",
    )
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/model-execution/providers/openai_compatible:verify",
            json={"perform_generation": False},
        )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "GENERATION_CONFIRMATION_REQUIRED"
