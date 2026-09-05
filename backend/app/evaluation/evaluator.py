from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.evaluation.diagnostics import diagnose
from app.evaluation.features import build_features, item_relevance
from app.evaluation.metrics import (
    answer_reference_exact_match,
    citation_hit_rate,
    citation_resolution_rate,
    citation_support_rate,
    context_precision,
    context_recall,
    context_relevance_ratio,
    mrr_at_k,
    ndcg_at_k,
    recall_at_k,
    unavailable_metric,
)
from app.evaluation.profile import EvaluationProfile
from app.persistence.models import DatasetSample


@dataclass(frozen=True)
class EvaluationArtifacts:
    metric_results: list[dict[str, Any]]
    diagnoses: list[dict[str, Any]]


class DeterministicRAGEvaluator:
    """Pure local evaluator: no network calls, LLM judges, or mutable state."""

    def __init__(self, profile: EvaluationProfile | None = None) -> None:
        self.profile = profile or EvaluationProfile()

    def evaluate(
        self,
        sample: DatasetSample,
        *,
        answer: str | None = None,
        contexts: list[dict[str, Any]] | None = None,
        citations: list[dict[str, Any]] | None = None,
        enforce_context_origin: bool = False,
        retrieval_run_id: str | None = None,
    ) -> EvaluationArtifacts:
        features = build_features(
            sample,
            answer=answer,
            contexts=contexts,
            citations_input=citations,
            enforce_context_origin=enforce_context_origin,
            retrieval_run_id=retrieval_run_id,
        )
        metrics = []
        for k in self.profile.retrieval_ks:
            if features.retrieval_metric_status == "ok":
                metrics.extend(
                    [
                        recall_at_k(features.gold_ids, features.retrieval_items, k),
                        mrr_at_k(features.gold_ids, features.retrieval_items, k),
                        ndcg_at_k(features.gold_ids, features.retrieval_items, k),
                    ]
                )
            else:
                reason = (
                    "context provenance cannot prove this run retrieved the items"
                    if features.retrieval_metric_status == "unknown"
                    else "provided context is not a retrieval run"
                )
                metrics.extend(
                    [
                        unavailable_metric(
                            f"recall_at_{k}", features.retrieval_metric_status, reason
                        ),
                        unavailable_metric(
                            f"mrr_at_{k}", features.retrieval_metric_status, reason
                        ),
                        unavailable_metric(
                            f"ndcg_at_{k}", features.retrieval_metric_status, reason
                        ),
                    ]
                )
        relevance_flags = [item_relevance(item) for item in features.ranked_items]
        covered_gold_ids = set().union(*(item.relevant_ids for item in features.ranked_items)) if features.ranked_items else set()
        metrics.extend(
            [
                context_precision(relevance_flags, judgements_available=features.relevance_available),
                context_relevance_ratio(relevance_flags, judgements_available=features.relevance_available),
                (
                    context_recall(features.gold_ids, covered_gold_ids)
                    if features.retrieval_metric_status == "ok"
                    else unavailable_metric(
                        "context_recall",
                        features.retrieval_metric_status,
                        "context provenance does not establish current-run retrieval",
                    )
                ),
                citation_resolution_rate(features.citations),
                citation_support_rate(features.citations),
                citation_hit_rate(features.citations),
                answer_reference_exact_match(features.answer, features.reference_answer),
            ]
        )
        diagnoses = diagnose(features, self.profile)
        return EvaluationArtifacts(
            metric_results=[result.as_dict() for result in metrics],
            diagnoses=[result.as_dict() for result in diagnoses],
        )
