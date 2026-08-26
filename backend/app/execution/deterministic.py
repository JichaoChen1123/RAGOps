from __future__ import annotations

from app.execution.contracts import ExecutionResult
from app.persistence.models import DatasetSample


class DeterministicExecutor:
    """Local orchestration fixture; it deliberately implements no quality metric."""

    def evaluate(self, sample: DatasetSample) -> ExecutionResult:
        answer = sample.answer or sample.reference_answer or "该样本已由确定性占位执行器处理。"
        return ExecutionResult(
            answer=answer,
            retrieval_results=sample.retrieved_contexts,
            metric_results=[
                {
                    "metric_name": "execution_success",
                    "metric_version": "placeholder-1.0.0",
                    "status": "succeeded",
                    "value": True,
                    "details": {
                        "note": "Operational placeholder only; no RAG quality score was computed."
                    },
                }
            ],
            diagnoses=[],
            latency_ms=0,
        )
