from fastapi.testclient import TestClient


def test_create_dataset_with_inline_samples(client, sample_payload) -> None:
    response = client.post(
        "/api/v1/datasets",
        json={
            "name": "support-regression",
            "description": "MVP regression samples",
            "owner": "quality-platform",
            "version": "2026.08",
            "samples": [sample_payload],
        },
    )

    assert response.status_code == 201
    assert response.json()["owner"] == "quality-platform"
    assert response.json()["version"] == "2026.08"
    assert response.json()["sample_count"] == 1
    assert response.json()["imported_samples"] == 1


def test_dataset_owner_and_version_reject_blank_values(client) -> None:
    response = client.post(
        "/api/v1/datasets",
        json={"name": "invalid-owner", "owner": " ", "version": " "},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    fields = {item["field"] for item in response.json()["error"]["details"]["errors"]}
    assert fields == {"owner", "version"}


def test_job_review_and_report_export_contract(client, sample_payload) -> None:
    dataset = client.post(
        "/api/v1/datasets",
        json={
            "name": "export-source",
            "owner": "quality-platform",
            "samples": [sample_payload],
        },
    )
    dataset_id = dataset.json()["id"]
    published = client.post(f"/api/v1/datasets/{dataset_id}:publish")
    assert published.status_code == 200

    created = client.post(
        "/api/v1/evaluation-jobs",
        json={
            "dataset_id": dataset_id,
            "name": "Support regression v1",
            "model_version": "deterministic-local-v1",
            "prompt_version": "support-prompt-v2",
        },
    )

    assert created.status_code == 202
    assert created.json()["status"] == "queued"
    assert created.json()["name"] == "Support regression v1"
    assert created.json()["config_version"] == "deterministic-local-v1:support-prompt-v2"
    job_id = created.json()["id"]

    completed = client.get(f"/api/v1/evaluation-jobs/{job_id}")
    assert completed.json()["status"] == "completed"
    assert completed.json()["outcome"] == "succeeded"

    reviewed = client.patch(
        f"/api/v1/evaluation-jobs/{job_id}/samples/{sample_payload['sample_id']}/review",
        json={"review_status": "confirmed"},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["review_status"] == "confirmed"
    assert reviewed.json()["reviewed_at"] is not None

    exported = client.get(f"/api/v1/evaluation-jobs/{job_id}/report/export")
    assert exported.status_code == 200
    assert exported.json()["schema_version"] == "1.0"
    assert exported.json()["report"]["status"] == "completed"
    assert exported.json()["report"]["outcome"] == "succeeded"
    assert exported.json()["samples"][0]["review_status"] == "confirmed"


def test_review_validation_and_missing_sample_errors(client, sample_payload) -> None:
    dataset = client.post(
        "/api/v1/datasets",
        json={"name": "review-errors", "owner": "quality-platform", "samples": [sample_payload]},
    )
    dataset_id = dataset.json()["id"]
    client.post(f"/api/v1/datasets/{dataset_id}:publish")
    job = client.post(
        "/api/v1/evaluation-jobs",
        json={"dataset_id": dataset_id, "config_version": "review-errors-v1"},
    )
    job_id = job.json()["id"]

    invalid = client.patch(
        f"/api/v1/evaluation-jobs/{job_id}/samples/{sample_payload['sample_id']}/review",
        json={"review_status": "approved"},
    )
    missing = client.patch(
        f"/api/v1/evaluation-jobs/{job_id}/samples/missing/review",
        json={"review_status": "dismissed"},
    )

    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_review_state_round_trip_is_consistent_in_list_and_export(client, sample_payload) -> None:
    dataset = client.post(
        "/api/v1/datasets",
        json={"name": "review-round-trip", "owner": "quality-platform", "samples": [sample_payload]},
    )
    dataset_id = dataset.json()["id"]
    client.post(f"/api/v1/datasets/{dataset_id}:publish")
    job = client.post(
        "/api/v1/evaluation-jobs",
        json={"dataset_id": dataset_id, "config_version": "review-round-trip-v1"},
    )
    job_id = job.json()["id"]
    sample_id = sample_payload["sample_id"]

    initial = client.get(f"/api/v1/evaluation-jobs/{job_id}/samples").json()["items"][0]
    assert initial["review_status"] == "pending"
    assert initial["reviewed_at"] is None

    dismissed = client.patch(
        f"/api/v1/evaluation-jobs/{job_id}/samples/{sample_id}/review",
        json={"review_status": "dismissed"},
    )
    assert dismissed.status_code == 200
    assert dismissed.json()["reviewed_at"] is not None
    dismissed_export = client.get(f"/api/v1/evaluation-jobs/{job_id}/report/export").json()
    assert dismissed_export["samples"][0]["review_status"] == "dismissed"

    reset = client.patch(
        f"/api/v1/evaluation-jobs/{job_id}/samples/{sample_id}/review",
        json={"review_status": "pending"},
    )
    assert reset.status_code == 200
    assert reset.json()["reviewed_at"] is None
    listed = client.get(f"/api/v1/evaluation-jobs/{job_id}/samples").json()["items"][0]
    reset_export = client.get(f"/api/v1/evaluation-jobs/{job_id}/report/export").json()
    assert listed["review_status"] == "pending"
    assert listed["reviewed_at"] is None
    assert reset_export["samples"][0]["review_status"] == "pending"


def test_openapi_exposes_mvp_write_contracts(client) -> None:
    document = client.get("/openapi.json").json()

    assert "/api/v1/datasets" in document["paths"]
    assert "post" in document["paths"]["/api/v1/datasets"]
    assert "/api/v1/evaluation-jobs" in document["paths"]
    assert "post" in document["paths"]["/api/v1/evaluation-jobs"]
    assert "/api/v1/evaluation-jobs/{job_id}/report/export" in document["paths"]
    review_path = "/api/v1/evaluation-jobs/{job_id}/samples/{sample_id}/review"
    assert "patch" in document["paths"][review_path]

    dataset_required = document["components"]["schemas"]["DatasetCreate"]["required"]
    assert {"name", "owner"}.issubset(dataset_required)
    assert document["components"]["schemas"]["ReviewStatus"]["enum"] == [
        "pending",
        "confirmed",
        "dismissed",
    ]


def test_unexpected_error_has_readable_envelope(client) -> None:
    @client.app.get("/test-only/unexpected-error")
    def unexpected_error() -> None:
        raise RuntimeError("sensitive implementation detail")

    with TestClient(client.app, raise_server_exceptions=False) as error_client:
        response = error_client.get("/test-only/unexpected-error")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert response.json()["error"]["message"] == "The server could not complete the request."
    assert response.json()["error"]["request_id"].startswith("req_")
    assert "sensitive" not in response.text
