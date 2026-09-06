from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.execution.adapters import (
    CodexBridgeConfig,
    CodexChatGPTAdapter,
    OpenAICompatibleAdapter,
    OpenAICompatibleConfig,
)
from app.execution.executor import ModelEvaluationExecutor
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
from app.persistence.models import DatasetSample
from app.schemas.jobs import EvaluationJobCreate
from app.services import jobs as job_service


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
        "codex_bridge_base_url": "http://host.docker.internal:8765",
        "codex_bridge_token": "BRIDGE-SECRET-TOKEN-AT-LEAST-32-CHARS",
        "codex_default_model": "codex-test-model",
        "openai_compat_base_url": "https://provider.invalid/v1",
        "openai_compat_api_key": "OPENAI-SECRET-KEY",
        "openai_compat_default_model": "openai-test-model",
    }
    values.update(overrides)
    return Settings(**values)


def _codex_adapter(
    transport: MemoryTransport,
    **settings_overrides: object,
) -> CodexChatGPTAdapter:
    return CodexChatGPTAdapter(
        CodexBridgeConfig(
            base_url="http://host.docker.internal:8765",
            bearer_token="BRIDGE-SECRET-TOKEN-AT-LEAST-32-CHARS",
            default_model="codex-test-model",
        ),
        _settings(**settings_overrides),
        transport=transport,
        transport_is_mock=True,
    )


def _request(**generation: object) -> ModelRequest:
    return ModelRequest(
        question="What is the policy?",
        context=[ModelContext(position=1, text="Only this safe context is visible.")],
        prompt="Use only context.",
        generation=GenerationConfig(model="codex-test-model", **generation),
    )


def _response(status_code: int, body: object, **headers: str) -> ModelTransportResponse:
    return ModelTransportResponse(
        status_code=status_code,
        headers=headers,
        body=json.dumps(body).encode(),
    )


def _codex_success(answer: str = "bridge answer") -> ModelTransportResponse:
    return _response(
        200,
        {
            "contract_version": "1.0",
            "answer": answer,
            "actual_model": None,
            "finish_reason": "stop",
            "usage": None,
            "provider_request_id": None,
            "session_isolated": True,
        },
        **{"x-request-id": "bridge-http-request"},
    )


def test_codex_maps_only_fixed_contract_fields_and_uses_independent_sessions() -> None:
    transport = MemoryTransport([_codex_success("first"), _codex_success("second")])
    adapter = _codex_adapter(transport)

    first = adapter.generate(_request())
    second = adapter.generate(_request())

    assert [first.answer, second.answer] == ["first", "second"]
    assert first.actual_model is None
    assert first.usage is None
    assert first.provider_request_id == "bridge-http-request"
    sent = transport.requests[0]
    assert sent.url == "http://host.docker.internal:8765/v1/generate"
    assert sent.headers["authorization"] == "Bearer BRIDGE-SECRET-TOKEN-AT-LEAST-32-CHARS"
    assert sent.json_body is not None
    assert sent.json_body["contract_version"] == "1.0"
    assert sent.json_body["session_mode"] == "isolated_ephemeral"
    assert sent.json_body["instructions"] == "Use only context."
    assert sent.json_body["input"] == {
        "question": "What is the policy?",
        "contexts": [{"position": 1, "text": "Only this safe context is visible."}],
    }
    assert "temperature" not in sent.json_body
    assert "top_p" not in sent.json_body
    assert "max_output_tokens" not in sent.json_body
    assert transport.requests[0].json_body["request_id"] != transport.requests[1].json_body[
        "request_id"
    ]


def test_codex_redacts_a_bridge_token_reflected_by_the_bridge() -> None:
    secret = "BRIDGE-SECRET-TOKEN-AT-LEAST-32-CHARS"
    transport = MemoryTransport(
        [
            _response(
                200,
                {
                    "contract_version": "1.0",
                    "answer": f"unsafe {secret}",
                    "actual_model": secret,
                    "finish_reason": None,
                    "usage": None,
                    "provider_request_id": secret,
                    "session_isolated": True,
                },
                **{"x-request-id": secret},
            )
        ]
    )

    response = _codex_adapter(transport).generate(_request())

    assert response.answer == "unsafe [REDACTED]"
    assert response.actual_model is None
    assert response.provider_request_id is None
    assert secret not in response.model_dump_json()


