from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPO_ROOT / "examples" / "eval-samples"

SUPPORTED_DIAGNOSIS_ORACLE = {
    "retrieval_missing": "retrieval.missing_evidence",
    "context_pollution": "context.pollution",
    "citation_missing": "citation.missing",
}
KNOWN_UNSUPPORTED_DIAGNOSES = {"model_hallucination", "rerank_ineffective"}

VALIDATION_ORACLE = {
    "SAMPLE_ID_REQUIRED": {
        "field_suffix": "samples.0.sample_id",
        "error_type": "string_too_short",
    },
    "QUESTION_REQUIRED": {
        "field_suffix": "samples.0.question",
        "error_type": "value_error",
    },
    "DUPLICATE_SAMPLE_ID": {"message": "sample_id must be unique within a batch"},
    "RANK_OUT_OF_RANGE": {
        "field_suffix": "samples.0.retrieved_contexts.0.rank",
        "error_type": "greater_than_equal",
    },
    "DUPLICATE_RANK": {"message": "retrieved context ranks must be unique"},
    "CITATION_TARGET_NOT_FOUND": {
        "message": "citation targets are missing from retrieved contexts"
    },
    "FIELD_TYPE_INVALID": {
        "field_suffix": "samples.0.gold_document_ids",
        "error_type": "list_type",
    },
    "SCHEMA_VERSION_UNSUPPORTED": {
        "field_suffix": "samples.0.schema_version",
        "error_type": "literal_error",
    },
}


def _load_jsonl(name: str) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in (FIXTURE_ROOT / name).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


VALID_SAMPLES = _load_jsonl("valid-samples.jsonl")
INVALID_CASES = _load_jsonl("invalid-samples.jsonl")
SINGLE_INVALID_CASES = [case for case in INVALID_CASES if "batch_id" not in case]


