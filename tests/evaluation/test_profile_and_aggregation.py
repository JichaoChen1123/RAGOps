from __future__ import annotations

from app.evaluation.aggregation import aggregate_metric_results
from app.evaluation.profile import EvaluationProfile
from app.schemas.datasets import DatasetSampleInput


def test_metric_config_selects_retrieval_windows():
    profile = EvaluationProfile.from_metric_config(
        [
            {"name": "recall_at_7", "parameters": {}},
            {"name": "ndcg", "parameters": {"k": 3}},
        ]
    )

    assert profile.retrieval_ks == (3, 7)
    assert profile.diagnosis_k == 7


def test_report_aggregation_excludes_not_applicable_values():
    report = aggregate_metric_results(
        [
            [
                {"metric_name": "recall_at_3", "metric_version": "1.0.0", "status": "ok", "value": 1.0},
                {
                    "metric_name": "citation_hit_rate",
                    "metric_version": "1.0.0",
                    "status": "not_applicable",
                    "value": None,
                },
            ],
            [
                {"metric_name": "recall_at_3", "metric_version": "1.0.0", "status": "ok", "value": 0.0},
                {
                    "metric_name": "citation_hit_rate",
                    "metric_version": "1.0.0",
                    "status": "not_applicable",
                    "value": None,
                },
            ],
        ],
        total_count=2,
        succeeded_count=2,
    )
    by_name = {metric["metric_name"]: metric for metric in report}

    assert by_name["recall_at_3"]["value"] == 0.5
    assert by_name["recall_at_3"]["evaluated_count"] == 2
    assert by_name["citation_hit_rate"]["status"] == "not_applicable"
    assert by_name["citation_hit_rate"]["excluded_count"] == 2


def test_unresolved_citation_can_preserve_invalid_target_for_scoring():
    sample = DatasetSampleInput.model_validate(
        {
            "sample_id": "invalid-citation-observation",
            "question": "What is the policy?",
            "citations": [
                {
                    "citation_id": "citation-1",
                    "chunk_id": "missing-chunk",
                    "resolved": False,
                    "supports_claim": False,
                }
            ],
        }
    )

    assert sample.citations[0].resolved is False
