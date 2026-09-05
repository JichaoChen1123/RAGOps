from __future__ import annotations

from typing import Any

from app.evaluation.contracts import (
    CitationJudgement,
    EvaluationFeatures,
    RankedItem,
)
from app.persistence.models import DatasetSample


def build_features(
    sample: DatasetSample,
    *,
    answer: str | None = None,
    contexts: list[dict[str, Any]] | None = None,
    citations_input: list[dict[str, Any]] | None = None,
    enforce_context_origin: bool = False,
    retrieval_run_id: str | None = None,
) -> EvaluationFeatures:
    gold_evidence = set(sample.gold_evidence_ids or [])
    gold_documents = set(sample.gold_document_ids or [])
    if gold_evidence:
        gold_ids = gold_evidence
        relevance_unit = "evidence_id"
    elif gold_documents:
        gold_ids = gold_documents
        relevance_unit = "document_id"
    else:
        gold_ids = set()
        relevance_unit = None

    ranked_items: list[RankedItem] = []
    explicit_relevance = False
    raw_contexts = sample.retrieved_contexts if contexts is None else contexts
    origins: set[str] = set()
    for raw in sorted(raw_contexts or [], key=lambda item: int(item.get("rank", 0))):
        evidence_ids = set(_string_list(raw.get("evidence_ids")))
        doc_id = str(raw.get("doc_id") or "")
        chunk_id = str(raw.get("chunk_id") or doc_id)
        relevant_ids = gold_evidence.intersection(evidence_ids) if gold_evidence else gold_documents.intersection({doc_id})
        raw_grade = raw.get("relevance_grade")
        grade = int(raw_grade) if isinstance(raw_grade, int) and not isinstance(raw_grade, bool) else int(bool(relevant_ids))
        usefulness = raw.get("usefulness") if isinstance(raw.get("usefulness"), bool) else None
        explicit_relevance = explicit_relevance or raw_grade is not None or usefulness is not None
        raw_rank_before = raw.get("rank_before")
        rank_before = (
            int(raw_rank_before)
            if isinstance(raw_rank_before, int) and not isinstance(raw_rank_before, bool)
            else None
        )
        origin = str(raw.get("origin") or "legacy_unknown")
        origins.add(origin)
        ranked_items.append(
            RankedItem(
                rank=int(raw.get("rank", len(ranked_items) + 1)),
                key=doc_id or chunk_id,
                doc_id=doc_id,
                chunk_id=chunk_id,
                relevant_ids=frozenset(relevant_ids),
                relevance_grade=grade,
                rank_before=rank_before,
                usefulness=usefulness,
                origin=origin,
                retrieval_run_id=(
                    str(raw["retrieval_run_id"]) if raw.get("retrieval_run_id") else None
                ),
            )
        )

    if not enforce_context_origin:
        retrieval_items = list(ranked_items)
        retrieval_metric_status = "ok"
    else:
        retrieval_items = [
            item
            for item in ranked_items
            if item.origin == "retrieved"
            and retrieval_run_id is not None
            and item.retrieval_run_id == retrieval_run_id
        ]
        if retrieval_items:
            retrieval_metric_status = "ok"
        elif "legacy_unknown" in origins or "retrieved" in origins:
            retrieval_metric_status = "unknown"
        else:
            retrieval_metric_status = "not_evaluated"

    contexts_by_chunk = {item.chunk_id: item for item in ranked_items}
    citations: list[CitationJudgement] = []
    raw_citations = sample.citations if citations_input is None else citations_input
    for index, raw in enumerate(raw_citations or [], start=1):
        chunk_id = str(raw.get("chunk_id") or raw.get("target_id") or "")
        target = contexts_by_chunk.get(chunk_id)
        explicit_resolves = raw.get("resolved")
        resolves = explicit_resolves if isinstance(explicit_resolves, bool) else target is not None
        explicit_support = raw.get("supports_claim")
        supports = explicit_support if isinstance(explicit_support, bool) else None
        citations.append(
            CitationJudgement(
                citation_id=str(raw.get("citation_id") or raw.get("claim_id") or f"citation-{index}"),
                chunk_id=chunk_id,
                resolves=resolves,
                supports_claim=supports,
            )
        )

    answerable = bool((sample.reference_answer or "").strip() or gold_ids)
    context_origin = next(iter(origins)) if len(origins) == 1 else ("mixed" if origins else "none")
    return EvaluationFeatures(
        sample_id=sample.external_id,
        answer=sample.answer if answer is None else answer,
        reference_answer=sample.reference_answer,
        answerable=answerable,
        gold_ids=frozenset(gold_ids),
        relevance_unit=relevance_unit,
        ranked_items=tuple(ranked_items),
        retrieval_items=tuple(retrieval_items),
        retrieval_metric_status=retrieval_metric_status,
        context_origin=context_origin,
        relevance_available=bool(gold_ids) or explicit_relevance,
        citations=tuple(citations),
    )


def item_relevance(item: RankedItem) -> bool:
    return item.usefulness if item.usefulness is not None else item.relevant


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]
