from __future__ import annotations

import json
import socket
import sqlite3
import time
from collections import deque
from copy import deepcopy
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPO_ROOT / "examples" / "offline-readiness"
RAW_PROVIDER_SECRET = "SENTINEL_RAW_PROVIDER_BODY"
FAKE_API_KEY = "SENTINEL_FAKE_API_KEY_never_log_this"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


VALID_V2 = _load_jsonl(FIXTURE_ROOT / "valid-v2.jsonl")
LEGACY_V1 = _load_jsonl(FIXTURE_ROOT / "legacy-v1.jsonl")
INVALID_V2 = _load_json(FIXTURE_ROOT / "invalid-v2.json")
PROVIDER_RESPONSES = _load_json(FIXTURE_ROOT / "provider-responses.json")


class RecordingMockTransport:
    """Intercept only provider.invalid and fail closed for every real network path."""

    def __init__(self, scripts: list[dict[str, Any]]) -> None:
        self.scripts = deque(deepcopy(scripts))
        self.requests: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if not self.scripts:
            raise AssertionError(f"unexpected provider request: {request.method} {request.url}")
        script = self.scripts.popleft()
        exception = script.get("exception")
        if exception == "timeout":
            raise httpx.ReadTimeout(
                f"{RAW_PROVIDER_SECRET}_timeout",
                request=request,
            )
        if exception == "transport":
            raise httpx.ConnectError(
                f"{RAW_PROVIDER_SECRET}_transport",
                request=request,
            )
        response_kwargs: dict[str, Any] = {
            "status_code": script["status"],
            "headers": script.get("headers", {}),
            "request": request,
        }
        if "json" in script:
            response_kwargs["json"] = script["json"]
        else:
            response_kwargs["content"] = script.get("body", "").encode("utf-8")
        return httpx.Response(**response_kwargs)


def _install_recording_transport(
    monkeypatch: pytest.MonkeyPatch,
    scripts: list[dict[str, Any]],
) -> RecordingMockTransport:
    provider = RecordingMockTransport(scripts)
    mock_transport = httpx.MockTransport(provider.handle)
    original_sync_send = httpx.Client.send
    original_async_send = httpx.AsyncClient.send
    original_getaddrinfo = socket.getaddrinfo

    def sync_send(
        client: httpx.Client,
        request: httpx.Request,
        *args: Any,
        **kwargs: Any,
    ) -> httpx.Response:
        if request.url.host == "provider.invalid":
            return mock_transport.handle_request(request)
        return original_sync_send(client, request, *args, **kwargs)

    async def async_send(
        client: httpx.AsyncClient,
        request: httpx.Request,
        *args: Any,
        **kwargs: Any,
    ) -> httpx.Response:
        if request.url.host == "provider.invalid":
            return provider.handle(request)
        return await original_async_send(client, request, *args, **kwargs)

    def guarded_getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        if str(host).lower() == "provider.invalid":
            raise AssertionError("provider request escaped the in-memory MockTransport")
        return original_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "send", sync_send)
    monkeypatch.setattr(httpx.AsyncClient, "send", async_send)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
    return provider


def _settings(database_path: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "environment": "test",
        "database_url": f"sqlite:///{database_path.as_posix()}",
        "log_level": "WARNING",
        "auto_create_schema": True,
        "model_execution_adapter": "mock",
        "model_external_calls_enabled": False,
        "model_request_timeout_ms": 100,
        "model_total_timeout_ms": 600,
        "model_max_attempts": 3,
        "model_retry_base_ms": 0,
        "model_retry_max_delay_ms": 0,
        "openai_compat_base_url": "https://provider.invalid/v1",
        "openai_compat_auth_mode": "bearer",
        "openai_compat_api_key": FAKE_API_KEY,
        "openai_compat_default_model": "synthetic-request-model-v1",
    }
    values.update(overrides)
    return Settings(**values)