@pytest.mark.parametrize(
    ("generation", "field"),
    [
        ({"temperature": 0.1}, "temperature"),
        ({"top_p": 0.9}, "top_p"),
        ({"max_output_tokens": 100}, "max_output_tokens"),
        ({"stop": ["END"]}, "stop"),
        ({"seed": 7}, "seed"),
    ],
)
def test_codex_rejects_unsupported_generation_values_before_transport(
    generation: dict[str, object],
    field: str,
) -> None:
    transport = MemoryTransport([_codex_success()])
    adapter = _codex_adapter(transport)

    with pytest.raises(ModelError) as caught:
        adapter.generate(_request(**generation))

    assert caught.value.code == ModelErrorCode.capability_unsupported, field
    assert transport.requests == []


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (_response(401, {"error": {"code": "PRIVATE"}}), ModelErrorCode.authentication_failed),
        (_response(409, {"error": {"code": "CODEX_NOT_LOGGED_IN"}}), ModelErrorCode.not_logged_in),
        (_response(429, {"error": {"code": "CODEX_QUOTA_EXCEEDED"}}), ModelErrorCode.quota_exceeded),
        (_response(429, {"error": {"code": "RATE_LIMIT"}}), ModelErrorCode.rate_limited),
        (_response(408, {}), ModelErrorCode.timeout),
        (_response(499, {}), ModelErrorCode.cancelled),
        (_response(503, {"private": "raw"}), ModelErrorCode.server_error),
        (_response(200, {"unexpected": "raw"}), ModelErrorCode.response_invalid),
    ],
)
def test_codex_error_matrix_is_safe_and_never_retried(
    response: ModelTransportResponse,
    expected: ModelErrorCode,
) -> None:
    transport = MemoryTransport([response])
    adapter = _codex_adapter(transport)

    with pytest.raises(ModelError) as caught:
        adapter.generate(_request())

    assert caught.value.code == expected
    assert caught.value.attempts == 1
    assert len(transport.requests) == 1
    assert "raw" not in caught.value.message
    assert "BRIDGE-SECRET-TOKEN-AT-LEAST-32-CHARS" not in caught.value.message
    assert adapter.last_attempts[0].retry_delay_ms == 0


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (TimeoutError(), ModelErrorCode.timeout),
        (ConnectionError(), ModelErrorCode.transport_error),
        (asyncio.CancelledError(), ModelErrorCode.cancelled),
    ],
)
def test_codex_transport_failures_are_single_attempt(
    failure: BaseException,
    expected: ModelErrorCode,
) -> None:
    transport = MemoryTransport([failure])
    adapter = _codex_adapter(transport)
    with pytest.raises(ModelError) as caught:
        adapter.generate(_request())
    assert caught.value.code == expected
    assert len(transport.requests) == 1


def test_codex_disabled_external_calls_make_zero_requests() -> None:
    transport = MemoryTransport([_codex_success()])
    adapter = CodexChatGPTAdapter(
        CodexBridgeConfig(
            base_url="http://host.docker.internal:8765",
            bearer_token="BRIDGE-SECRET-TOKEN-AT-LEAST-32-CHARS",
        ),
        _settings(model_external_calls_enabled=False),
        transport=transport,
        transport_is_mock=False,
    )
    with pytest.raises(ModelError) as caught:
        adapter.generate(_request())
    assert caught.value.code == ModelErrorCode.external_calls_disabled
    assert transport.requests == []


def test_openai_quota_and_cancellation_are_not_retried() -> None:
    for scripted, expected in [
        (
            _response(429, {"error": {"code": "insufficient_quota", "message": "private"}}),
            ModelErrorCode.quota_exceeded,
        ),
        (asyncio.CancelledError(), ModelErrorCode.cancelled),
    ]:
        transport = MemoryTransport([scripted])
        adapter = OpenAICompatibleAdapter(
            OpenAICompatibleConfig(
                base_url="https://provider.invalid/v1",
                api_key="OPENAI-SECRET-KEY",
                default_model="openai-test-model",
            ),
            _settings(),
            transport=transport,
            transport_is_mock=True,
            sleeper=lambda _: None,
        )
        with pytest.raises(ModelError) as caught:
            adapter.generate(_request())
        assert caught.value.code == expected
        assert len(transport.requests) == 1


