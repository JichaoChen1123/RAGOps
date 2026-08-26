from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'ragops-test.db'}",
        log_level="WARNING",
        auto_create_schema=True,
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def sample_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "sample_id": "support-policy-001",
        "question": "企业版审计日志默认保留多久？",
        "reference_answer": "企业版审计日志默认保留 180 天。",
        "gold_document_ids": ["policy-audit"],
        "gold_evidence_ids": ["ev-audit-retention"],
        "retrieved_contexts": [
            {
                "rank": 1,
                "doc_id": "policy-audit",
                "chunk_id": "audit-01",
                "evidence_ids": ["ev-audit-retention"],
                "text": "企业版工作区的审计日志默认保留 180 天。",
                "score": 0.97,
            }
        ],
        "answer": "企业版账户的审计日志默认保留 180 天。[audit-01]",
        "citations": [{"claim_id": "c1", "chunk_id": "audit-01"}],
        "tags": ["happy-path", "zh-CN"],
        "metadata": {"source": "synthetic"},
    }


def create_published_dataset(client: TestClient, samples: list[dict[str, object]]) -> str:
    created = client.post(
        "/api/v1/datasets",
        json={"name": f"dataset-{samples[0]['sample_id']}", "schema_version": "1.0"},
    )
    assert created.status_code == 201
    dataset_id = created.json()["id"]
    imported = client.post(
        f"/api/v1/datasets/{dataset_id}/samples:import",
        json={"samples": samples},
    )
    assert imported.status_code == 201
    published = client.post(f"/api/v1/datasets/{dataset_id}:publish")
    assert published.status_code == 200
    return dataset_id