def _create_dataset(
    client: TestClient,
    samples: list[dict[str, Any]],
    *,
    schema_version: str = "2.0",
) -> tuple[str, str]:
    created = client.post(
        "/api/v1/datasets",
        json={
            "name": f"offline-contract-{uuid4()}",
            "description": "Synthetic offline contract acceptance data.",
            "owner": "qa",
            "version": "v2" if schema_version == "2.0" else "v1",
            "schema_version": schema_version,
        },
    )
    assert created.status_code == 201, created.text
    dataset_id = created.json()["id"]
    imported = client.post(
        f"/api/v1/datasets/{dataset_id}/samples:import",
        json={"samples": samples},
    )
    assert imported.status_code == 201, imported.text
    assert imported.json()["accepted"] == len(samples)
    published = client.post(f"/api/v1/datasets/{dataset_id}:publish")
    assert published.status_code == 200, published.text
    content_sha256 = published.json()["content_sha256"]
    assert len(content_sha256) == 64
    return dataset_id, content_sha256


def _job_payload(
    dataset_id: str,
    *,
    adapter_id: str,
    metrics: list[dict[str, Any]] | None = None,
    context_policy: str = "dataset_contexts",
) -> dict[str, Any]:
    return {
        "schema_version": "2.0",
        "dataset_id": dataset_id,
        "name": f"offline-contract-{adapter_id}",
        "execution": {
            "adapter_id": adapter_id,
            "prompt": {
                "version": "offline-contract-v1",
                "text": "仅依据给定上下文回答；证据不足时明确说明。",
            },
            "generation": {
                "model": (
                    "mock-ragops-v1"
                    if adapter_id == "mock"
                    else "synthetic-request-model-v1"
                ),
                "temperature": 0.25,
                "top_p": 0.8,
                "max_output_tokens": 321,
                "stop": ["END"],
                "seed": 7,
            },
            "context_policy": context_policy,
        },
        "metrics": metrics or [],
        "quality_gate": None,
    }


def _create_job(
    client: TestClient,
    dataset_id: str,
    *,
    adapter_id: str,
    metrics: list[dict[str, Any]] | None = None,
    context_policy: str = "dataset_contexts",
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/evaluation-jobs",
        headers={"Idempotency-Key": f"offline-contract-{uuid4()}"},
        json=_job_payload(
            dataset_id,
            adapter_id=adapter_id,
            metrics=metrics,
            context_policy=context_policy,
        ),
    )
    assert response.status_code == 202, response.text
    job_id = response.json()["id"]
    completed = client.get(f"/api/v1/evaluation-jobs/{job_id}")
    assert completed.status_code == 200, completed.text
    return completed.json()


def _only_sample(client: TestClient, job_id: str) -> dict[str, Any]:
    response = client.get(f"/api/v1/evaluation-jobs/{job_id}/samples")
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
    return response.json()["items"][0]


def _metric(sample: dict[str, Any], name: str) -> dict[str, Any]:
    return next(item for item in sample["metric_results"] if item["metric_name"] == name)


def _provider_payload(request: httpx.Request) -> dict[str, Any]:
    return json.loads(request.content.decode("utf-8"))


def _assert_error(response: httpx.Response, status_code: int, code: str) -> dict[str, Any]:
    assert response.status_code == status_code, response.text
    error = response.json()["error"]
    assert error["code"] == code
    assert error["request_id"]
    return error


def _sample_storage_state(database_path: Path, external_id: str) -> tuple[Any, ...]:
    with sqlite3.connect(database_path) as connection:
        return connection.execute(
            """
            SELECT content_sha256, reference_answer, gold_document_ids,
                   gold_evidence_ids, historical_answer, metadata
            FROM dataset_samples
            WHERE external_id = ?
            """,
            (external_id,),
        ).fetchone()


