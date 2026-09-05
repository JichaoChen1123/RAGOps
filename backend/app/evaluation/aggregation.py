from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import Any


def aggregate_metric_results(
    sample_metric_results: Iterable[list[dict[str, Any]]],
    *,
    total_count: int,
    succeeded_count: int,
    execution_metric_version: str = "2.0.0",
) -> list[dict[str, Any]]:
    rows = list(sample_metric_results)
    report: list[dict[str, Any]] = [
        {
            "metric_name": "execution_success_rate",
            "metric_version": execution_metric_version,
            "status": "ok",
            "value": succeeded_count / total_count if total_count else None,
            "evaluated_count": total_count,
            "excluded_count": 0,
            "details": {"aggregation": "successful_samples / total_samples"},
        }
    ]
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for metric_results in rows:
        for result in metric_results:
            grouped[(str(result["metric_name"]), str(result.get("metric_version", "1.0.0")))].append(result)

    for (name, version), results in sorted(grouped.items()):
        values = [
            float(result["value"])
            for result in results
            if result.get("status") == "ok"
            and isinstance(result.get("value"), (int, float, bool))
        ]
        evaluated_count = len(values)
        excluded_count = total_count - evaluated_count
        status_counts = _status_counts(results)
        aggregate_status = "ok" if values else _aggregate_empty_status(status_counts)
        report.append(
            {
                "metric_name": name,
                "metric_version": version,
                "status": aggregate_status,
                "value": sum(values) / len(values) if values else None,
                "evaluated_count": evaluated_count,
                "excluded_count": excluded_count,
                "details": {
                    "aggregation": "macro_mean",
                    "sample_status_counts": status_counts,
                },
            }
        )
    return report


def _status_counts(results: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for result in results:
        counts[str(result.get("status", "error"))] += 1
    return dict(sorted(counts.items()))


def _aggregate_empty_status(counts: dict[str, int]) -> str:
    for status in ("error", "unknown", "not_evaluated", "not_applicable", "legacy"):
        if counts.get(status):
            return status
    return "not_evaluated"
