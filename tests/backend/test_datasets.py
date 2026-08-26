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


def test_duplicate_batch_is_rejected_atomically(client, sample_payload) -> None:
    created = client.post("/api/v1/datasets", json={"name": "duplicates"})
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
    empty = client.post("/api/v1/datasets", json={"name": "empty-dataset"})
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