def test_a01_openai_request_response_mapping_and_optional_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _install_recording_transport(
        monkeypatch,
        [PROVIDER_RESPONSES["success_full"], PROVIDER_RESPONSES["success_nullable"]],
    )
    settings = _settings(
        tmp_path / "a01.sqlite",
        model_execution_adapter="openai_compatible",
        model_external_calls_enabled=True,
    )

    with TestClient(create_app(settings)) as client:
        dataset_id, _ = _create_dataset(client, [VALID_V2[0]])
        first = _create_job(client, dataset_id, adapter_id="openai_compatible")
        first_sample = _only_sample(client, first["id"])
        second = _create_job(client, dataset_id, adapter_id="openai_compatible")
        second_sample = _only_sample(client, second["id"])
        status = client.get("/api/v1/model-execution/status")

    assert len(provider.requests) == 2
    request = provider.requests[0]
    payload = _provider_payload(request)
    assert request.url == "https://provider.invalid/v1/chat/completions"
    assert request.headers["authorization"] == f"Bearer {FAKE_API_KEY}"
    assert payload["model"] == "synthetic-request-model-v1"
    assert payload["temperature"] == 0.25
    assert payload["top_p"] == 0.8
    assert payload["max_tokens"] == 321
    assert payload["stop"] == ["END"]
    assert payload["seed"] == 7
    assert [message["role"] for message in payload["messages"]] == ["system", "user"]
    user_message = payload["messages"][1]["content"]
    assert user_message.index("[1]") < user_message.index("[2]")
    assert "在演示租户的安全设置中选择“轮换访问令牌”。" in user_message
    assert "轮换后，旧令牌会立即失效。" in user_message

    first_run = first_sample["run"]
    assert first_run["answer"] == "在安全设置中选择轮换访问令牌。"
    assert first_run["actual_model"] == "synthetic-provider-model-v9"
    assert first_run["finish_reason"] == "stop"
    assert first_run["usage"] == {
        "input_tokens": 31,
        "output_tokens": 12,
        "total_tokens": 43,
    }
    assert first_run["provider_request_id"] == "provider-request-synthetic-001"
    assert first_run["is_mock"] is True
    assert first_run["latency_ms"] >= 0

    second_run = second_sample["run"]
    assert second_run["answer"] == "synthetic response without optional fields"
    assert second_run["actual_model"] is None
    assert second_run["finish_reason"] is None
    assert second_run["usage"] is None
    assert second_run["provider_request_id"] is None
    assert status.status_code == 200
    provider_state = status.json()["providers"][0]
    assert provider_state["configuration_status"] == "configured_unverified"
    assert provider_state["last_verified_at"] is None


def test_a02_all_labels_history_metadata_and_internal_ids_stay_out_of_provider_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _install_recording_transport(
        monkeypatch,
        [PROVIDER_RESPONSES["success_full"]],
    )
    settings = _settings(
        tmp_path / "a02.sqlite",
        model_execution_adapter="openai_compatible",
        model_external_calls_enabled=True,
    )

    with TestClient(create_app(settings)) as client:
        dataset_id, _ = _create_dataset(client, [VALID_V2[0]])
        _create_job(client, dataset_id, adapter_id="openai_compatible")

    assert len(provider.requests) == 1
    serialized = provider.requests[0].content.decode("utf-8")
    for sentinel in (
        "SENTINEL_REFERENCE_7f0b3f",
        "SENTINEL_GOLD_DOCUMENT_7f0b3f",
        "SENTINEL_GOLD_EVIDENCE_7f0b3f",
        "SENTINEL_DIAGNOSIS_7f0b3f",
        "SENTINEL_CONTEXT_EVIDENCE_1",
        "SENTINEL_CONTEXT_EVIDENCE_2",
        "SENTINEL_INTERNAL_DOC_1",
        "SENTINEL_INTERNAL_DOC_2",
        "SENTINEL_INTERNAL_CHUNK_1",
        "SENTINEL_INTERNAL_CHUNK_2",
        "SENTINEL_HISTORICAL_ANSWER_7f0b3f",
        "SENTINEL_HISTORICAL_CITATION_7f0b3f",
        "SENTINEL_HISTORICAL_TARGET_7f0b3f",
        "SENTINEL_JUDGE_7f0b3f",
        "SENTINEL_METADATA_SECRET_7f0b3f",
        "SENTINEL_METADATA_NESTED_7f0b3f",
    ):
        assert sentinel not in serialized
    for forbidden_field in (
        "reference_answer",
        "gold_document_ids",
        "gold_evidence_ids",
        "expected_diagnoses",
        "relevance_grade",
        "usefulness",
        "supports_claim",
        "historical_output",
        "metadata",
        "sample_id",
        "dataset_id",
    ):
        assert forbidden_field not in serialized


