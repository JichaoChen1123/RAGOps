from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


MetricStatus = Literal["ok", "not_applicable", "error"]
DiagnosisStatus = Literal["confirmed", "suspected", "not_determinable"]


@dataclass(frozen=True)
class MetricResult:
    metric_name: str
    value: float | bool | None
    status: MetricStatus = "ok"
    details: dict[str, Any] = field(default_factory=dict)
    metric_version: str = "1.0.0"

    def as_dict(self) -> dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "metric_version": self.metric_version,
            "status": self.status,
            "value": self.value,
            "details": self.details,
        }


@dataclass(frozen=True)
class DiagnosisResult:
    rule_id: str
    status: DiagnosisStatus
    severity: str
    reason: str
    evidence: list[dict[str, Any]] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    confidence: float | None = None
    missing_inputs: list[str] = field(default_factory=list)
    blocked_by_rule_ids: list[str] = field(default_factory=list)
    rule_version: str = "1.0.0"
    profile_version: str = "mvp-default-1.0.0"

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_version": self.rule_version,
            "profile_version": self.profile_version,
            "status": self.status,
            "severity": self.severity,
            "confidence": self.confidence,
            "reason": self.reason,
            "evidence": self.evidence,
            "missing_inputs": self.missing_inputs,
            "blocked_by_rule_ids": self.blocked_by_rule_ids,
            "suggestions": self.suggestions,
        }


@dataclass(frozen=True)
class RankedItem:
    rank: int
    key: str
    doc_id: str
    chunk_id: str
    relevant_ids: frozenset[str]
    relevance_grade: int
    rank_before: int | None = None
    usefulness: bool | None = None

    @property
    def relevant(self) -> bool:
        return bool(self.relevant_ids) or self.relevance_grade > 0


@dataclass(frozen=True)
class CitationJudgement:
    citation_id: str
    chunk_id: str
    resolves: bool
    supports_claim: bool


@dataclass(frozen=True)
class EvaluationFeatures:
    sample_id: str
    answer: str | None
    reference_answer: str | None
    answerable: bool
    gold_ids: frozenset[str]
    relevance_unit: str | None
    ranked_items: tuple[RankedItem, ...]
    relevance_available: bool
    citations: tuple[CitationJudgement, ...]