def test_executor_does_not_leak_labels_metadata_or_history_to_codex() -> None:
    sentinel = "DO-NOT-LEAK-SENTINEL"
    transport = MemoryTransport([_codex_success()])
    executor = ModelEvaluationExecutor(
        _codex_adapter(transport),
        {
            "adapter_id": "codex_chatgpt",
            "provider_id": "codex_chatgpt",
            "prompt": {"version": "v1", "text": "Use visible inputs."},
            "generation": GenerationConfig(model="codex-test-model").model_dump(mode="json"),
            "context_policy": "dataset_contexts",
            "metric_config": [],
        },
    )
    sample = DatasetSample(
        external_id=f"sample-{sentinel}",
        question="Safe question",
        reference_answer=sentinel,
        gold_document_ids=[sentinel],
        gold_evidence_ids=[sentinel],
        retrieved_contexts=[
            {
                "rank": 1,
                "doc_id": sentinel,
                "chunk_id": sentinel,
                "evidence_ids": [sentinel],
                "text": "Safe model context",
            }
        ],
        answer=sentinel,
        historical_answer=sentinel,
        citations=[],
        historical_citations=[],
        tags=[sentinel],
        expected_diagnoses=[sentinel],
        metadata_json={sentinel: sentinel},
        content_sha256="0" * 64,
    )

    executor.generate(sample)

    serialized = json.dumps(transport.requests[0].json_body)
    assert sentinel not in serialized
    assert "Safe question" in serialized
    assert "Safe model context" in serialized


class StaticFactory:
    def __init__(self, adapter: CodexChatGPTAdapter) -> None:
        self.adapter = adapter
        self.calls: list[str] = []

    def create(self, adapter_id: str, server_config=None, *, test_transport=None):
        self.calls.append(adapter_id)
        assert adapter_id == "codex_chatgpt"
        return self.adapter


def test_status_is_local_and_login_and_generation_verification_are_separate() -> None:
    transport = MemoryTransport(
        [
            _response(
                200,
                {
                    "contract_version": "1.0",
                    "login_status": "logged_in",
                    "codex_version": "codex-cli 1.2.3",
                    "available_models": ["codex-test-model"],
                    "rate_limits": {
                        "primary": {
                            "used_percent": 25,
                            "window_duration_minutes": 15,
                            "resets_at": 1_800_000_000,
                        },
                        "secondary": None,
                        "rate_limit_reached": False,
                    },
                },
            ),
            _codex_success("OK"),
        ]
    )
    adapter = _codex_adapter(transport)
    settings = _settings(model_execution_adapter="codex_chatgpt")
    with TestClient(create_app(settings)) as client:
        client.app.state.model_adapter_factory = StaticFactory(adapter)

        initial = client.get("/api/v1/model-execution/status")
        assert transport.requests == []
        assert initial.json()["execution_available"] is True
        initial_codex = initial.json()["providers"][1]
        assert initial_codex["login_status"] == "unknown"
        assert initial_codex["generation_verified"] is False

        login = client.post("/api/v1/model-execution/providers/codex_chatgpt/verify-login")
        assert login.status_code == 200, login.text
        assert login.json()["login_status"] == "logged_in"
        assert login.json()["generation_verified"] is False
        assert [item.method for item in transport.requests] == ["GET"]

        generated = client.post(
            "/api/v1/model-execution/providers/codex_chatgpt/verify-generation",
            json={"model": "codex-test-model"},
        )
        assert generated.status_code == 200, generated.text
        assert generated.json()["generation_verified"] is True
        assert generated.json()["actual_model"] is None
        assert generated.json()["usage"] is None
        assert generated.json()["cost"] is None
        assert [item.method for item in transport.requests] == ["GET", "POST"]

        current = client.get("/api/v1/model-execution/status").json()
        assert current["providers"][1]["generation_verified"] is True
        assert "BRIDGE-SECRET-TOKEN-AT-LEAST-32-CHARS" not in json.dumps(current)


class OpenAIStaticFactory:
    def __init__(self, adapter: OpenAICompatibleAdapter) -> None:
        self.adapter = adapter

    def create(self, adapter_id: str, server_config=None, *, test_transport=None):
        assert adapter_id == "openai_compatible"
        return self.adapter


