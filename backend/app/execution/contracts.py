from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.execution.model import ModelResponse
from app.persistence.models import DatasetSample


@dataclass(frozen=True)
class GeneratedOutput:
    response: ModelResponse
    contexts: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    attempts: list[dict[str, Any]]


@dataclass(frozen=True)
class EvaluatedOutput:
    metric_results: list[dict[str, Any]]
    diagnoses: list[dict[str, Any]]


@dataclass(frozen=True)
class ExecutionResult:
    """Legacy all-at-once result retained for explicitly injected test executors."""

    answer: str
    retrieval_results: list[dict[str, Any]]
    metric_results: list[dict[str, Any]]
    diagnoses: list[dict[str, Any]]
    latency_ms: int


class EvaluationExecutor(Protocol):
    def evaluate(self, sample: DatasetSample) -> ExecutionResult: ...


class SnapshotExecutor(Protocol):
    adapter_id: str
    provider_id: str | None

    def generate(self, sample: DatasetSample) -> GeneratedOutput: ...

    def evaluate_generated(
        self,
        sample: DatasetSample,
        generated: GeneratedOutput,
    ) -> EvaluatedOutput: ...
