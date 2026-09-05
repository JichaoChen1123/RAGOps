from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.execution.adapters import (
    MockModelAdapter,
    OpenAICompatibleAdapter,
    OpenAICompatibleConfig,
)
from app.execution.model import ModelResponse, ModelTransportRequest, ModelTransportResponse
from app.main import create_app
from app.schemas.jobs import EvaluationJobCreate
from app.services import jobs as job_service
from conftest import create_published_dataset


def _v2_sample() -> dict[str, object]:
    return {
        "schema_version": "2.0",
        "sample_id": "sample-v2-001",
        "question": "How do I reset the demo password?",
        "labels": {
            "reference_answer": "REFERENCE-LABEL-SENTINEL",
            "gold_document_ids": ["GOLD-DOCUMENT-SENTINEL"],
            "gold_evidence_ids": ["GOLD-EVIDENCE-SENTINEL"],
            "expected_diagnoses": [],
        },
        "contexts": [
            {
                "origin": "provided",
                "rank": 1,
                "rank_before": None,
                "retrieval_run_id": None,
                "doc_id": "PRIVATE-DOC-ID-SENTINEL",
                "chunk_id": "chunk-safe",
                "evidence_ids": ["PRIVATE-EVIDENCE-SENTINEL"],
                "text": "Use the settings page. [chunk-safe]",
                "score": None,
                "relevance_grade": 3,
                "usefulness": True,
            }
        ],
        "historical_output": {
            "answer": "HISTORICAL-ANSWER-SENTINEL",
            "citations": [],
            "recorded_at": "2026-09-05T08:00:00Z",
        },
        "tags": ["synthetic"],
        "metadata": {"private": "METADATA-SENTINEL"},
    }


