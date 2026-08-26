from __future__ import annotations

import hashlib
import json
import logging

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.errors import DomainError
from app.evaluation.aggregation import aggregate_metric_results
from app.execution.contracts import EvaluationExecutor
from app.execution.deterministic import DeterministicExecutor
from app.persistence.db import Database
from app.persistence.models import (
    Dataset,
    DatasetSample,
    EvaluationJob,
    EvaluationJobSample,
    EvaluationReport,
    utc_now,
)
from app.schemas.jobs import (
    EvaluationJobCreate,
    EvaluationJobResponse,
    EvaluationReportResponse,
    EvaluationSampleResponse,
)

logger = logging.getLogger(__name__)

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "queued": {"running", "failed", "cancelled"},
    "running": {"succeeded", "partial_failed", "failed", "cancelled"},
    "succeeded": set(),
    "partial_failed": set(),
    "failed": set(),
    "cancelled": set(),
}


def _fingerprint(payload: EvaluationJobCreate) -> str:
    canonical = json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def transition_job(job: EvaluationJob, target: str) -> None:
    if target not in ALLOWED_TRANSITIONS.get(job.status, set()):
        raise DomainError(
            "INVALID_JOB_TRANSITION",
            f"Evaluation job cannot transition from {job.status} to {target}.",
            status_code=status.HTTP_409_CONFLICT,
            details={"from_status": job.status, "to_status": target},
        )
    job.status = target


def derive_terminal_status(*, total: int, succeeded: int, failed: int) -> str:
    if total <= 0 or succeeded + failed != total:
        raise ValueError("all samples must be terminal before deriving job status")
    if succeeded == total:
        return "succeeded"
    if failed == total:
        return "failed"
    return "partial_failed"


def create_job(
    session: Session,
    payload: EvaluationJobCreate,
    *,
    idempotency_key: str | None,
) -> tuple[EvaluationJob, bool]:
    fingerprint = _fingerprint(payload)
    if idempotency_key:
        existing = session.scalar(
            select(EvaluationJob).where(EvaluationJob.idempotency_key == idempotency_key)
        )
        if existing is not None:
            if existing.request_fingerprint != fingerprint:
                raise DomainError(
                    "IDEMPOTENCY_KEY_CONFLICT",
                    "Idempotency-Key was already used with a different request.",
                    status_code=status.HTTP_409_CONFLICT,
                    details={"idempotency_key": idempotency_key},
                )
            return existing, False

    dataset = session.get(Dataset, payload.dataset_id)
    if dataset is None:
        raise DomainError(
            "RESOURCE_NOT_FOUND",
            "Dataset not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"dataset_id": payload.dataset_id},
        )
    if dataset.status != "published":
        raise DomainError(
            "DATASET_VERSION_NOT_PUBLISHED",
            "Dataset must be published before evaluation.",
            status_code=status.HTTP_409_CONFLICT,
            details={"dataset_id": dataset.id},
        )

    samples = list(
        session.scalars(
            select(DatasetSample)
            .where(DatasetSample.dataset_id == dataset.id)
            .order_by(DatasetSample.ordinal)
        )
    )
    job = EvaluationJob(
        dataset_id=dataset.id,
        status="queued",
        config_version=payload.config_version,
        metric_config=[metric.model_dump(mode="json") for metric in payload.metrics],
        total_count=len(samples),
        queued_count=len(samples),
        request_fingerprint=fingerprint,
        idempotency_key=idempotency_key,
    )
    session.add(job)
    session.flush()
    session.add_all(
        [EvaluationJobSample(job_id=job.id, sample_id=sample.id, status="queued") for sample in samples]
    )
    session.commit()
    logger.info(
        "job.created",
        extra={"event": "job.created", "job_id": job.id, "dataset_id": dataset.id},
    )
    return job, True


def get_job(session: Session, job_id: str) -> EvaluationJob:
    job = session.get(EvaluationJob, job_id)
    if job is None:
        raise DomainError(
            "RESOURCE_NOT_FOUND",
            "Evaluation job not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"job_id": job_id},
        )
    return job


def list_jobs(session: Session) -> list[EvaluationJob]:
    return list(session.scalars(select(EvaluationJob).order_by(EvaluationJob.created_at.desc())))


def job_to_response(job: EvaluationJob) -> EvaluationJobResponse:
    base = f"/api/v1/evaluation-jobs/{job.id}"
    return EvaluationJobResponse(
        id=job.id,
        dataset_id=job.dataset_id,
        status=job.status,
        config_version=job.config_version,
        metric_config=job.metric_config,
        total_count=job.total_count,
        queued_count=job.queued_count,
        running_count=job.running_count,
        succeeded_count=job.succeeded_count,
        failed_count=job.failed_count,
        progress=job.progress,
        failure_code=job.failure_code,
        failure_message=job.failure_message,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        links={"self": base, "samples": f"{base}/samples", "report": f"{base}/report"},
    )