def _create_dataset(client, name: str) -> str:
    response = client.post(
        "/api/v1/datasets",
        json={
            "name": name,
            "description": "Synthetic QA acceptance fixture.",
            "owner": "backend-tests",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def _assert_validation_oracle(response, expected_error: str) -> None:
    assert response.status_code == 422
    payload = response.json()["error"]
    assert payload["code"] == (
        "UNSUPPORTED_SCHEMA_VERSION"
        if expected_error == "SCHEMA_VERSION_UNSUPPORTED"
        else "VALIDATION_ERROR"
    )
    assert payload["request_id"].startswith("req_")

    expected = VALIDATION_ORACLE[expected_error]
    errors = payload["details"]["errors"]
    assert any(
        ("field_suffix" not in expected or error["field"].endswith(expected["field_suffix"]))
        and ("error_type" not in expected or error["type"] == expected["error_type"])
        and ("message" not in expected or expected["message"] in error["message"])
        for error in errors
    ), {"oracle": expected_error, "expected": expected, "actual": errors}


def _metric(items: list[dict[str, Any]], name: str) -> dict[str, Any]:
    return next(item for item in items if item["metric_name"] == name)


def test_sanitized_fixtures_complete_the_real_api_evaluation_loop(client) -> None:
    live = client.get("/health/live")
    ready = client.get("/health/ready")
    openapi = client.get("/openapi.json")

    assert live.status_code == 200
    assert live.json() == {"status": "ok"}
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready"}
    assert {
        "/api/v1/datasets",
        "/api/v1/datasets/{dataset_id}/samples:import",
        "/api/v1/evaluation-jobs",
        "/api/v1/evaluation-jobs/{job_id}/report",
    } <= set(openapi.json()["paths"])

    dataset_id = _create_dataset(client, "mvp-acceptance-fixtures")
    imported = client.post(
        f"/api/v1/datasets/{dataset_id}/samples:import",
        json={"samples": VALID_SAMPLES},
    )
    published = client.post(f"/api/v1/datasets/{dataset_id}:publish")

    assert imported.status_code == 201
    assert imported.json()["accepted"] == len(VALID_SAMPLES) == 6
    assert imported.json()["rejected"] == 0
    assert published.status_code == 200
    assert published.json()["status"] == "published"
    assert published.json()["sample_count"] == 6
    assert len(published.json()["content_sha256"]) == 64

    created = client.post(
        "/api/v1/evaluation-jobs",
        headers={"Idempotency-Key": "mvp-fixture-acceptance-v1"},
        json={
            "dataset_id": dataset_id,
            "config_version": "qa-mvp-v1",
            "metrics": [
                {"name": "recall_at_3", "version": "1.0.0", "parameters": {"k": 3}},
                {"name": "mrr_at_3", "version": "1.0.0", "parameters": {"k": 3}},
                {"name": "ndcg_at_3", "version": "1.0.0", "parameters": {"k": 3}},
            ],
        },
    )

    assert created.status_code == 202
    assert created.json()["status"] == "queued"
    job_id = created.json()["id"]

    job = client.get(f"/api/v1/evaluation-jobs/{job_id}")
    sample_results = client.get(f"/api/v1/evaluation-jobs/{job_id}/samples")
    report = client.get(f"/api/v1/evaluation-jobs/{job_id}/report")

    assert job.status_code == 200
    assert job.json()["status"] == "completed"
    assert job.json()["outcome"] == "succeeded"
    assert job.json()["progress"] == 1.0
    assert job.json()["queued_count"] == 0
    assert job.json()["running_count"] == 0
    assert job.json()["succeeded_count"] == 6
    assert job.json()["failed_count"] == 0
    assert job.json()["started_at"] is not None
    assert job.json()["finished_at"] is not None

    assert sample_results.status_code == 200
    assert sample_results.json()["total"] == 6
    by_sample_id = {item["sample_id"]: item for item in sample_results.json()["items"]}
    assert set(by_sample_id) == {sample["sample_id"] for sample in VALID_SAMPLES}
    assert all(item["status"] == "succeeded" for item in by_sample_id.values())

    fixture_labels = {
        label for sample in VALID_SAMPLES for label in sample.get("expected_diagnoses", [])
    }
    assert fixture_labels - set(SUPPORTED_DIAGNOSIS_ORACLE) == KNOWN_UNSUPPORTED_DIAGNOSES
    for fixture in VALID_SAMPLES:
        current = by_sample_id[fixture["sample_id"]]
        # Version 1 fixtures have unknown retrieval provenance, even through the
        # legacy job-creation API. Historical labels are not this run's output.
        assert _metric(current["metric_results"], "recall_at_3")["value"] is None
        assert current["answer"].startswith("[mock]")
        assert current["run"]["answer"] == current["answer"]
        assert current["reference_answer"] == fixture.get("reference_answer")
        assert current["quality_status"] != "evaluated"

    assert report.status_code == 200
    assert report.json()["status"] == "completed"
    assert report.json()["outcome"] == "succeeded"
    assert report.json()["summary"] == {
        "total_count": 6,
        "succeeded_count": 6,
        "failed_count": 0,
    }
    execution_rate = _metric(report.json()["metrics"], "execution_success_rate")
    recall_at_3 = _metric(report.json()["metrics"], "recall_at_3")
    assert execution_rate["value"] == 1.0
    assert recall_at_3["value"] is None
    assert recall_at_3["evaluated_count"] == 0
    assert recall_at_3["excluded_count"] == 6


@pytest.mark.parametrize(
    "case",
    SINGLE_INVALID_CASES,
    ids=[case["case_id"] for case in SINGLE_INVALID_CASES],
)
def test_invalid_fixture_is_rejected_atomically_by_import_api(client, case) -> None:
    dataset_id = _create_dataset(client, f"qa-{case['case_id']}")
    response = client.post(
        f"/api/v1/datasets/{dataset_id}/samples:import",
        json={"samples": [case["input"]]},
    )

    _assert_validation_oracle(response, case["expected_error"])
    dataset = client.get(f"/api/v1/datasets/{dataset_id}")
    assert dataset.json()["sample_count"] == 0


def test_duplicate_id_fixture_batch_is_rejected_atomically(client) -> None:
    duplicate_cases = [
        case for case in INVALID_CASES if case.get("batch_id") == "duplicate-id-batch"
    ]
    assert len(duplicate_cases) == 2
    assert {case["expected_error"] for case in duplicate_cases} == {"DUPLICATE_SAMPLE_ID"}

    dataset_id = _create_dataset(client, "qa-duplicate-id-batch")
    response = client.post(
        f"/api/v1/datasets/{dataset_id}/samples:import",
        json={"samples": [case["input"] for case in duplicate_cases]},
    )

    _assert_validation_oracle(response, "DUPLICATE_SAMPLE_ID")
    dataset = client.get(f"/api/v1/datasets/{dataset_id}")
    assert dataset.json()["sample_count"] == 0