def test_a03_two_runs_evaluate_and_persist_their_own_answers_without_mutating_sample(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_answer = "独立脚本回答 Alpha"
    second_answer = "独立脚本回答 Beta"
    provider = _install_recording_transport(
        monkeypatch,
        [
            {
                "status": 200,
                "headers": {},
                "json": {
                    "choices": [
                        {"message": {"content": first_answer}, "finish_reason": "stop"}
                    ]
                },
            },
            {
                "status": 200,
                "headers": {},
                "json": {
                    "choices": [
                        {"message": {"content": second_answer}, "finish_reason": "stop"}
                    ]
                },
            },
        ],
    )
    database_path = tmp_path / "a03.sqlite"
    settings = _settings(
        database_path,
        model_execution_adapter="openai_compatible",
        model_external_calls_enabled=True,
    )
    sample = deepcopy(VALID_V2[1])
    sample["sample_id"] = "two-run-answer-isolation"
    sample["labels"]["reference_answer"] = first_answer
    metric_config = [
        {
            "name": "answer_reference_exact_match",
            "version": "2.0.0",
            "parameters": {},
        }
    ]

    with TestClient(create_app(settings)) as client:
        dataset_id, dataset_hash = _create_dataset(client, [sample])
        before = _sample_storage_state(database_path, sample["sample_id"])
        first_job = _create_job(
            client,
            dataset_id,
            adapter_id="openai_compatible",
            metrics=metric_config,
        )
        second_job = _create_job(
            client,
            dataset_id,
            adapter_id="openai_compatible",
            metrics=metric_config,
        )
        first_sample = _only_sample(client, first_job["id"])
        second_sample = _only_sample(client, second_job["id"])

    after = _sample_storage_state(database_path, sample["sample_id"])
    assert len(provider.requests) == 2
    assert before == after
    assert first_sample["run"]["run_id"] != second_sample["run"]["run_id"]
    assert first_sample["run"]["answer"] == first_answer
    assert second_sample["run"]["answer"] == second_answer
    assert first_sample["answer"] == first_answer
    assert second_sample["answer"] == second_answer
    assert _metric(first_sample, "answer_reference_exact_match")["value"] is True
    assert _metric(second_sample, "answer_reference_exact_match")["value"] is False

    with TestClient(create_app(settings)) as reopened:
        dataset = reopened.get(f"/api/v1/datasets/{dataset_id}")
        first_reloaded = _only_sample(reopened, first_job["id"])
        second_reloaded = _only_sample(reopened, second_job["id"])
        first_report = reopened.get(f"/api/v1/evaluation-jobs/{first_job['id']}/report")
        second_report = reopened.get(f"/api/v1/evaluation-jobs/{second_job['id']}/report")

    assert dataset.status_code == 200
    assert dataset.json()["content_sha256"] == dataset_hash
    assert first_reloaded["run"]["answer"] == first_answer
    assert second_reloaded["run"]["answer"] == second_answer
    assert first_report.status_code == 200
    assert second_report.status_code == 200


ERROR_CASES = [
    ("authentication_401", "PROVIDER_AUTHENTICATION_FAILED", 1),
    ("authorization_403", "PROVIDER_AUTHENTICATION_FAILED", 1),
    ("rate_limited_429", "PROVIDER_RATE_LIMITED", 3),
    ("rate_limited_long_retry_after", "PROVIDER_RATE_LIMITED", 1),
    ("timeout", "PROVIDER_TIMEOUT", 3),
    ("server_error_500", "PROVIDER_SERVER_ERROR", 3),
    ("transport", "PROVIDER_TRANSPORT_ERROR", 3),
    ("invalid_json", "PROVIDER_RESPONSE_INVALID", 1),
    ("empty_body", "PROVIDER_RESPONSE_INVALID", 1),
    ("missing_answer", "PROVIDER_RESPONSE_INVALID", 1),
    ("answer_wrong_type", "PROVIDER_RESPONSE_INVALID", 1),
]


@pytest.mark.parametrize(
    ("case_id", "expected_code", "expected_attempts"),
    ERROR_CASES,
    ids=[case[0] for case in ERROR_CASES],
)
def test_a04_errors_are_bounded_retried_as_specified_and_sanitized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case_id: str,
    expected_code: str,
    expected_attempts: int,
) -> None:
    if case_id in {"timeout", "transport"}:
        script = {"exception": case_id}
    else:
        script = PROVIDER_RESPONSES[case_id]
    provider = _install_recording_transport(
        monkeypatch,
        [script for _ in range(expected_attempts)],
    )
    settings = _settings(
        tmp_path / f"a04-{case_id}.sqlite",
        model_execution_adapter="openai_compatible",
        model_external_calls_enabled=True,
    )
    sample = deepcopy(VALID_V2[2])
    sample["sample_id"] = f"error-{case_id}"

    with TestClient(create_app(settings)) as client:
        dataset_id, _ = _create_dataset(client, [sample])
        started = time.perf_counter()
        job = _create_job(client, dataset_id, adapter_id="openai_compatible")
        elapsed = time.perf_counter() - started
        result = _only_sample(client, job["id"])
        report = client.get(f"/api/v1/evaluation-jobs/{job['id']}/report")

    assert job["status"] == "failed"
    assert result["run"]["status"] == "failed"
    assert result["run"]["answer"] is None
    assert result["run"]["attempt_count"] == expected_attempts
    assert result["run"]["error"]["code"] == expected_code
    assert result["run"]["error"]["attempts"] == expected_attempts
    assert len(result["run"]["attempts"]) == expected_attempts
    assert len(provider.requests) == expected_attempts
    assert elapsed <= 0.7
    for request in provider.requests:
        timeout = request.extensions.get("timeout")
        if isinstance(timeout, dict):
            configured = [value for value in timeout.values() if isinstance(value, (int, float))]
            assert configured
            assert max(configured) <= 0.1
    if case_id == "rate_limited_long_retry_after":
        assert result["run"]["error"]["retry_after_ms"] == 5000
    assert report.status_code == 200
    serialized = json.dumps(
        {"job": job, "sample": result, "report": report.json()},
        ensure_ascii=False,
    )
    assert RAW_PROVIDER_SECRET not in serialized
    assert FAKE_API_KEY not in serialized
    assert "provider.invalid" not in serialized


