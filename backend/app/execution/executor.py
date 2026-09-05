from __future__ import annotations

import re
from typing import Any

from app.evaluation import DeterministicRAGEvaluator, EvaluationProfile
from app.execution.contracts import EvaluatedOutput, GeneratedOutput
from app.execution.model import GenerationConfig, ModelAdapter, ModelContext, ModelRequest
from app.persistence.models import DatasetSample


class ModelEvaluationExecutor:
    """Turns an immutable execution snapshot into one model call per sample."""

    def __init__(
        self,
        adapter: ModelAdapter,
        snapshot: dict[str, Any],
    ) -> None:
        self.adapter = adapter
        self.snapshot = snapshot
        self.adapter_id = str(snapshot["adapter_id"])
        self.provider_id = snapshot.get("provider_id")
        self.prompt = str(snapshot["prompt"]["text"])
        self.generation = GenerationConfig.model_validate(snapshot["generation"])
        self.context_policy = str(snapshot["context_policy"])
        self.evaluator = DeterministicRAGEvaluator(
            EvaluationProfile.from_metric_config(snapshot.get("metric_config") or [])
        )

    def generate(self, sample: DatasetSample) -> GeneratedOutput:
        contexts = list(sample.retrieved_contexts or []) if self.context_policy == "dataset_contexts" else []
        visible_contexts = []
        for raw in sorted(contexts, key=lambda item: int(item.get("rank", 0))):
            text = raw.get("text")
            rank = raw.get("rank")
            if not isinstance(text, str) or not text.strip():
                continue
            if not isinstance(rank, int) or isinstance(rank, bool) or rank < 1:
                continue
            visible_contexts.append(ModelContext(position=rank, text=text))
        request = ModelRequest(
            question=sample.question,
            context=visible_contexts,
            prompt=self.prompt,
            generation=self.generation,
        )
        response = self.adapter.generate(request)
        citations = _parse_citations(response.answer, contexts)
        return GeneratedOutput(
            response=response,
            contexts=contexts,
            citations=citations,
            attempts=[item.model_dump(mode="json") for item in self.adapter.last_attempts],
        )

    def evaluate_generated(
        self,
        sample: DatasetSample,
        generated: GeneratedOutput,
    ) -> EvaluatedOutput:
        artifacts = self.evaluator.evaluate(
            sample,
            answer=generated.response.answer,
            contexts=generated.contexts,
            citations=generated.citations,
            enforce_context_origin=True,
        )
        return EvaluatedOutput(
            metric_results=artifacts.metric_results,
            diagnoses=artifacts.diagnoses,
        )


def _parse_citations(answer: str, contexts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    context_ids = {
        str(context.get("chunk_id"))
        for context in contexts
        if context.get("chunk_id") is not None
    }
    position_targets = {
        str(context["rank"]): str(context["chunk_id"])
        for context in contexts
        if context.get("rank") is not None and context.get("chunk_id") is not None
    }
    citations: list[dict[str, Any]] = []
    for index, match in enumerate(re.finditer(r"\[([^\[\]]+)\]", answer), start=1):
        target_id = match.group(1).strip()
        if target_id == "mock":
            continue
        target_id = position_targets.get(target_id, target_id)
        citations.append(
            {
                "citation_id": f"citation-{index}",
                "claim_id": None,
                "raw": match.group(0),
                "target_type": "context_item",
                "target_id": target_id,
                "resolved": target_id in context_ids,
                "supports_claim": None,
                "support_judge_version": None,
            }
        )
    return citations
