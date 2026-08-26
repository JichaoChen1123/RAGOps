from conftest import create_published_dataset


def test_complete_persisted_evaluation_loop(client, sample_payload) -> None:
    second = {
        **sample_payload,
        "sample_id": "support-policy-002",
        "question": "无法回答的问题会怎样？",
        "reference_answer": None,
        "answer": None,
        "retrieved_contexts": [],
        "citations": [],
    }
    dataset_id = create_published_dataset(client, [sample_payload, second])

    created = client.post(
        "/api/v1/evaluation-jobs",
        headers={"Idempotency-Key": "evaluation-demo-1"},
        json={
            "dataset_id": dataset_id,
            "config_version": "rag-config-demo-v1",
            "metrics": [],
        },
    )

    assert created.status_code == 202
    assert created.json()["status"] == "queued"
    job_id = created.json()["id"]

    status_response = client.get(f"/api/v1/evaluation-jobs/{job_id}")
    sample_results = client.get(f"/api/v1/evaluation-jobs/{job_id}/samples")
    report = client.get(f"/api/v1/evaluation-jobs/{job_id}/report")

    assert status_response.json()["status"] == "succeeded"
    assert status_response.json()["progress"] == 1.0
    assert status_response.json()["succeeded_count"] == 2
    assert sample_results.json()["total"] == 2
    assert {item["status"] for item in sample_results.json()["items"]} == {"succeeded"}
    assert sample_results.json()["items"][0]["retrieval_results"][0]["doc_id"] == "policy-audit"
    assert report.status_code == 200
    assert report.json()["summary"] == {
        "total_count": 2,
        "succeeded_count": 2,
        "failed_count": 0,
    }
    assert report.json()["metrics"][0]["metric_name"] == "execution_success_rate"
    assert report.json()["metrics"][0]["value"] == 1.0
    assert "placeholder" in report.json()["metrics"][0]["details"]["note"].lower()


def test_job_idempotency_and_conflict(client, sample_payload) -> None:
    dataset_id = create_published_dataset(client, [sample_payload])
    headers = {"Idempotency-Key": "same-job"}
    payload = {"dataset_id": dataset_id, "config_version": "config-v1"}

    first = client.post("/api/v1/evaluation-jobs", headers=headers, json=payload)
    replay = client.post("/api/v1/evaluation-jobs", headers=headers, json=payload)
    conflict = client.post(
        "/api/v1/evaluation-jobs",
        headers=headers,
        json={**payload, "config_version": "config-v2"},
    )

    assert replay.status_code == 202
    assert replay.json()["id"] == first.json()["id"]
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"


def test_draft_dataset_and_unknown_job_errors(client, sample_payload) -> None:
    draft = client.post("/api/v1/datasets", json={"name": "draft"})
    imported = client.post(
        f"/api/v1/datasets/{draft.json()['id']}/samples:import",
        json={"samples": [sample_payload]},
    )
    assert imported.status_code == 201

    job = client.post(
        "/api/v1/evaluation-jobs",
        json={"dataset_id": draft.json()["id"], "config_version": "config-v1"},
    )
    missing = client.get("/api/v1/evaluation-jobs/00000000-0000-0000-0000-000000000000")

    assert job.status_code == 409
    assert job.json()["error"]["code"] == "DATASET_VERSION_NOT_PUBLISHED"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
