from __future__ import annotations

from copy import deepcopy

from app.evaluation import DeterministicRAGEvaluator, EvaluationProfile
from helpers import dataset_sample, load_sanitized_samples


SANITIZED_SAMPLES = load_sanitized_samples()


def _diagnoses_by_rule(artifacts):
    return {item["rule_id"]: item for item in artifacts.diagnoses}


def test_retrieval_missing_rule_uses_observed_gold_absence():
    sample = dataset_sample(SANITIZED_SAMPLES["rag-retrieval-miss-001"])

    diagnosis = _diagnoses_by_rule(DeterministicRAGEvaluator().evaluate(sample))[
        "retrieval.missing_evidence"
    ]

    assert diagnosis["status"] == "suspected"
    assert diagnosis["confidence"] == 0.75
    assert diagnosis["evidence"][0]["gold_ids"] == ["ev-recovery-30d"]
    assert diagnosis["reason"]


def test_context_pollution_rule_identifies_distractors():
    sample = dataset_sample(SANITIZED_SAMPLES["rag-context-pollution-001"])

    diagnosis = _diagnoses_by_rule(DeterministicRAGEvaluator().evaluate(sample))["context.pollution"]

    assert diagnosis["status"] == "suspected"
    assert diagnosis["confidence"] is not None
    assert diagnosis["evidence"][0]["distractor_chunk_ids"] == ["enterprise-01", "storage-02"]


def test_citation_missing_rule_is_confirmed_when_support_exists():
    sample = dataset_sample(SANITIZED_SAMPLES["rag-citation-missing-001"])

    diagnosis = _diagnoses_by_rule(DeterministicRAGEvaluator().evaluate(sample))["citation.missing"]

    assert diagnosis["status"] == "confirmed"
    assert diagnosis["confidence"] == 1.0
    assert diagnosis["evidence"][0]["citation_count"] == 0


def test_rerank_rule_reports_unknown_without_pre_ranks_and_confirms_drop_with_evidence():
    payload = SANITIZED_SAMPLES["rag-rerank-failure-001"]
    unknown = _diagnoses_by_rule(DeterministicRAGEvaluator().evaluate(dataset_sample(payload)))[
        "rerank.no_gain_or_regression"
    ]
    assert unknown["status"] == "not_determinable"
    assert unknown["confidence"] is None
    assert unknown["missing_inputs"] == ["retrieved_contexts[].rank_before"]

    comparable_payload = deepcopy(payload)
    comparable_payload["retrieved_contexts"][-1]["rank_before"] = 1
    evaluator = DeterministicRAGEvaluator(EvaluationProfile(diagnosis_k=3))
    confirmed = _diagnoses_by_rule(evaluator.evaluate(dataset_sample(comparable_payload)))[
        "rerank.no_gain_or_regression"
    ]

    assert confirmed["status"] == "confirmed"
    assert confirmed["evidence"][0]["rank_changes"] == [
        {"chunk_id": "rotation-04", "rank_before": 1, "rank_after": 4, "delta": 3}
    ]


def test_happy_path_has_no_positive_diagnosis():
    sample = dataset_sample(SANITIZED_SAMPLES["rag-perfect-001"])
    artifacts = DeterministicRAGEvaluator().evaluate(sample)

    positives = [
        diagnosis
        for diagnosis in artifacts.diagnoses
        if diagnosis["status"] in {"confirmed", "suspected"}
    ]
    assert positives == []
    assert {metric["metric_name"] for metric in artifacts.metric_results} >= {
        "recall_at_3",
        "mrr_at_3",
        "ndcg_at_3",
        "context_precision",
        "context_recall",
        "citation_hit_rate",
        "answer_reference_exact_match",
    }