def test_openai_generation_verification_is_explicit_minimal_and_secret_free() -> None:
    transport = MemoryTransport(
        [_response(200, {"choices": [{"message": {"content": "OK"}}]})]
    )
    settings = _settings(model_execution_adapter="openai_compatible")
    adapter = OpenAICompatibleAdapter(
        OpenAICompatibleConfig(
            base_url="https://provider.invalid/v1",
            api_key="OPENAI-SECRET-KEY",
            default_model="openai-test-model",
        ),
        settings,
        transport=transport,
        transport_is_mock=True,
        sleeper=lambda _: None,
    )
    with TestClient(create_app(settings)) as client:
        client.app.state.model_adapter_factory = OpenAIStaticFactory(adapter)
        assert client.get("/api/v1/model-execution/status").json()["providers"][0][
            "generation_verified"
        ] is False
        assert transport.requests == []

        verified = client.post(
            "/api/v1/model-execution/providers/openai_compatible/verify-generation",
            json={},
        )

        assert verified.status_code == 200, verified.text
        assert verified.json()["requested_model"] == "openai-test-model"
        assert verified.json()["actual_model"] is None
        assert verified.json()["usage"] is None
        assert verified.json()["cost"] is None
        assert len(transport.requests) == 1
        assert transport.requests[0].url == "https://provider.invalid/v1/chat/completions"
        assert transport.requests[0].json_body["messages"][1]["content"] == (
            "Question:\nReply with exactly OK.\n\nContext:\n(none)"
        )
        status = client.get("/api/v1/model-execution/status")
        assert status.json()["providers"][0]["generation_verified"] is True
        assert "OPENAI-SECRET-KEY" not in status.text


def _sample() -> dict[str, object]:
    return {
        "schema_version": "2.0",
        "sample_id": "codex-sample-1",
        "question": "What is the policy?",
        "labels": {
            "reference_answer": "PRIVATE-REFERENCE",
            "gold_document_ids": [],
            "gold_evidence_ids": [],
            "expected_diagnoses": [],
        },
        "contexts": [
            {
                "origin": "provided",
                "rank": 1,
                "rank_before": None,
                "retrieval_run_id": None,
                "doc_id": "safe-doc",
                "chunk_id": "safe-chunk",
                "evidence_ids": [],
                "text": "Safe context.",
                "score": None,
                "relevance_grade": None,
                "usefulness": None,
            }
        ],
        "historical_output": None,
        "tags": [],
        "metadata": {"private": "PRIVATE-METADATA"},
    }


def _job(dataset_id: str) -> dict[str, object]:
    return {
        "schema_version": "2.0",
        "dataset_id": dataset_id,
        "execution": {
            "adapter_id": "codex_chatgpt",
            "prompt": {"version": "v1", "text": "Use context."},
            "generation": {
                "model": "codex-test-model",
                "temperature": 0,
                "top_p": 1,
                "max_output_tokens": 512,
                "stop": [],
                "seed": None,
            },
            "context_policy": "dataset_contexts",
        },
    }


def test_codex_job_snapshot_and_report_keep_requested_effective_and_unknown_values() -> None:
    settings = _settings(auto_create_schema=True)
    transport = MemoryTransport([_codex_success()])
    adapter = _codex_adapter(transport)
    factory = StaticFactory(adapter)
    with TestClient(create_app(settings)) as client:
        created_dataset = client.post(
            "/api/v1/datasets",
            json={
                "name": "codex-contract",
                "owner": "tests",
                "version": "v1",
                "schema_version": "2.0",
                "samples": [_sample()],
            },
        )
        dataset_id = created_dataset.json()["id"]
        client.post(f"/api/v1/datasets/{dataset_id}:publish")
        payload = EvaluationJobCreate.model_validate(_job(dataset_id))
        with client.app.state.database.session() as session:
            job, created = job_service.create_job(
                session,
                payload,
                idempotency_key=None,
                settings=settings,
            )
            job_id = job.id
            snapshot = dict(job.execution_snapshot)
        assert created is True
        assert snapshot["provider_id"] == "codex_chatgpt"
        assert snapshot["requested_generation"]["max_output_tokens"] == 512
        assert snapshot["effective_generation"] == {"model": "codex-test-model"}
        assert "PRIVATE-REFERENCE" not in json.dumps(snapshot)
        assert "PRIVATE-METADATA" not in json.dumps(snapshot)

        job_service.execute_job(
            client.app.state.database,
            job_id,
            settings,
            adapter_factory=factory,
        )

        sample = client.get(f"/api/v1/evaluation-jobs/{job_id}/samples").json()["items"][0]
        report = client.get(f"/api/v1/evaluation-jobs/{job_id}/report").json()
        assert factory.calls == ["codex_chatgpt"]
        assert sample["run"]["adapter_id"] == "codex_chatgpt"
        assert sample["run"]["provider_id"] == "codex_chatgpt"
        assert sample["run"]["actual_model"] is None
        assert sample["run"]["usage"] is None
        assert sample["run"]["cost"] is None
        assert sample["run"]["effective_generation"] == {"model": "codex-test-model"}
        assert report["execution_snapshot"]["provider_id"] == "codex_chatgpt"
