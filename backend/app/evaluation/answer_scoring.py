"""Versioned, offline-only answer scoring used by normal evaluation and rescoring."""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Sequence

from app.evaluation.contracts import MetricResult

ALGORITHM_VERSION = "answer-score-v1"
_PROSE_PUNCTUATION = re.compile(r"[\"'“”‘’()\[\]{}，、；：！!？?。.]" )
_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9]*|[+-]?\d+(?:[,.]\d+)*(?:%|[A-Za-z]+)?|[\u3400-\u9fff]")


def normalize_answer(value: str) -> str:
    """Normalize prose but preserve signs, numeric separators, percent and units."""
    value = unicodedata.normalize("NFKC", value).casefold()
    # A comma/dot between digits is numeric syntax; all other punctuation is prose.
    value = re.sub(r"(?<!\d)[,.]|[,.](?!\d)", " ", value)
    value = _PROSE_PUNCTUATION.sub(" ", value)
    return " ".join(value.split())


def answer_tokens(value: str) -> list[str]:
    return _TOKEN.findall(normalize_answer(value))


def _references(references: str | Sequence[str] | None) -> list[str]:
    if references is None:
        return []
    return [references] if isinstance(references, str) else list(references)


def references_from_sample(sample: object) -> list[str]:
    """One authoritative compatibility path for normal evaluation and rescoring."""
    metadata = getattr(sample, "metadata_json", {}) or {}
    listed = metadata.get("reference_answers") if isinstance(metadata, dict) else None
    if isinstance(listed, list) and all(isinstance(item, str) for item in listed):
        return list(listed)
    reference = getattr(sample, "reference_answer", None)
    return [] if reference is None else [reference]


def _aggregate(answer: str | None, references: str | Sequence[str] | None, name: str, score) -> MetricResult:
    refs = _references(references)
    if not refs:
        return MetricResult(name, None, status="not_applicable", metric_version=ALGORITHM_VERSION,
                            details={"reason": "reference answer set is empty", "algorithm_version": ALGORITHM_VERSION})
    if answer is None:
        return MetricResult(name, None, status="not_applicable", metric_version=ALGORITHM_VERSION,
                            details={"reason": "answer is unavailable", "algorithm_version": ALGORITHM_VERSION})
    values = [score(answer, ref) for ref in refs]
    hit = max(range(len(values)), key=values.__getitem__)
    return MetricResult(name, values[hit], metric_version=ALGORITHM_VERSION,
                        details={"algorithm_version": ALGORITHM_VERSION, "matched_reference_index": hit,
                                 "reference_count": len(refs)})


def strict_em(answer: str | None, references: str | Sequence[str] | None) -> MetricResult:
    return _aggregate(answer, references, "strict_em", lambda a, b: float(a == b))


def normalized_em(answer: str | None, references: str | Sequence[str] | None) -> MetricResult:
    return _aggregate(answer, references, "normalized_em", lambda a, b: float(normalize_answer(a) == normalize_answer(b)))


def chinese_answer_f1(answer: str | None, references: str | Sequence[str] | None) -> MetricResult:
    def score(a: str, b: str) -> float:
        aa, bb = answer_tokens(a), answer_tokens(b)
        if not aa and not bb:
            return 1.0
        if not aa or not bb:
            return 0.0
        common = sum((Counter(aa) & Counter(bb)).values())
        precision, recall = common / len(aa), common / len(bb)
        return 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return _aggregate(answer, references, "chinese_answer_f1", score)


def answer_score_results(answer: str | None, references: str | Sequence[str] | None) -> list[MetricResult]:
    return [strict_em(answer, references), normalized_em(answer, references), chinese_answer_f1(answer, references)]
