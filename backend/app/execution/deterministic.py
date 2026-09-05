from __future__ import annotations

from typing import Any, Iterable

from app.evaluation import DeterministicRAGEvaluator, EvaluationProfile
from app.execution.contracts import ExecutionResult
from app.persistence.models import DatasetSample


class DeterministicExecutor:
    """Backend execution adapter for the deterministic RAG evaluator."""

    def __init__(self, profile: EvaluationProfile | None = None) -> None:
        self.profile = profile or EvaluationProfile()
        self.evaluator = DeterministicRAGEvaluator(self.profile)

    @classmethod
    def from_metric_config(cls, metric_config: Iterable[dict[str, Any]]) -> DeterministicExecutor:
        return cls(EvaluationProfile.from_metric_config(metric_config))

    def evaluate(self, sample: DatasetSample) -> ExecutionResult:
        contexts = list(sample.retrieved_contexts or [])
        visible_text = next(
            (
                str(context.get("text", "")).strip()
                for context in sorted(contexts, key=lambda item: int(item.get("rank", 0)))
                if str(context.get("text", "")).strip()
            ),
            None,
        )
        answer = (
            f"[mock] {visible_text[:500]}"
            if visible_text
            else f"[mock] Insufficient context for: {sample.question}"
        )
        artifacts = self.evaluator.evaluate(
            sample,
            answer=answer,
            contexts=contexts,
            citations=[],
        )
        return ExecutionResult(
            answer=answer,
            retrieval_results=contexts,
            metric_results=artifacts.metric_results,
            diagnoses=artifacts.diagnoses,
            latency_ms=0,
        )
