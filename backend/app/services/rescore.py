"""Offline append-only answer rescoring. This module intentionally has no model imports."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.ids import uuid7_str
from app.evaluation.answer_scoring import ALGORITHM_VERSION, answer_score_results
from app.persistence.models import AnswerRescore, EvaluationJobSample


@dataclass
class RescoreSummary:
    batch_id: str
    selected: int = 0
    succeeded: int = 0
    skipped: int = 0
    failed: int = 0
    failures: list[dict[str, str]] = field(default_factory=list)


def _references(row: EvaluationJobSample) -> list[str]:
    metadata: dict[str, Any] = row.sample.metadata_json or {}
    listed = metadata.get("reference_answers")
    if isinstance(listed, list) and all(isinstance(item, str) for item in listed):
        return list(listed)
    return [] if row.sample.reference_answer is None else [row.sample.reference_answer]


def rescore_job(session: Session, job_id: str, *, dry_run: bool = False) -> RescoreSummary:
    batch_id = uuid7_str()
    rows = list(session.scalars(select(EvaluationJobSample).options(joinedload(EvaluationJobSample.sample)).where(EvaluationJobSample.job_id == job_id)))
    summary = RescoreSummary(batch_id=batch_id, selected=len(rows))
    for row in rows:
        if row.answer is None:
            summary.skipped += 1
            summary.failures.append({"job_sample_id": row.id, "reason": "stored model answer is unavailable"})
            continue
        references = _references(row)
        if not references:
            summary.skipped += 1
            summary.failures.append({"job_sample_id": row.id, "reason": "reference answer set is empty"})
            continue
        try:
            metrics = [metric.as_dict() for metric in answer_score_results(row.answer, references)]
            if not dry_run:
                session.add(AnswerRescore(batch_id=batch_id, job_id=row.job_id, job_sample_id=row.id,
                    sample_id=row.sample_id, algorithm_version=ALGORITHM_VERSION, source_answer=row.answer,
                    reference_answers=references, metric_results=metrics, status="calculated"))
            summary.succeeded += 1
        except Exception as exc:  # Persist per-row failure without aborting a batch.
            summary.failed += 1
            summary.failures.append({"job_sample_id": row.id, "reason": str(exc)})
            if not dry_run:
                session.add(AnswerRescore(batch_id=batch_id, job_id=row.job_id, job_sample_id=row.id,
                    sample_id=row.sample_id, algorithm_version=ALGORITHM_VERSION, source_answer=row.answer,
                    reference_answers=references, metric_results=[], status="failed", failure_reason=str(exc)))
    if not dry_run:
        session.commit()
    return summary
