from __future__ import annotations

import pytest

from app.evaluation.contracts import CitationJudgement, RankedItem
from app.evaluation.metrics import (
    answer_reference_exact_match,
    citation_hit_rate,
    context_precision,
    context_recall,
    mrr_at_k,
    ndcg_at_k,
    recall_at_k,
)
from helpers import load_metric_oracle


METRIC_ORACLE = load_metric_oracle()


def _case(oracle, case_id):
    return next(case for case in oracle["cases"] if case["case_id"] == case_id)


def _ranked_items(gold_ids, retrieved_ids, grades):
    gold = set(gold_ids)
    return [
        RankedItem(
            rank=index,
            key=item_id,
            doc_id=item_id,
            chunk_id=item_id,
            relevant_ids=frozenset({item_id}) if item_id in gold else frozenset(),
            relevance_grade=grade,
        )
        for index, (item_id, grade) in enumerate(zip(retrieved_ids, grades, strict=True), start=1)
    ]


@pytest.mark.parametrize("k", [1, 3, 4])
def test_ranked_metrics_match_qa_oracle(k):
    case = _case(METRIC_ORACLE, "ranked-mixed")
    inputs = case["input"]
    items = _ranked_items(
        inputs["gold_document_ids"],
        inputs["retrieved_document_ids"],
        inputs["relevance_grades"],
    )
    expected = case["expected"][f"at_{k}"]

    assert recall_at_k(inputs["gold_document_ids"], items, k).value == pytest.approx(expected["recall"])
    assert mrr_at_k(inputs["gold_document_ids"], items, k).value == pytest.approx(expected["mrr"])
    assert ndcg_at_k(inputs["gold_document_ids"], items, k).value == pytest.approx(expected["ndcg"])


def test_ranked_metrics_deduplicate_documents():
    case = _case(METRIC_ORACLE, "duplicate-document")
    inputs = case["input"]
    items = _ranked_items(
        inputs["gold_document_ids"],
        inputs["retrieved_document_ids"],
        inputs["relevance_grades"],
    )
    k = inputs["k"]

    assert recall_at_k(inputs["gold_document_ids"], items, k).value == 1.0
    assert mrr_at_k(inputs["gold_document_ids"], items, k).value == 1.0
    assert ndcg_at_k(inputs["gold_document_ids"], items, k).value == 1.0


def test_empty_gold_is_not_applicable():
    case = _case(METRIC_ORACLE, "no-gold")
    inputs = case["input"]
    items = _ranked_items([], inputs["retrieved_document_ids"], inputs["relevance_grades"])

    for result in (recall_at_k([], items, 1), mrr_at_k([], items, 1), ndcg_at_k([], items, 1)):
        assert result.status == "not_applicable"
        assert result.value is None
        assert "gold" in result.details["reason"]


def test_context_metrics_match_qa_oracle():
    case = _case(METRIC_ORACLE, "context-partial")
    inputs = case["input"]
    expected = case["expected"]

    precision = context_precision(
        [bool(value) for value in inputs["context_relevance_flags"]],
        judgements_available=True,
    )
    recall = context_recall(inputs["gold_evidence_ids"], inputs["covered_gold_evidence_ids"])

    assert precision.value == pytest.approx(expected["context_precision"])
    assert recall.value == pytest.approx(expected["context_recall"])


def test_citation_metric_matches_qa_oracle():
    case = _case(METRIC_ORACLE, "citation-partial")
    judgements = [
        CitationJudgement(
            citation_id=item["citation_id"],
            chunk_id=item["citation_id"],
            resolves=item["resolves"],
            supports_claim=item["supports_claim"],
        )
        for item in case["input"]["citation_judgements"]
    ]

    result = citation_hit_rate(judgements)

    assert result.value == pytest.approx(case["expected"]["citation_hit_rate"])
    assert result.details["invalid_citation_ids"] == case["expected"]["invalid_citation_ids"]


def test_empty_citations_and_missing_answer_inputs_are_not_applicable():
    assert citation_hit_rate([]).status == "not_applicable"
    assert answer_reference_exact_match(None, "reference").status == "not_applicable"
    assert answer_reference_exact_match("answer", None).status == "not_applicable"


def test_exact_match_normalizes_whitespace_case_and_citation_suffix():
    result = answer_reference_exact_match("  Policy VALUE [ctx-1] ", "policy value")

    assert result.status == "ok"
    assert result.value is True