def _v2_job(dataset_id: str, *, adapter_id: str = "mock") -> dict[str, object]:
    return {
        "schema_version": "2.0",
        "dataset_id": dataset_id,
        "name": "offline v2 run",
        "execution": {
            "adapter_id": adapter_id,
            "prompt": {"version": "support-rag-v2", "text": "Use only the given context."},
            "generation": {
                "model": "mock-ragops-v1" if adapter_id == "mock" else "test-model",
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


def test_v2_mock_run_separates_labels_history_execution_and_quality(client) -> None:
    dataset = client.post(
        "/api/v1/datasets",
        json={
            "name": "v2-offline-contract",
            "owner": "backend-tests",
            "version": "v2",
            "schema_version": "2.0",
            "samples": [_v2_sample()],
        },
    )
    assert dataset.status_code == 201, dataset.text
    dataset_id = dataset.json()["id"]
    published = client.post(f"/api/v1/datasets/{dataset_id}:publish")
    original_hash = published.json()["content_sha256"]

    created = client.post("/api/v1/evaluation-jobs", json=_v2_job(dataset_id))
    assert created.status_code == 202, created.text
    assert created.json()["schema_version"] == "2.0"
    assert created.json()["execution_snapshot"]["adapter_id"] == "mock"
    assert len(created.json()["execution_snapshot"]["config_version"]) == 64
    serialized_snapshot = json.dumps(created.json()["execution_snapshot"])
    assert "REFERENCE-LABEL-SENTINEL" not in serialized_snapshot
    assert "METADATA-SENTINEL" not in serialized_snapshot

    job_id = created.json()["id"]
    job = client.get(f"/api/v1/evaluation-jobs/{job_id}").json()
    sample = client.get(f"/api/v1/evaluation-jobs/{job_id}/samples").json()["items"][0]
    report = client.get(f"/api/v1/evaluation-jobs/{job_id}/report").json()
    dataset_after = client.get(f"/api/v1/datasets/{dataset_id}").json()

    assert job["status"] == "completed"
    assert job["outcome"] == "succeeded"
    assert job["quality_status"] == "not_evaluated"
    assert job["quality_verdict"] == "unknown"
    assert job["quality_score"] is None
    assert sample["labels"]["reference_answer"] == "REFERENCE-LABEL-SENTINEL"
    assert sample["historical_answer"] == "HISTORICAL-ANSWER-SENTINEL"
    assert sample["answer"] == "[mock] Use the settings page. [chunk-safe]"
    assert sample["run"]["answer"] == sample["answer"]
    assert sample["run"]["actual_model"] == "mock-ragops-v1"
    assert sample["run"]["is_mock"] is True
    assert sample["run"]["usage"] is None
    assert sample["run"]["cost"] is None
    assert sample["run"]["attempt_count"] == 1
    metrics = {item["metric_name"]: item for item in sample["metric_results"]}
    assert metrics["recall_at_1"]["status"] == "not_evaluated"
    assert metrics["recall_at_1"]["value"] is None
    assert metrics["citation_resolution_rate"]["value"] == 1.0
    assert metrics["citation_support_rate"]["status"] == "not_evaluated"
    assert metrics["citation_support_rate"]["value"] is None
    assert report["execution_summary"]["success_rate"] == 1.0
    assert report["quality_summary"] == {
        "status": "not_evaluated",
        "verdict": "unknown",
        "score": None,
        "evaluated_sample_count": 0,
    }
    assert dataset_after["content_sha256"] == original_hash


def test_execution_status_is_local_and_secret_free() -> None:
    settings = Settings(
        environment="test",
        database_url="sqlite://",
        auto_create_schema=True,
        model_execution_adapter="mock",
        model_external_calls_enabled=False,
        openai_compat_base_url="https://user-name.example.invalid/secret-path",
        openai_compat_auth_mode="bearer",
        openai_compat_api_key="VERY-SECRET-KEY",
        openai_compat_default_model="configured-model",
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/model-execution/status")

    assert response.status_code == 200
    body = response.json()
    assert body["backend_execution_adapter"] == "mock"
    assert body["external_calls_enabled"] is False
    assert body["execution_available"] is True
    assert body["providers"][0]["configuration_status"] == "configured_unverified"
    assert body["providers"][0]["credential_configured"] is True
    serialized = response.text
    assert "VERY-SECRET-KEY" not in serialized
    assert "user-name" not in serialized
    assert "secret-path" not in serialized
    assert "configured-model" not in serialized


def test_explicit_quality_gate_is_the_only_source_of_verdict_and_score(client) -> None:
    created_dataset = client.post(
        "/api/v1/datasets",
        json={
            "name": "quality-gate-v2",
            "owner": "backend-tests",
            "version": "v2",
            "schema_version": "2.0",
            "samples": [_v2_sample()],
        },
    )
    dataset_id = created_dataset.json()["id"]
    client.post(f"/api/v1/datasets/{dataset_id}:publish")
    payload = _v2_job(dataset_id)
    payload["quality_gate"] = {
        "version": "quality-v1",
        "rules": [
            {"metric_name": "context_precision", "operator": "gte", "threshold": 0.9}
        ],
        "score_metric": "context_precision",
    }

    job_id = client.post("/api/v1/evaluation-jobs", json=payload).json()["id"]
    job = client.get(f"/api/v1/evaluation-jobs/{job_id}").json()
    sample = client.get(f"/api/v1/evaluation-jobs/{job_id}/samples").json()["items"][0]

    assert job["outcome"] == "succeeded"
    assert job["quality_status"] == "evaluated"
    assert job["quality_verdict"] == "passed"
    assert job["quality_score"] == 100.0
    assert sample["quality_status"] == "evaluated"


def test_unavailable_execution_modes_are_rejected_without_creating_a_job(
    client,
    sample_payload,
) -> None:
    dataset_id = create_published_dataset(client, [sample_payload])

    unknown = client.post("/api/v1/evaluation-jobs", json=_v2_job(dataset_id, adapter_id="codex"))
    openai = client.post(
        "/api/v1/evaluation-jobs",
        json=_v2_job(dataset_id, adapter_id="openai_compatible"),
    )
    retrieval_payload = _v2_job(dataset_id)
    retrieval_payload["execution"]["context_policy"] = "retrieval"
    retrieval = client.post("/api/v1/evaluation-jobs", json=retrieval_payload)

    assert unknown.status_code == 422
    assert unknown.json()["error"]["code"] == "EXECUTION_ADAPTER_NOT_FOUND"
    assert openai.status_code == 409
    assert openai.json()["error"]["code"] == "PROVIDER_NOT_CONFIGURED"
    assert retrieval.status_code == 409
    assert retrieval.json()["error"]["code"] == "EXECUTION_MODE_UNAVAILABLE"
    assert client.get("/api/v1/evaluation-jobs").json()["total"] == 0


class OneShotAuthenticationFailureTransport:
    def __init__(self) -> None:
        self.calls = 0

    def send(self, request: ModelTransportRequest) -> ModelTransportResponse:
        self.calls += 1
        return ModelTransportResponse(
            status_code=401,
            headers={},
            body=b'{"private":"RAW-ERROR-BODY"}',
        )


class InjectedFactory:
    def __init__(self, settings: Settings, transport: OneShotAuthenticationFailureTransport):
        self.settings = settings
        self.transport = transport

    def create(self, adapter_id: str, server_config=None, *, test_transport=None):
        assert adapter_id == "openai_compatible"
        return OpenAICompatibleAdapter(
            OpenAICompatibleConfig(
                base_url="https://provider.invalid/v1",
                auth_mode="bearer",
                api_key="FAKE-KEY",
                default_model="test-model",
            ),
            self.settings,
            transport=self.transport,
            transport_is_mock=True,
        )


def test_all_failed_job_still_has_a_safe_queryable_report(client, sample_payload) -> None:
    dataset_id = create_published_dataset(client, [sample_payload])
    settings = Settings(
        environment="test",
        database_url="sqlite://",
        model_external_calls_enabled=True,
        openai_compat_base_url="https://provider.invalid/v1",
        openai_compat_auth_mode="bearer",
        openai_compat_api_key="FAKE-KEY",
        openai_compat_default_model="test-model",
    )
    database = client.app.state.database
    payload = EvaluationJobCreate.model_validate(_v2_job(dataset_id, adapter_id="openai_compatible"))
    with database.session() as session:
        job, created = job_service.create_job(
            session,
            payload,
            idempotency_key=None,
            settings=settings,
        )
        job_id = job.id
        assert created is True

    transport = OneShotAuthenticationFailureTransport()
    job_service.execute_job(
        database,
        job_id,
        settings,
        adapter_factory=InjectedFactory(settings, transport),
    )

    job = client.get(f"/api/v1/evaluation-jobs/{job_id}").json()
    sample = client.get(f"/api/v1/evaluation-jobs/{job_id}/samples").json()["items"][0]
    report = client.get(f"/api/v1/evaluation-jobs/{job_id}/report")
    assert transport.calls == 1
    assert job["status"] == "failed"
    assert job["outcome"] == "failed"
    assert sample["run"]["status"] == "failed"
    assert sample["run"]["attempt_count"] == 1
    assert sample["run"]["error"]["code"] == "PROVIDER_AUTHENTICATION_FAILED"
    assert "RAW-ERROR-BODY" not in json.dumps(sample)
    assert "FAKE-KEY" not in json.dumps(sample)
    assert report.status_code == 200
    assert report.json()["execution_summary"]["failed_count"] == 1
    assert report.json()["quality_summary"]["score"] is None


class FixedAnswerAdapter(MockModelAdapter):
    def __init__(self, answer: str) -> None:
        super().__init__()
        self.answer = answer

    def generate(self, request) -> ModelResponse:
        response = super().generate(request)
        return response.model_copy(update={"answer": self.answer})


class FixedAnswerFactory:
    def __init__(self, answer: str) -> None:
        self.answer = answer

    def create(self, adapter_id: str, server_config=None, *, test_transport=None):
        assert adapter_id == "mock"
        return FixedAnswerAdapter(self.answer)


def test_two_runs_keep_independent_answers_and_survive_database_reopen(tmp_path) -> None:
    database_path = tmp_path / "persistent-runs.db"
    settings = Settings(
        environment="test",
        database_url=f"sqlite:///{database_path.as_posix()}",
        log_level="WARNING",
        auto_create_schema=True,
    )
    job_ids: list[str] = []
    with TestClient(create_app(settings)) as client:
        created_dataset = client.post(
            "/api/v1/datasets",
            json={
                "name": "persistent-v2-runs",
                "owner": "backend-tests",
                "version": "v2",
                "schema_version": "2.0",
                "samples": [_v2_sample()],
            },
        )
        dataset_id = created_dataset.json()["id"]
        published = client.post(f"/api/v1/datasets/{dataset_id}:publish").json()
        original_hash = published["content_sha256"]
        database = client.app.state.database
        for index, answer in enumerate(("first run answer", "second run answer"), start=1):
            payload_dict = _v2_job(dataset_id)
            payload_dict["name"] = f"run {index}"
            payload = EvaluationJobCreate.model_validate(payload_dict)
            with database.session() as session:
                job, _ = job_service.create_job(
                    session,
                    payload,
                    idempotency_key=None,
                    settings=settings,
                )
                job_ids.append(job.id)
            job_service.execute_job(
                database,
                job.id,
                settings,
                adapter_factory=FixedAnswerFactory(answer),
            )
        assert client.get(f"/api/v1/datasets/{dataset_id}").json()["content_sha256"] == original_hash

    with TestClient(create_app(settings)) as reopened:
        persisted = [
            reopened.get(f"/api/v1/evaluation-jobs/{job_id}/samples").json()["items"][0]
            for job_id in job_ids
        ]
        source_sample = reopened.get(f"/api/v1/datasets/{dataset_id}/samples").json()["items"][0]

    assert [item["answer"] for item in persisted] == ["first run answer", "second run answer"]
    assert persisted[0]["run"]["run_id"] != persisted[1]["run"]["run_id"]
    assert source_sample["historical_output"]["answer"] == "HISTORICAL-ANSWER-SENTINEL"
    assert source_sample["historical_output"]["answer"] not in {
        item["answer"] for item in persisted
    }
