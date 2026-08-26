from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class EvaluationProfile:
    """Versioned thresholds and windows used by the deterministic MVP."""

    version: str = "mvp-default-1.0.0"
    retrieval_ks: tuple[int, ...] = (1, 3, 5, 10)
    diagnosis_k: int = 3
    context_relevance_ratio_low: float = 0.5
    include_not_determinable: bool = True

    def __post_init__(self) -> None:
        if not self.retrieval_ks or any(k <= 0 for k in self.retrieval_ks):
            raise ValueError("retrieval_ks must contain positive integers")
        if self.diagnosis_k <= 0:
            raise ValueError("diagnosis_k must be positive")
        if not 0.0 <= self.context_relevance_ratio_low <= 1.0:
            raise ValueError("context_relevance_ratio_low must be between 0 and 1")

    @classmethod
    def from_metric_config(cls, metric_config: Iterable[dict[str, Any]]) -> EvaluationProfile:
        configured_ks: set[int] = set()
        for metric in metric_config:
            parameters = metric.get("parameters") or {}
            raw_k = parameters.get("k")
            if isinstance(raw_k, int) and not isinstance(raw_k, bool) and raw_k > 0:
                configured_ks.add(raw_k)
            match = re.search(r"(?:@|_at_)(\d+)$", str(metric.get("name", "")))
            if match:
                configured_ks.add(int(match.group(1)))
        if not configured_ks:
            return cls()
        ks = tuple(sorted(configured_ks))
        return cls(retrieval_ks=ks, diagnosis_k=max(ks))
