from conftest import create_published_dataset


def test_dataset_empty_state_and_validation_error(client) -> None:
    empty = client.get("/api/v1/datasets")
    invalid = client.post("/api/v1/datasets", json={"name": "   "})

    assert empty.status_code == 200
    assert empty.json() == {"items": [], "total": 0, "next_cursor": None}
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"
    assert invalid.json()["error"]["request_id"].startswith("req_")


def test_import_publish_and_read_utf8_sample(client, sample_payload) -> None:
    dataset_id = create_published_dataset(client, [sample_payload])

    dataset = client.get(f"/api/v1/datasets/{dataset_id}")
    samples = client.get(f"/api/v1/datasets/{dataset_id}/samples")

    assert dataset.json()["status"] == "published"
    assert dataset.json()["sample_count"] == 1
    assert len(dataset.json()["content_sha256"]) == 64
    assert samples.json()["items"][0]["question"] == sample_payload["question"]
    assert samples.json()["items"][0]["metadata"] == {"source": "synthetic"}


def test_v2_import_round_trip_preserves_context_metadata_and_reference_compatibility(client) -> None:
    payload = {
        "schema_version": "2.0",
        "sample_id": "cmrc-v2-1",
        "question": "中文问题",
        "labels": {
            "reference_answer": "主参考答案",
            "reference_answers": ["候选一", "候选二"],
            "gold_document_ids": ["doc-cmrc"],
            "gold_evidence_ids": ["evidence-cmrc"],
            "expected_diagnoses": [],
        },
        "contexts": [{
            "origin": "provided", "rank": 1, "retrieval_run_id": None,
            "doc_id": "doc-cmrc", "chunk_id": "chunk-cmrc",
            "evidence_ids": ["evidence-cmrc"], "text": "中文上下文", "score": None,
        }],
        "metadata": {"source": {"dataset": "CMRC", "split": "dev"}},
        "tags": ["zh-CN"],
    }
    created = client.post("/api/v1/datasets", json={"name": "cmrc-roundtrip", "owner": "backend-tests", "schema_version": "2.0"})
    assert created.status_code == 201
    dataset_id = created.json()["id"]
    imported = client.post(f"/api/v1/datasets/{dataset_id}/samples:import", json={"samples": [payload]})
    assert imported.status_code == 201, imported.json()

    saved = client.get(f"/api/v1/datasets/{dataset_id}/samples")
    assert saved.status_code == 200
    item = saved.json()["items"][0]
    assert item["question"] == payload["question"]
    assert item["contexts"] == [{
        **payload["contexts"][0], "rank_before": None,
        "relevance_grade": None, "usefulness": None,
    }]
    assert item["labels"] == payload["labels"]
    # The backend's compatibility echo is intentional and represents the same
    # alternate-reference field that the client normalizes on resume.
    assert item["metadata"] == {**payload["metadata"], "reference_answers": ["候选一", "候选二"]}


def test_duplicate_batch_is_rejected_atomically(client, sample_payload) -> None:
    created = client.post(
        "/api/v1/datasets",
        json={"name": "duplicates", "owner": "backend-tests"},
    )
    dataset_id = created.json()["id"]
    duplicate = dict(sample_payload)

    response = client.post(
        f"/api/v1/datasets/{dataset_id}/samples:import",
        json={"samples": [sample_payload, duplicate]},
    )
    dataset = client.get(f"/api/v1/datasets/{dataset_id}")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert dataset.json()["sample_count"] == 0


def test_empty_publish_and_published_mutation_are_conflicts(client, sample_payload) -> None:
    empty = client.post(
        "/api/v1/datasets",
        json={"name": "empty-dataset", "owner": "backend-tests"},
    )
    empty_publish = client.post(f"/api/v1/datasets/{empty.json()['id']}:publish")
    dataset_id = create_published_dataset(client, [sample_payload])
    mutate = client.post(
        f"/api/v1/datasets/{dataset_id}/samples:import",
        json={"samples": [{**sample_payload, "sample_id": "later"}]},
    )

    assert empty_publish.status_code == 409
    assert empty_publish.json()["error"]["code"] == "DATASET_EMPTY"
    assert mutate.status_code == 409
    assert mutate.json()["error"]["code"] == "DATASET_IMMUTABLE"