def execute_job(
    database: Database,
    job_id: str,
    executor: EvaluationExecutor | None = None,
) -> None:
    runner = executor
    with database.session() as session:
        job = get_job(session, job_id)
        if job.status != "queued":
            return
        if runner is None:
            runner = DeterministicExecutor.from_metric_config(job.metric_config)
        transition_job(job, "running")
        job.started_at = utc_now()
        job.running_count = job.total_count
        job.queued_count = 0
        result_ids = list(
            session.scalars(
                select(EvaluationJobSample.id)
                .where(EvaluationJobSample.job_id == job_id)
                .order_by(EvaluationJobSample.created_at)
            )
        )
        session.commit()

    for result_id in result_ids:
        _execute_sample(database, result_id, runner)

    with database.session() as session:
        job = get_job(session, job_id)
        terminal_status = derive_terminal_status(
            total=job.total_count,
            succeeded=job.succeeded_count,
            failed=job.failed_count,
        )
        transition_job(job, terminal_status)
        job.finished_at = utc_now()
        job.progress = 1.0
        if terminal_status in {"succeeded", "partial_failed"}:
            sample_metric_results = list(
                session.scalars(
                    select(EvaluationJobSample.metric_results)
                    .where(EvaluationJobSample.job_id == job.id)
                    .order_by(EvaluationJobSample.created_at)
                )
            )
            report = EvaluationReport(
                job_id=job.id,
                status=terminal_status,
                total_count=job.total_count,
                succeeded_count=job.succeeded_count,
                failed_count=job.failed_count,
                metrics=aggregate_metric_results(
                    sample_metric_results,
                    total_count=job.total_count,
                    succeeded_count=job.succeeded_count,
                ),
            )
            session.add(report)
        else:
            job.failure_code = job.failure_code or "ALL_SAMPLES_FAILED"
            job.failure_message = job.failure_message or "All deterministic sample executions failed."
        session.commit()
        logger.info(
            "job.transitioned",
            extra={"event": "job.transitioned", "job_id": job.id, "status": terminal_status},
        )


def _execute_sample(
    database: Database,
    result_id: str,
    executor: EvaluationExecutor,
) -> None:
    with database.session() as session:
        result = session.scalar(
            select(EvaluationJobSample)
            .options(joinedload(EvaluationJobSample.sample))
            .where(EvaluationJobSample.id == result_id)
        )
        if result is None or result.status != "queued":
            return
        result.status = "running"
        result.started_at = utc_now()
        session.commit()

        try:
            output = executor.evaluate(result.sample)
            result.answer = output.answer
            result.retrieval_results = output.retrieval_results
            result.metric_results = output.metric_results
            result.diagnoses = output.diagnoses
            result.latency_ms = output.latency_ms
            result.status = "succeeded"
            result.job.succeeded_count += 1
        except Exception as exc:
            logger.exception(
                "sample.execution.failed",
                extra={"event": "sample.execution.failed", "job_id": result.job_id, "sample_id": result.sample_id},
            )
            result.status = "failed"
            result.failure_code = "EXECUTOR_ERROR"
            result.failure_message = str(exc)[:500]
            result.job.failed_count += 1
        result.job.running_count -= 1
        terminal_count = result.job.succeeded_count + result.job.failed_count
        result.job.progress = terminal_count / result.job.total_count
        result.finished_at = utc_now()
        session.commit()


def list_job_samples(session: Session, job_id: str) -> list[EvaluationSampleResponse]:
    get_job(session, job_id)
    rows = list(
        session.scalars(
            select(EvaluationJobSample)
            .options(joinedload(EvaluationJobSample.sample))
            .where(EvaluationJobSample.job_id == job_id)
            .order_by(EvaluationJobSample.created_at)
        )
    )
    return [
        EvaluationSampleResponse(
            id=row.id,
            sample_id=row.sample.external_id,
            question=row.sample.question,
            status=row.status,
            answer=row.answer,
            retrieval_results=row.retrieval_results,
            metric_results=row.metric_results,
            diagnoses=row.diagnoses,
            latency_ms=row.latency_ms,
            failure_code=row.failure_code,
            failure_message=row.failure_message,
        )
        for row in rows
    ]


def get_report(session: Session, job_id: str) -> EvaluationReportResponse:
    job = get_job(session, job_id)
    report = session.scalar(select(EvaluationReport).where(EvaluationReport.job_id == job_id))
    if report is None:
        raise DomainError(
            "REPORT_NOT_READY",
            "The report is not available until the job has usable terminal results.",
            status_code=status.HTTP_409_CONFLICT,
            details={"job_id": job_id, "job_status": job.status},
            retryable=job.status in {"queued", "running"},
        )
    return EvaluationReportResponse(
        id=report.id,
        job_id=report.job_id,
        status=report.status,
        generated_at=report.generated_at,
        summary={
            "total_count": report.total_count,
            "succeeded_count": report.succeeded_count,
            "failed_count": report.failed_count,
        },
        metrics=report.metrics,
        links={
            "job": f"/api/v1/evaluation-jobs/{job_id}",
            "samples": f"/api/v1/evaluation-jobs/{job_id}/samples",
        },
    )