def test_a05_missing_configuration_still_starts_and_status_does_not_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _install_recording_transport(monkeypatch, [])
    settings = _settings(
        tmp_path / "a05-no-config.sqlite",
        openai_compat_base_url=None,
        openai_compat_api_key=None,
        openai_compat_default_model=None,
    )

    with TestClient(create_app(settings)) as client:
        live = client.get("/health/live")
        ready = client.get("/health/ready")
        status = client.get("/api/v1/model-execution/status")

    assert live.status_code == 200
    assert ready.status_code == 200
    assert status.status_code == 200
    assert status.json()["backend_execution_adapter"] == "mock"
    assert status.json()["providers"][0]["configuration_status"] == "not_configured"
    assert provider.requests == []


def test_a05_disabled_external_calls_do_not_touch_transport_or_fallback_to_mock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _install_recording_transport(
        monkeypatch,
        [PROVIDER_RESPONSES["success_full"]],
    )
    settings = _settings(
        tmp_path / "a05-disabled.sqlite",
        model_execution_adapter="openai_compatible",
        model_external_calls_enabled=False,
    )

    with TestClient(create_app(settings)) as client:
        dataset_id, _ = _create_dataset(client, [VALID_V2[2]])
        ready = client.get("/health/ready")
        status = client.get("/api/v1/model-execution/status")
        create = client.post(
            "/api/v1/evaluation-jobs",
            json=_job_payload(dataset_id, adapter_id="openai_compatible"),
        )
        jobs = client.get("/api/v1/evaluation-jobs")

    assert ready.status_code == 200
    assert status.status_code == 200
    _assert_error(create, 403, "EXTERNAL_CALLS_DISABLED")
    assert jobs.status_code == 200
    assert jobs.json()["total"] == 0
    assert provider.requests == []


