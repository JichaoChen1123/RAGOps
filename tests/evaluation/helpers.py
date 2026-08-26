from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.persistence.models import DatasetSample
from app.schemas.datasets import DatasetSampleInput


REPO_ROOT = Path(__file__).resolve().parents[2]


def load_metric_oracle() -> dict[str, Any]:
    path = REPO_ROOT / "examples" / "eval-samples" / "metric-cases.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_sanitized_samples() -> dict[str, dict[str, Any]]:
    path = REPO_ROOT / "examples" / "eval-samples" / "valid-samples.jsonl"
    return {
        payload["sample_id"]: payload
        for payload in (
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }


def dataset_sample(payload: dict[str, Any]) -> DatasetSample:
    parsed = DatasetSampleInput.model_validate(payload)
    return DatasetSample(
        external_id=parsed.sample_id,
        question=parsed.question,
        reference_answer=parsed.reference_answer,
        gold_document_ids=parsed.gold_document_ids,
        gold_evidence_ids=parsed.gold_evidence_ids,
        retrieved_contexts=[item.model_dump(mode="json") for item in parsed.retrieved_contexts],
        answer=parsed.answer,
        citations=[item.model_dump(mode="json") for item in parsed.citations],
        tags=parsed.tags,
        expected_diagnoses=parsed.expected_diagnoses,
        metadata_json=parsed.metadata,
        content_sha256="0" * 64,
    )
