from __future__ import annotations

from app.evaluation.contracts import DiagnosisResult, EvaluationFeatures
from app.evaluation.features import item_relevance
from app.evaluation.profile import EvaluationProfile


def diagnose(features: EvaluationFeatures, profile: EvaluationProfile) -> list[DiagnosisResult]:
    results: list[DiagnosisResult] = []
    retrieval = _retrieval_missing(features, profile)
    if retrieval is not None:
        results.append(retrieval)
    pollution = _context_pollution(features, profile)
    if pollution is not None:
        results.append(pollution)
    citation = _citation_missing(features, profile, retrieval)
    if citation is not None:
        results.append(citation)
    rerank = _rerank_regression(features, profile)
    if rerank is not None:
        results.append(rerank)
    return results


def _retrieval_missing(
    features: EvaluationFeatures,
    profile: EvaluationProfile,
) -> DiagnosisResult | None:
    rule_id = "retrieval.missing_evidence"
    if features.retrieval_metric_status != "ok":
        return _unknown(
            rule_id,
            profile,
            "Current-run retrieval provenance is unavailable.",
            ["contexts[].origin=retrieved and matching retrieval_run_id"],
        )
    if not features.gold_ids:
        return _unknown(
            rule_id,
            profile,
            "Gold evidence is unavailable, so retrieval recall cannot be audited.",
            ["gold_evidence_ids or gold_document_ids"],
        )
    all_covered = set().union(*(item.relevant_ids for item in features.ranked_items)) if features.ranked_items else set()
    if features.gold_ids.intersection(all_covered):
        return None
    return DiagnosisResult(
        rule_id=rule_id,
        status="suspected",
        severity="high",
        confidence=0.75,
        reason="No observed retrieval candidate contains any gold evidence; corpus presence is not available to confirm the root cause.",
        evidence=[
            {"gold_ids": sorted(features.gold_ids), "relevance_unit": features.relevance_unit},
            {
                "observed_candidate_count": len(features.ranked_items),
                "observed_chunk_ids": [item.chunk_id for item in features.ranked_items],
            },
        ],
        suggestions=[
            "Verify that the gold evidence exists in the locked corpus version.",
            "Audit query rewriting, filters, document-ID alignment, and per-retriever recall.",
        ],
        profile_version=profile.version,
    )


def _context_pollution(
    features: EvaluationFeatures,
    profile: EvaluationProfile,
) -> DiagnosisResult | None:
    rule_id = "context.pollution"
    if not features.relevance_available:
        return _unknown(
            rule_id,
            profile,
            "Neither gold alignment nor explicit usefulness judgements are available.",
            ["gold evidence or context usefulness judgements"],
        )
    if not features.ranked_items:
        return None
    relevant = [item for item in features.ranked_items if item_relevance(item)]
    irrelevant = [item for item in features.ranked_items if not item_relevance(item)]
    ratio = len(relevant) / len(features.ranked_items)
    if not relevant or not irrelevant or ratio >= profile.context_relevance_ratio_low:
        return None
    confidence = min(0.9, 0.6 + (profile.context_relevance_ratio_low - ratio))
    return DiagnosisResult(
        rule_id=rule_id,
        status="suspected",
        severity="medium",
        confidence=confidence,
        reason="The final context contains useful evidence but is dominated by contexts that do not align with gold evidence or usefulness labels.",
        evidence=[
            {
                "context_relevance_ratio": ratio,
                "profile_threshold": profile.context_relevance_ratio_low,
                "relevant_chunk_ids": [item.chunk_id for item in relevant],
                "distractor_chunk_ids": [item.chunk_id for item in irrelevant],
            }
        ],
        suggestions=[
            "Inspect rerank, deduplication, source freshness, and context-window packing.",
            "Run a counterfactual evaluation after removing the identified distractors.",
        ],
        profile_version=profile.version,
    )


def _citation_missing(
    features: EvaluationFeatures,
    profile: EvaluationProfile,
    retrieval_result: DiagnosisResult | None,
) -> DiagnosisResult | None:
    rule_id = "citation.missing"
    if features.answer is None or not features.answer.strip():
        return _unknown(rule_id, profile, "No answer is available to inspect.", ["answer"])
    if not features.answerable:
        return None
    relevant_chunks = [item.chunk_id for item in features.ranked_items if item_relevance(item)]
    if not relevant_chunks:
        blocked = [retrieval_result.rule_id] if retrieval_result and retrieval_result.status != "not_determinable" else []
        return _unknown(
            rule_id,
            profile,
            "Citation requirements cannot be evaluated because no supporting context is observable.",
            ["supporting context"],
            blocked_by=blocked,
        )
    if features.citations:
        return None
    return DiagnosisResult(
        rule_id=rule_id,
        status="confirmed",
        severity="medium",
        confidence=1.0,
        reason="An answer was produced from observable supporting context, but the parsed citation list is empty.",
        evidence=[
            {
                "citation_count": 0,
                "supporting_chunk_ids": relevant_chunks,
                "answer_character_count": len(features.answer),
            }
        ],
        suggestions=[
            "Require structured claim-level citations in the generation contract.",
            "Validate citation targets on the server before publishing the answer.",
        ],
        profile_version=profile.version,
    )


def _rerank_regression(
    features: EvaluationFeatures,
    profile: EvaluationProfile,
) -> DiagnosisResult | None:
    rule_id = "rerank.no_gain_or_regression"
    if features.retrieval_metric_status != "ok":
        return _unknown(
            rule_id,
            profile,
            "Current-run retrieval provenance is unavailable for rerank comparison.",
            ["retrieved contexts from the current run"],
        )
    relevant = [item for item in features.ranked_items if item_relevance(item)]
    comparable = [item for item in relevant if item.rank_before is not None]
    if not comparable:
        return _unknown(
            rule_id,
            profile,
            "Pre-rerank ranks are unavailable for relevant candidates.",
            ["retrieved_contexts[].rank_before"],
        )
    dropped = [
        item
        for item in comparable
        if item.rank_before is not None and item.rank_before <= profile.diagnosis_k < item.rank
    ]
    if not dropped:
        return None
    return DiagnosisResult(
        rule_id=rule_id,
        status="confirmed",
        severity="high",
        confidence=0.95,
        reason="Gold-aligned evidence was inside the effective window before reranking and fell outside it afterward.",
        evidence=[
            {
                "k": profile.diagnosis_k,
                "rank_changes": [
                    {
                        "chunk_id": item.chunk_id,
                        "rank_before": item.rank_before,
                        "rank_after": item.rank,
                        "delta": item.rank - item.rank_before,
                    }
                    for item in dropped
                    if item.rank_before is not None
                ],
            }
        ],
        suggestions=[
            "Verify score direction, query-document input assembly, and rerank truncation.",
            "Compare enabled and bypassed rerank on the same candidate pool.",
        ],
        profile_version=profile.version,
    )


def _unknown(
    rule_id: str,
    profile: EvaluationProfile,
    reason: str,
    missing_inputs: list[str],
    *,
    blocked_by: list[str] | None = None,
) -> DiagnosisResult | None:
    if not profile.include_not_determinable:
        return None
    return DiagnosisResult(
        rule_id=rule_id,
        status="not_determinable",
        severity="info",
        confidence=None,
        reason=reason,
        missing_inputs=missing_inputs,
        blocked_by_rule_ids=blocked_by or [],
        profile_version=profile.version,
    )
