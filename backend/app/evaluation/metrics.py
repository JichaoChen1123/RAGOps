from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Iterable, Sequence

from app.evaluation.contracts import CitationJudgement, MetricResult, RankedItem


def deduplicate_ranked_items(items: Sequence[RankedItem]) -> list[RankedItem]:
    """Deduplicate by item key, preserving the earliest rank."""

    ordered = sorted(items, key=lambda item: item.rank)
    seen: set[str] = set()
    result: list[RankedItem] = []
    for item in ordered:
        if item.key in seen:
            continue
        seen.add(item.key)
        result.append(item)
    return result


def recall_at_k(
    gold_ids: Iterable[str],
    items: Sequence[RankedItem],
    k: int,
) -> MetricResult:
    gold = set(gold_ids)
    name = f"recall_at_{k}"
    if not gold:
        return _not_applicable(name, "gold evidence is empty")
    window = deduplicate_ranked_items(items)[:k]
    retrieved_ids = set().union(*(item.relevant_ids for item in window)) if window else set()
    matched = gold.intersection(retrieved_ids)
    return MetricResult(
        metric_name=name,
        value=len(matched) / len(gold),
        details={
            "k": k,
            "gold_count": len(gold),
            "matched_ids": sorted(matched),
            "missing_ids": sorted(gold - matched),
            "deduplicated_item_keys": [item.key for item in window],
        },
    )


def mrr_at_k(
    gold_ids: Iterable[str],
    items: Sequence[RankedItem],
    k: int,
) -> MetricResult:
    gold = set(gold_ids)
    name = f"mrr_at_{k}"
    if not gold:
        return _not_applicable(name, "gold evidence is empty")
    first_relevant_rank: int | None = None
    for rank, item in enumerate(deduplicate_ranked_items(items)[:k], start=1):
        if gold.intersection(item.relevant_ids):
            first_relevant_rank = rank
            break
    return MetricResult(
        metric_name=name,
        value=0.0 if first_relevant_rank is None else 1.0 / first_relevant_rank,
        details={"k": k, "first_relevant_rank": first_relevant_rank},
    )


def ndcg_at_k(
    gold_ids: Iterable[str],
    items: Sequence[RankedItem],
    k: int,
) -> MetricResult:
    gold = set(gold_ids)
    name = f"ndcg_at_{k}"
    if not gold:
        return _not_applicable(name, "gold evidence is empty")
    ranked = deduplicate_ranked_items(items)
    actual_grades = [item.relevance_grade for item in ranked[:k]]
    grade_by_gold = {gold_id: 1 for gold_id in gold}
    for item in ranked:
        for gold_id in gold.intersection(item.relevant_ids):
            grade_by_gold[gold_id] = max(grade_by_gold[gold_id], item.relevance_grade)
    ideal_grades = sorted(grade_by_gold.values(), reverse=True)[:k]
    dcg = _dcg(actual_grades)
    idcg = _dcg(ideal_grades)
    if idcg == 0:
        return _not_applicable(name, "ideal DCG is zero", {"k": k, "dcg": dcg})
    return MetricResult(
        metric_name=name,
        value=dcg / idcg,
        details={
            "k": k,
            "actual_grades": actual_grades,
            "ideal_grades": ideal_grades,
            "dcg": dcg,
            "idcg": idcg,
        },
    )


def context_precision(
    relevance_flags: Sequence[bool],
    *,
    judgements_available: bool,
) -> MetricResult:
    if not judgements_available:
        return _not_applicable("context_precision", "context usefulness judgements are unavailable")
    if not relevance_flags:
        return MetricResult(
            metric_name="context_precision",
            value=0.0,
            details={"context_count": 0, "relevant_count": 0, "precision_at_relevant_positions": []},
        )
    precisions: list[float] = []
    relevant_count = 0
    for position, relevant in enumerate(relevance_flags, start=1):
        if relevant:
            relevant_count += 1
            precisions.append(relevant_count / position)
    value = 0.0 if relevant_count == 0 else sum(precisions) / relevant_count
    return MetricResult(
        metric_name="context_precision",
        value=value,
        details={
            "context_count": len(relevance_flags),
            "relevant_count": relevant_count,
            "precision_at_relevant_positions": precisions,
        },
    )


def context_relevance_ratio(
    relevance_flags: Sequence[bool],
    *,
    judgements_available: bool,
) -> MetricResult:
    if not judgements_available:
        return _not_applicable("context_relevance_ratio", "context relevance is unavailable")
    value = 0.0 if not relevance_flags else sum(relevance_flags) / len(relevance_flags)
    return MetricResult(
        metric_name="context_relevance_ratio",
        value=value,
        details={
            "context_count": len(relevance_flags),
            "relevant_count": sum(relevance_flags),
            "irrelevant_count": len(relevance_flags) - sum(relevance_flags),
        },
    )


def context_recall(
    gold_ids: Iterable[str],
    covered_gold_ids: Iterable[str],
) -> MetricResult:
    gold = set(gold_ids)
    if not gold:
        return _not_applicable("context_recall", "gold evidence is empty")
    covered = gold.intersection(covered_gold_ids)
    return MetricResult(
        metric_name="context_recall",
        value=len(covered) / len(gold),
        details={
            "gold_count": len(gold),
            "covered_count": len(covered),
            "covered_ids": sorted(covered),
            "missing_ids": sorted(gold - covered),
        },
    )


def citation_hit_rate(citations: Sequence[CitationJudgement]) -> MetricResult:
    if not citations:
        return _not_applicable("citation_hit_rate", "answer contains no parsed citations")
    hits = [citation for citation in citations if citation.resolves and citation.supports_claim]
    invalid = [
        citation.citation_id
        for citation in citations
        if not citation.resolves or not citation.supports_claim
    ]
    return MetricResult(
        metric_name="citation_hit_rate",
        value=len(hits) / len(citations),
        details={
            "citation_count": len(citations),
            "hit_count": len(hits),
            "hit_citation_ids": [citation.citation_id for citation in hits],
            "invalid_citation_ids": invalid,
        },
    )


def answer_reference_exact_match(answer: str | None, reference_answer: str | None) -> MetricResult:
    if reference_answer is None or not reference_answer.strip():
        return _not_applicable("answer_reference_exact_match", "reference answer is unavailable")
    if answer is None or not answer.strip():
        return _not_applicable("answer_reference_exact_match", "answer is unavailable")
    normalized_answer = _normalize_answer(answer)
    normalized_reference = _normalize_answer(reference_answer)
    return MetricResult(
        metric_name="answer_reference_exact_match",
        value=normalized_answer == normalized_reference,
        details={
            "normalization": "NFKC, casefold, whitespace collapse, bracket-citation removal",
            "answer_length": len(normalized_answer),
            "reference_length": len(normalized_reference),
        },
    )


def _dcg(grades: Sequence[int]) -> float:
    return sum((2**grade - 1) / math.log2(position + 1) for position, grade in enumerate(grades, start=1))


def _normalize_answer(value: str) -> str:
    without_citations = re.sub(r"\[[^\[\]]+\]", " ", value)
    normalized = unicodedata.normalize("NFKC", without_citations).casefold()
    return " ".join(normalized.split()).strip()


def _not_applicable(
    metric_name: str,
    reason: str,
    details: dict[str, object] | None = None,
) -> MetricResult:
    return MetricResult(
        metric_name=metric_name,
        value=None,
        status="not_applicable",
        details={"reason": reason, **(details or {})},
    )