def test_a05_unavailable_retrieval_mode_is_explicit_and_does_not_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _install_recording_transport(monkeypatch, [])
    settings = _settings(tmp_path / "a05-retrieval.sqlite")

    with TestClient(create_app(settings)) as client:
        dataset_id, _ = _create_dataset(client, [VALID_V2[2]])
        create = client.post(
            "/api/v1/evaluation-jobs",
            json=_job_payload(
                dataset_id,
                adapter_id="mock",
                context_policy="retrieval",
            ),
        )
        jobs = client.get("/api/v1/evaluation-jobs")

    _assert_error(create, 409, "EXECUTION_MODE_UNAVAILABLE")
    assert jobs.json()["total"] == 0
    assert provider.requests == []


def test_a06_execution_success_configuration_and_mocking_do_not_claim_quality(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _install_recording_transport(monkeypatch, [])
    settings = _settings(
        tmp_path / "a06.sqlite",
        model_execution_adapter="mock",
        model_external_calls_enabled=False,
    )

    with TestClient(create_app(settings)) as client:
        status = client.get("/api/v1/model-execution/status")
        dataset_id, _ = _create_dataset(client, [VALID_V2[1]])
        job = _create_job(client, dataset_id, adapter_id="mock")
        sample = _only_sample(client, job["id"])
        report = client.get(f"/api/v1/evaluation-jobs/{job['id']}/report")

    assert status.status_code == 200
    assert status.json()["backend_execution_adapter"] == "mock"
    assert status.json()["external_calls_enabled"] is False
    assert status.json()["providers"][0]["configuration_status"] == "configured_unverified"
    assert job["status"] == "completed"
    assert job["outcome"] == "succeeded"
    assert job["quality_status"] == "not_evaluated"
    assert job["quality_verdict"] == "unknown"
    assert job["quality_score"] is None
    assert sample["run"]["is_mock"] is True
    assert report.status_code == 200
    assert report.json()["execution_summary"]["success_rate"] == 1.0
    assert report.json()["quality_summary"] == {
        "status": "not_evaluated",
        "verdict": "unknown",
        "score": None,
        "evaluated_sample_count": 0,
    }
    assert provider.requests == []


def test_a07_provided_context_and_unjudged_citation_do_not_create_recall_or_support_score(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _install_recording_transport(monkeypatch, [])
    settings = _settings(tmp_path / "a07-provided.sqlite")
    metrics = [
        {"name": "recall_at_1", "version": "2.0.0", "parameters": {"k": 1}},
        {
            "name": "citation_resolution_rate",
            "version": "2.0.0",
            "parameters": {},
        },
        {"name": "citation_support_rate", "version": "2.0.0", "parameters": {}},
    ]

    with TestClient(create_app(settings)) as client:
        dataset_id, _ = _create_dataset(client, [VALID_V2[1]])
        job = _create_job(client, dataset_id, adapter_id="mock", metrics=metrics)
        sample = _only_sample(client, job["id"])

    assert sample["run"]["contexts"][0]["origin"] == "provided"
    recall = _metric(sample, "recall_at_1")
    resolution = _metric(sample, "citation_resolution_rate")
    support = _metric(sample, "citation_support_rate")
    assert recall["status"] == "not_evaluated"
    assert recall["value"] is None
    assert resolution["status"] == "ok"
    assert resolution["value"] == 1.0
    assert support["status"] == "not_evaluated"
    assert support["value"] is None
    assert sample["run"]["citations"][0]["resolved"] is True
    assert sample["run"]["citations"][0]["supports_claim"] is None
    assert provider.requests == []


def test_a07_legacy_unknown_context_does_not_create_retrieval_recall(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _install_recording_transport(monkeypatch, [])
    settings = _settings(tmp_path / "a07-legacy.sqlite")
    metrics = [
        {"name": "recall_at_1", "version": "2.0.0", "parameters": {"k": 1}}
    ]

    with TestClient(create_app(settings)) as client:
        dataset_id, _ = _create_dataset(
            client,
            LEGACY_V1,
            schema_version="1.0",
        )
        job = _create_job(client, dataset_id, adapter_id="mock", metrics=metrics)
        sample = _only_sample(client, job["id"])

    assert sample["run"]["contexts"][0]["origin"] == "legacy_unknown"
    recall = _metric(sample, "recall_at_1")
    assert recall["status"] == "unknown"
    assert recall["value"] is None
    assert provider.requests == []


def test_a08_v1_and_v2_imports_preserve_versioned_meaning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _install_recording_transport(monkeypatch, [])
    settings = _settings(tmp_path / "a08-versions.sqlite")

    with TestClient(create_app(settings)) as client:
        v2_id, _ = _create_dataset(client, [VALID_V2[0]])
        v1_id, _ = _create_dataset(client, LEGACY_V1, schema_version="1.0")
        v2_samples = client.get(f"/api/v1/datasets/{v2_id}/samples")
        v1_samples = client.get(f"/api/v1/datasets/{v1_id}/samples")

    assert v2_samples.status_code == 200
    assert v1_samples.status_code == 200
    v2 = v2_samples.json()["items"][0]
    v1 = v1_samples.json()["items"][0]
    assert v2["schema_version"] == "2.0"
    assert v2["historical_output"]["answer"] == "SENTINEL_HISTORICAL_ANSWER_7f0b3f"
    assert v2["contexts"][0]["origin"] == "provided"
    assert v1["schema_version"] == "1.0"
    assert v1["historical_output"]["answer"] == "这是导入前保存的历史回答。"
    assert v1["contexts"][0]["origin"] == "legacy_unknown"
    assert provider.requests == []


@pytest.mark.parametrize(
    "case",
    INVALID_V2["cases"],
    ids=[case["case_id"] for case in INVALID_V2["cases"]],
)
def test_a08_invalid_samples_are_rejected_atomically_with_field_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: dict[str, Any],
) -> None:
    provider = _install_recording_transport(monkeypatch, [])
    settings = _settings(tmp_path / f"a08-{case['case_id']}.sqlite")

    with TestClient(create_app(settings)) as client:
        created = client.post(
            "/api/v1/datasets",
            json={
                "name": f"invalid-{case['case_id']}-{uuid4()}",
                "owner": "qa",
                "version": "v2",
                "schema_version": "2.0",
            },
        )
        assert created.status_code == 201, created.text
        dataset_id = created.json()["id"]
        response = client.post(
            f"/api/v1/datasets/{dataset_id}/samples:import",
            json={"samples": [case["input"]]},
        )
        dataset = client.get(f"/api/v1/datasets/{dataset_id}")

    expected = case["expected"]
    error = _assert_error(response, expected["http"], expected["code"])
    errors = error["details"]["errors"]
    assert any(item["field"].endswith(expected["field"]) for item in errors), errors
    assert dataset.json()["sample_count"] == 0
    assert provider.requests == []


def test_a08_batch_and_database_duplicate_ids_are_atomic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _install_recording_transport(monkeypatch, [])
    settings = _settings(tmp_path / "a08-duplicates.sqlite")
    duplicate = deepcopy(VALID_V2[2])
    duplicate["sample_id"] = INVALID_V2["batch_duplicate"]["sample_id"]

    with TestClient(create_app(settings)) as client:
        created = client.post(
            "/api/v1/datasets",
            json={
                "name": f"duplicates-{uuid4()}",
                "owner": "qa",
                "version": "v2",
                "schema_version": "2.0",
            },
        )
        dataset_id = created.json()["id"]
        batch = client.post(
            f"/api/v1/datasets/{dataset_id}/samples:import",
            json={"samples": [duplicate, duplicate]},
        )
        after_batch = client.get(f"/api/v1/datasets/{dataset_id}")
        accepted = client.post(
            f"/api/v1/datasets/{dataset_id}/samples:import",
            json={"samples": [VALID_V2[0]]},
        )
        database_duplicate = client.post(
            f"/api/v1/datasets/{dataset_id}/samples:import",
            json={"samples": [VALID_V2[0]]},
        )
        after_database = client.get(f"/api/v1/datasets/{dataset_id}")

    _assert_error(batch, 422, "VALIDATION_ERROR")
    assert after_batch.json()["sample_count"] == 0
    assert accepted.status_code == 201
    error = _assert_error(database_duplicate, 409, "DUPLICATE_SAMPLE_ID")
    assert any(
        item["field"].endswith("sample_id")
        for item in error["details"]["errors"]
    )
    assert after_database.json()["sample_count"] == 1
    assert provider.requests == []


def test_a08_legacy_database_upgrades_twice_and_keeps_samples_reports_and_reviews(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _install_recording_transport(monkeypatch, [])
    database_path = tmp_path / "a08-legacy.sqlite"
    with sqlite3.connect(database_path) as connection:
        connection.executescript((FIXTURE_ROOT / "legacy-v1.sql").read_text(encoding="utf-8"))
    settings = _settings(database_path)

    observed: list[dict[str, Any]] = []
    for _ in range(2):
        with TestClient(create_app(settings)) as client:
            dataset = client.get("/api/v1/datasets/legacy-dataset-001")
            job = client.get("/api/v1/evaluation-jobs/legacy-job-001")
            samples = client.get("/api/v1/evaluation-jobs/legacy-job-001/samples")
            report = client.get("/api/v1/evaluation-jobs/legacy-job-001/report")
            observed.append(
                {
                    "dataset": dataset.json(),
                    "job": job.json(),
                    "samples": samples.json(),
                    "report": report.json(),
                }
            )

    assert observed[0] == observed[1]
    assert observed[0]["dataset"]["content_sha256"] == "a" * 64
    assert observed[0]["job"]["execution_snapshot"] is None
    assert observed[0]["job"]["quality_status"] == "legacy_unknown"
    assert observed[0]["job"]["quality_verdict"] == "unknown"
    sample = observed[0]["samples"]["items"][0]
    assert sample["review_status"] == "confirmed"
    assert sample["historical_answer"] == "旧历史回答"
    assert sample["run"]["actual_model"] is None
    assert sample["run"]["is_mock"] is None
    assert observed[0]["report"]["schema_version"] == "1.0"
    assert observed[0]["report"]["quality_summary"]["status"] == "legacy_unknown"
    assert provider.requests == []
