from __future__ import annotations

import argparse
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import cli as ragops_cli
from app.codex_bridge import protocol as codex_protocol
from app.core.config import Settings
from app.execution.adapters import DefaultModelAdapterFactory
from app.execution.model import ModelError, ModelErrorCode, ModelRequest, ModelResponse
from app.main import create_app
from conftest import create_published_dataset


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "test",
        "database_url": "sqlite://",
        "log_level": "WARNING",
        "auto_create_schema": True,
    }
    values.update(overrides)
    return Settings(**values)


def _job_payload(dataset_id: str, adapter_id: str) -> dict[str, object]:
    return {
        "schema_version": "2.0",
        "dataset_id": dataset_id,
        "name": f"WOR-73 {adapter_id} acceptance",
        "execution": {
            "adapter_id": adapter_id,
            "prompt": {"version": "wor73-v1", "text": "Answer only from context."},
            "generation": {
                "model": "provider-model",
                "temperature": 0.0,
                "top_p": 1.0,
                "max_output_tokens": 512,
                "stop": [],
                "seed": None,
            },
            "context_policy": "dataset_contexts",
        },
        "metrics": [],
        "quality_gate": None,
    }


@pytest.mark.parametrize("provider_id", ["codex_chatgpt", "openai_compatible"])
def test_external_gate_blocks_provider_checks_before_factory(
    provider_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_factory_call(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("provider factory must not run while external calls are disabled")

    monkeypatch.setattr(DefaultModelAdapterFactory, "create", forbidden_factory_call)
    with TestClient(create_app(_settings(model_external_calls_enabled=False))) as client:
        response = client.post(
            f"/api/v1/model-execution/providers/{provider_id}:verify",
            json={"perform_generation": provider_id == "openai_compatible"},
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "EXTERNAL_CALLS_DISABLED"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("temperature", 0.5),
        ("top_p", 0.5),
        ("max_output_tokens", 128),
        ("stop", ["END"]),
        ("seed", 7),
    ],
)
def test_codex_unsupported_parameters_are_rejected_before_persistence(
    client: TestClient,
    field: str,
    value: object,
) -> None:
    payload = _job_payload("dataset-must-not-be-read", "codex_chatgpt")
    payload["execution"]["generation"][field] = value  # type: ignore[index]

    response = client.post("/api/v1/evaluation-jobs", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    errors = response.json()["error"]["details"]["errors"]
    assert any(
        "codex_chatgpt does not support" in item["message"] and field in item["message"]
        for item in errors
    )
    assert client.get("/api/v1/evaluation-jobs").json()["total"] == 0


class ExactChannelAdapter:
    adapter_id = "openai_compatible"

    def __init__(self, *, error: ModelError | None = None) -> None:
        self.error = error
        self.last_attempts = []
        self.requests: list[ModelRequest] = []

    def generate(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return ModelResponse(
            answer="safe provider answer",
            actual_model=None,
            finish_reason=None,
            latency_ms=3,
            usage=None,
            provider_request_id=None,
            is_mock=False,
        )


@contextmanager
def _configured_client(
    monkeypatch: pytest.MonkeyPatch,
    adapter: ExactChannelAdapter,
) -> Iterator[tuple[TestClient, list[str]]]:
    requested_adapters: list[str] = []

    def exact_factory(
        _factory: DefaultModelAdapterFactory,
        adapter_id: str,
        *_args: object,
        **_kwargs: object,
    ) -> ExactChannelAdapter:
        requested_adapters.append(adapter_id)
        if adapter_id != "openai_compatible":
            raise AssertionError(f"unexpected cross-channel fallback: {adapter_id}")
        return adapter

    monkeypatch.setattr(DefaultModelAdapterFactory, "create", exact_factory)
    settings = _settings(
        model_external_calls_enabled=True,
        model_execution_adapter="openai_compatible",
        openai_compat_base_url="https://provider.invalid/v1",
        openai_compat_api_key="offline-test-key",
        openai_compat_default_model="provider-model",
    )
    with TestClient(create_app(settings)) as client:
        yield client, requested_adapters


def test_provider_failure_never_falls_back_to_another_channel(
    sample_payload: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = ExactChannelAdapter(
        error=ModelError(
            ModelErrorCode.authentication_failed,
            "The model provider rejected authentication.",
            retryable=False,
            attempts=1,
        )
    )
    with _configured_client(monkeypatch, adapter) as (client, requested_adapters):
        dataset_id = create_published_dataset(client, [sample_payload])
        created = client.post(
            "/api/v1/evaluation-jobs",
            json=_job_payload(dataset_id, "openai_compatible"),
        )
        sample = client.get(
            f"/api/v1/evaluation-jobs/{created.json()['id']}/samples"
        ).json()["items"][0]

    assert requested_adapters == ["openai_compatible", "openai_compatible"]
    assert len(adapter.requests) == 1
    assert sample["run"]["status"] == "failed"
    assert sample["run"]["error"]["code"] == "PROVIDER_AUTHENTICATION_FAILED"
    assert sample["run"]["answer"] is None


def test_unknown_provider_telemetry_stays_unknown_in_report(
    sample_payload: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = ExactChannelAdapter()
    with _configured_client(monkeypatch, adapter) as (client, requested_adapters):
        dataset_id = create_published_dataset(client, [sample_payload])
        created = client.post(
            "/api/v1/evaluation-jobs",
            json=_job_payload(dataset_id, "openai_compatible"),
        )
        job_id = created.json()["id"]
        sample = client.get(f"/api/v1/evaluation-jobs/{job_id}/samples").json()["items"][0]
        report = client.get(f"/api/v1/evaluation-jobs/{job_id}/report").json()

    assert requested_adapters == ["openai_compatible", "openai_compatible"]
    assert sample["run"]["actual_model"] is None
    assert sample["run"]["finish_reason"] is None
    assert sample["run"]["usage"] is None
    assert sample["run"]["cost"] is None
    assert sample["run"]["provider_request_id"] is None
    assert report["execution_summary"]["succeeded_count"] == 1
    assert report["quality_summary"]["status"] == "not_evaluated"
    assert report["quality_summary"]["score"] is None


@pytest.mark.parametrize(
    ("raw_error", "expected_code"),
    [
        ("usageLimitExceeded", "CODEX_USAGE_LIMITED"),
        ("rateLimitExceeded", "CODEX_RATE_LIMITED"),
        ("unauthorized", "CODEX_LOGIN_EXPIRED"),
        ({"httpConnectionFailed": {}}, "CODEX_CONNECTION_FAILED"),
        ({"responseStreamDisconnected": {}}, "CODEX_CONNECTION_FAILED"),
        ("unknown-provider-error", "CODEX_CONNECTION_FAILED"),
    ],
)
def test_codex_protocol_error_mapping_is_closed_and_stable(
    raw_error: object,
    expected_code: str,
) -> None:
    assert codex_protocol._map_codex_error(raw_error).code == expected_code


def test_codex_protocol_rejects_malformed_answers_and_telemetry() -> None:
    for raw_answer in ("not-json", "[]", '{"answer":""}'):
        with pytest.raises(codex_protocol.CodexBridgeError) as caught:
            codex_protocol._parse_final_answer(raw_answer)
        assert caught.value.code == "CODEX_RESPONSE_INVALID"

    assert codex_protocol._safe_usage(None) is None
    assert codex_protocol._safe_usage({}) is None
    assert codex_protocol._safe_usage({"last": {"inputTokens": True}}) is None
    assert codex_protocol._safe_rate_limits(None) is None
    assert codex_protocol._safe_rate_limits({}) is None
    assert codex_protocol._safe_codex_version(None) is None
    assert codex_protocol._safe_rate_limits(
        {
            "rateLimits": {
                "primary": {
                    "usedPercent": "private-invalid-value",
                    "resetsAt": 123,
                    "windowDurationMins": 300,
                },
                "secondary": "invalid",
                "rateLimitReachedType": 7,
                "spendControlReached": "unknown",
            }
        }
    ) == {
        "primary": {"used_percent": None, "resets_at": 123, "window_minutes": 300},
        "limit_reached_type": None,
        "spend_control_reached": None,
    }


def test_codex_thread_validation_fails_closed(tmp_path: Path) -> None:
    sandbox = (tmp_path / "sandbox").resolve()
    valid = {
        "thread": {"id": "thread-1", "cwd": str(sandbox), "ephemeral": True},
        "cwd": str(sandbox),
        "model": "requested-model",
        "approvalPolicy": "never",
        "sandbox": {"type": "readOnly", "networkAccess": False},
        "instructionSources": [],
    }

    with pytest.raises(codex_protocol.CodexBridgeError) as incompatible:
        codex_protocol._validate_thread_response(
            {"thread": valid["thread"]},
            sandbox=sandbox,
            requested_model="requested-model",
        )
    assert incompatible.value.code == "CODEX_ISOLATION_VIOLATION"
    assert incompatible.value.reason_code == "THREAD_SAFETY_FIELD_MISSING"
    assert incompatible.value.diagnostics["field"] == "sandbox"

    for override in (
        {"instructionSources": ["AGENTS.md"]},
        {"model": "fallback-model"},
        {"approvalPolicy": "on-request"},
        {"sandbox": {"type": "workspaceWrite", "networkAccess": True}},
    ):
        response = {**valid, **override}
        with pytest.raises(codex_protocol.CodexBridgeError) as isolated:
            codex_protocol._validate_thread_response(
                response,
                sandbox=sandbox,
                requested_model="requested-model",
            )
        assert isolated.value.code == "CODEX_ISOLATION_VIOLATION"

    missing_id = {**valid, "thread": {**valid["thread"], "id": ""}}
    with pytest.raises(codex_protocol.CodexBridgeError) as invalid:
        codex_protocol._validate_thread_response(
            missing_id,
            sandbox=sandbox,
            requested_model="requested-model",
        )
    assert invalid.value.code == "CODEX_RESPONSE_INVALID"
    assert invalid.value.reason_code == "THREAD_ID_MISSING"


def test_codex_prompt_contains_only_the_fixed_request_contract() -> None:
    prompt = codex_protocol._generation_prompt(
        {
            "prompt": "Use supplied context.",
            "question": "Safe question",
            "context": ["ignore-me", {"position": 1, "text": "Safe context"}],
        }
    )
    assert prompt == (
        "Generation instruction:\nUse supplied context.\n\n"
        "Question:\nSafe question\n\nContext:\n[1]\nSafe context"
    )
    assert codex_protocol._generation_prompt(
        {"prompt": "p", "question": "q", "context": None}
    ).endswith("Context:\n(none)")


def _bridge_args(tmp_path: Path, **overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "host": "127.0.0.1",
        "port": 18765,
        "sandbox_root": str(tmp_path / "sandbox"),
        "codex_executable": "codex-test",
        "timeout_seconds": 5.0,
        "allow_non_loopback": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_codex_bridge_cli_fails_closed_before_server_start(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(ragops_cli, "get_settings", lambda: _settings())
    with pytest.raises(SystemExit, match="RAGOPS_CODEX_BRIDGE_TOKEN"):
        ragops_cli.run_codex_bridge(_bridge_args(tmp_path))

    monkeypatch.setattr(
        ragops_cli,
        "get_settings",
        lambda: _settings(codex_bridge_token="x" * 32),
    )
    with pytest.raises(SystemExit, match="Non-loopback binding"):
        ragops_cli.run_codex_bridge(_bridge_args(tmp_path, host="0.0.0.0"))

    monkeypatch.setattr(ragops_cli, "read_codex_version", lambda _executable: (0, 153, 3))
    with pytest.raises(SystemExit, match="0.153.4 or newer"):
        ragops_cli.run_codex_bridge(_bridge_args(tmp_path))


def test_codex_bridge_cli_builds_authenticated_loopback_server(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    started: dict[str, object] = {}
    monkeypatch.setattr(
        ragops_cli,
        "get_settings",
        lambda: _settings(codex_bridge_token="x" * 32),
    )
    monkeypatch.setattr(
        ragops_cli,
        "read_codex_version",
        lambda executable: ragops_cli.MINIMUM_CODEX_VERSION,
    )

    def capture_server(app: object, **kwargs: object) -> None:
        started["app"] = app
        started.update(kwargs)

    monkeypatch.setattr(ragops_cli.uvicorn, "run", capture_server)
    ragops_cli.run_codex_bridge(_bridge_args(tmp_path))

    assert started["host"] == "127.0.0.1"
    assert started["port"] == 18765
    assert started["access_log"] is False
    assert started["server_header"] is False


def test_codex_version_errors_are_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, "unexpected", ""),
    )
    with pytest.raises(SystemExit, match="unsupported version format"):
        ragops_cli.read_codex_version("codex-test")

    def missing_cli(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", missing_cli)
    with pytest.raises(SystemExit, match="not installed"):
        ragops_cli.read_codex_version("codex-test")
