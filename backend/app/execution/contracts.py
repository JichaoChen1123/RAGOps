from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.persistence.models import DatasetSample


@dataclass(frozen=True)
class ExecutionResult:
    answer: str
    retrieval_results: list[dict[str, Any]]
    metric_results: list[dict[str, Any]]
    diagnoses: list[dict[str, Any]]
    latency_ms: int


class EvaluationExecutor(Protocol):
    def evaluate(self, sample: DatasetSample) -> ExecutionResult: ...
