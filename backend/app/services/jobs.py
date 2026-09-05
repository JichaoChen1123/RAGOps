from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from typing import Any

from fastapi import status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.config import Settings, get_settings
from app.core.errors import DomainError
from app.core.ids import uuid7_str
from app.evaluation.aggregation import aggregate_metric_results
from app.execution.adapters import DefaultModelAdapterFactory
from app.execution.contracts import SnapshotExecutor
from app.execution.executor import ModelEvaluationExecutor
from app.execution.model import ModelError, ModelErrorCode
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
    QualityGate,
    ReportExportResponse,
    SampleReviewUpdate,
)

logger = logging.getLogger(__name__)

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "queued": {"running", "failed", "cancelled"},
    "running": {"completed", "failed", "cancelled"},
    "completed": set(),
    "failed": set(),
    "cancelled": set(),
}


def _canonical_hash(value: object) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _fingerprint(payload: EvaluationJobCreate) -> str:
    return _canonical_hash(payload.model_dump(mode="json"))


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
    return "failed" if failed == total else "completed"


def derive_job_outcome(*, total: int, succeeded: int, failed: int) -> str:
    terminal_status = derive_terminal_status(total=total, succeeded=succeeded, failed=failed)
    if terminal_status == "failed":
        return "failed"
    return "partial_failed" if failed else "succeeded"


def create_job(
    session: Session,
    payload: EvaluationJobCreate,
    *,
    idempotency_key: str | None,
    settings: Settings | None = None,
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

    execution = payload.resolved_execution
    if execution.context_policy == "retrieval":
        raise DomainError(
            "EXECUTION_MODE_UNAVAILABLE",
            "Retrieval execution is not implemented in this offline stage.",
            status_code=status.HTTP_409_CONFLICT,
        )
    resolved_settings = settings or get_settings()
    _validate_adapter(execution.adapter_id, resolved_settings)
    if execution.adapter_id == "mock" and execution.generation.model != "mock-ragops-v1":
        raise DomainError(
            "PROVIDER_CAPABILITY_UNSUPPORTED",
            "The selected provider does not support this request.",
            status_code=422,
        )

    samples = list(
        session.scalars(
            select(DatasetSample)
            .where(DatasetSample.dataset_id == dataset.id)
            .order_by(DatasetSample.ordinal)
        )
    )
    created_at = utc_now()
    metric_config = [metric.model_dump(mode="json") for metric in payload.metrics]
    snapshot: dict[str, Any] = {
        "contract_version": "2.0",
        "adapter_id": execution.adapter_id,
        "provider_id": (
            "openai_compatible" if execution.adapter_id == "openai_compatible" else None
        ),
        "prompt": execution.prompt.model_dump(mode="json"),
        "generation": execution.generation.model_dump(mode="json"),
        "context_policy": execution.context_policy,
        "dataset": {
            "id": dataset.id,
            "version": dataset.version,
            "schema_version": dataset.schema_version,
            "content_sha256": dataset.content_sha256,
        },
        "metric_config": metric_config,
        "quality_gate": (
            payload.quality_gate.model_dump(mode="json") if payload.quality_gate else None
        ),
        "external_calls_enabled_at_creation": resolved_settings.model_external_calls_enabled,
        "created_at": created_at.isoformat().replace("+00:00", "Z"),
    }
    snapshot["config_version"] = _canonical_hash(snapshot)

    legacy_model_label = payload.legacy_model_label
    compatibility_config_version = (
        payload.config_version
        or f"{legacy_model_label}:{execution.prompt.version}"
        if payload.is_legacy_request
        else snapshot["config_version"]
    )
    job = EvaluationJob(
        dataset_id=dataset.id,
        name=payload.name or f"{dataset.name} evaluation",
        status="queued",
        config_version=compatibility_config_version,
        model_version=legacy_model_label or execution.generation.model,
        prompt_version=execution.prompt.version,
        metric_config=metric_config,
        total_count=len(samples),
        queued_count=len(samples),
        request_fingerprint=fingerprint,
        idempotency_key=idempotency_key,
        contract_version="2.0",
        adapter_id=execution.adapter_id,
        execution_snapshot=snapshot,
        quality_status="not_evaluated",
        quality_verdict="unknown",
        quality_score=None,
        created_at=created_at,
    )
    session.add(job)
    session.flush()
    queued_rows = []
    for sample in samples:
        run_id = uuid7_str()
        contexts = (
            list(sample.retrieved_contexts or [])
            if execution.context_policy == "dataset_contexts"
            else []
        )
        queued_rows.append(
            EvaluationJobSample(
                job_id=job.id,
                sample_id=sample.id,
                status="queued",
                run_id=run_id,
                quality_status="not_evaluated",
                run_snapshot={
                    "run_id": run_id,
                    "status": "queued",
                    "adapter_id": execution.adapter_id,
                    "provider_id": snapshot["provider_id"],
                    "requested_model": execution.generation.model,
                    "actual_model": None,
                    "is_mock": True if execution.adapter_id == "mock" else None,
                    "finish_reason": None,
                    "answer": None,
                    "contexts": contexts,
                    "citations": [],
                    "latency_ms": None,
                    "usage": None,
                    "cost": None,
                    "provider_request_id": None,
                    "attempt_count": 0,
                    "attempts": [],
                    "error": None,
                    "started_at": None,
                    "finished_at": None,
                },
            )
        )
    session.add_all(queued_rows)
    session.commit()
    logger.info(
        "job.created",
        extra={"event": "job.created", "job_id": job.id, "dataset_id": dataset.id},
    )
    return job, True


def _validate_adapter(adapter_id: str, settings: Settings) -> None:
    try:
        DefaultModelAdapterFactory(settings).create(adapter_id)
    except ModelError as exc:
        raise _model_domain_error(exc) from None


def _model_domain_error(error: ModelError) -> DomainError:
    status_by_code = {
        ModelErrorCode.adapter_not_found: 422,
        ModelErrorCode.capability_unsupported: 422,
        ModelErrorCode.not_configured: status.HTTP_409_CONFLICT,
        ModelErrorCode.external_calls_disabled: status.HTTP_403_FORBIDDEN,
    }
    return DomainError(
        error.code.value,
        error.message,
        status_code=status_by_code.get(error.code, status.HTTP_502_BAD_GATEWAY),
        retryable=error.retryable,
    )


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
        name=job.name,
        status=job.status,
        outcome=job.outcome,
        execution_snapshot=job.execution_snapshot,
        quality_status=job.quality_status,
        quality_verdict=job.quality_verdict,
        quality_score=job.quality_score,
        config_version=job.config_version,
        model_version=job.model_version,
        prompt_version=job.prompt_version,
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
    settings: Settings | None = None,
    *,
    adapter_factory: DefaultModelAdapterFactory | None = None,
    executor_factory: Callable[[dict[str, Any]], SnapshotExecutor] | None = None,
) -> None:
    resolved_settings = settings or get_settings()
    with database.session() as session:
        job = get_job(session, job_id)
        if job.status != "queued":
            return
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
        snapshot = dict(job.execution_snapshot or {})
        legacy_metric_compat = job.model_version != snapshot.get("generation", {}).get("model")
        session.commit()

    runner: SnapshotExecutor | None = None
    setup_error: ModelError | None = None
    try:
        if executor_factory is not None:
            runner = executor_factory(snapshot)
        else:
            factory = adapter_factory or DefaultModelAdapterFactory(resolved_settings)
            adapter = factory.create(str(snapshot["adapter_id"]))
            runner = ModelEvaluationExecutor(
                adapter,
                snapshot,
                legacy_metric_compat=legacy_metric_compat,
            )
    except ModelError as exc:
        setup_error = exc

    for result_id in result_ids:
        if runner is not None:
            _execute_sample(database, result_id, runner)
        else:
            assert setup_error is not None
            _fail_sample_without_runner(database, result_id, snapshot, setup_error)

    _finish_job(database, job_id, legacy_metric_compat=legacy_metric_compat)


def _execute_sample(database: Database, result_id: str, executor: SnapshotExecutor) -> None:
    with database.session() as session:
        result = session.scalar(
            select(EvaluationJobSample)
            .options(
                joinedload(EvaluationJobSample.sample),
                joinedload(EvaluationJobSample.job),
            )
            .where(EvaluationJobSample.id == result_id)
        )
        if result is None or result.status != "queued":
            return
        result.status = "running"
        result.started_at = utc_now()
        result.run_snapshot = _initial_run_snapshot(result, executor)
        session.commit()

        try:
            generated = executor.generate(result.sample)
            response = generated.response
            result.answer = response.answer
            result.retrieval_results = generated.contexts
            result.latency_ms = response.latency_ms
            result.run_snapshot = {
                **(result.run_snapshot or {}),
                "actual_model": response.actual_model,
                "is_mock": response.is_mock,
                "finish_reason": response.finish_reason,
                "answer": response.answer,
                "contexts": generated.contexts,
                "citations": generated.citations,
                "latency_ms": response.latency_ms,
                "usage": response.usage.model_dump(mode="json") if response.usage else None,
                "cost": None,
                "provider_request_id": response.provider_request_id,
                "attempt_count": len(generated.attempts),
                "attempts": generated.attempts,
                "error": None,
            }
            session.commit()

            evaluated = executor.evaluate_generated(result.sample, generated)
            result.metric_results = evaluated.metric_results
            result.diagnoses = evaluated.diagnoses
            result.quality_status = _sample_quality_status(
                evaluated.metric_results,
                result.job.execution_snapshot.get("quality_gate")
                if result.job.execution_snapshot
                else None,
            )
            result.status = "succeeded"
            result.finished_at = utc_now()
            result.run_snapshot = {
                **(result.run_snapshot or {}),
                "status": "succeeded",
                "finished_at": _timestamp(result.finished_at),
            }
            result.job.succeeded_count += 1
        except ModelError as exc:
            _record_model_failure(result, executor, exc)
        except Exception:
            logger.error(
                "sample.execution.failed",
                extra={
                    "event": "sample.execution.failed",
                    "job_id": result.job_id,
                    "sample_id": result.sample_id,
                    "failure_code": "EXECUTOR_ERROR",
                },
            )
            _record_safe_failure(
                result,
                code="EXECUTOR_ERROR",
                message="The sample execution could not be completed.",
                attempts=[],
            )
        result.job.running_count -= 1
        terminal_count = result.job.succeeded_count + result.job.failed_count
        result.job.progress = terminal_count / result.job.total_count
        session.commit()


def _initial_run_snapshot(
    result: EvaluationJobSample,
    executor: SnapshotExecutor,
) -> dict[str, Any]:
    generation = result.job.execution_snapshot.get("generation", {})
    return {
        **(result.run_snapshot or {}),
        "run_id": result.run_id,
        "status": "running",
        "adapter_id": executor.adapter_id,
        "provider_id": executor.provider_id,
        "requested_model": generation.get("model"),
        "actual_model": None,
        "is_mock": (result.run_snapshot or {}).get("is_mock"),
        "finish_reason": None,
        "answer": None,
        "contexts": (result.run_snapshot or {}).get("contexts", []),
        "citations": [],
        "latency_ms": None,
        "usage": None,
        "cost": None,
        "provider_request_id": None,
        "attempt_count": 0,
        "attempts": [],
        "error": None,
        "started_at": _timestamp(result.started_at),
        "finished_at": None,
    }


def _record_model_failure(
    result: EvaluationJobSample,
    executor: SnapshotExecutor,
    error: ModelError,
) -> None:
    attempts = []
    adapter = getattr(executor, "adapter", None)
    if adapter is not None:
        attempts = [item.model_dump(mode="json") for item in adapter.last_attempts]
    _record_safe_failure(
        result,
        code=error.code.value,
        message=error.message,
        attempts=attempts,
        error=error.as_dict(),
    )


def _record_safe_failure(
    result: EvaluationJobSample,
    *,
    code: str,
    message: str,
    attempts: list[dict[str, Any]],
    error: dict[str, object] | None = None,
) -> None:
    result.status = "failed"
    result.answer = None
    result.failure_code = code
    result.failure_message = message
    result.quality_status = "not_evaluated"
    result.finished_at = utc_now()
    result.run_snapshot = {
        **(result.run_snapshot or {}),
        "status": "failed",
        "answer": None,
        "attempt_count": len(attempts),
        "attempts": attempts,
        "error": error
        or {
            "code": code,
            "message": message,
            "retryable": False,
            "attempts": len(attempts),
            "provider_request_id": None,
            "retry_after_ms": None,
        },
        "finished_at": _timestamp(result.finished_at),
    }
    result.job.failed_count += 1


def _fail_sample_without_runner(
    database: Database,
    result_id: str,
    snapshot: dict[str, Any],
    error: ModelError,
) -> None:
    with database.session() as session:
        result = session.scalar(
            select(EvaluationJobSample)
            .options(joinedload(EvaluationJobSample.job))
            .where(EvaluationJobSample.id == result_id)
        )
        if result is None or result.status != "queued":
            return
        result.started_at = utc_now()
        result.run_snapshot = {
            "run_id": result.run_id,
            "status": "running",
            "adapter_id": snapshot.get("adapter_id"),
            "provider_id": snapshot.get("provider_id"),
            "requested_model": snapshot.get("generation", {}).get("model"),
            "actual_model": None,
            "is_mock": None,
            "finish_reason": None,
            "answer": None,
            "contexts": [],
            "citations": [],
            "latency_ms": None,
            "usage": None,
            "cost": None,
            "provider_request_id": None,
            "attempt_count": 0,
            "attempts": [],
            "error": None,
            "started_at": _timestamp(result.started_at),
            "finished_at": None,
        }
        _record_safe_failure(
            result,
            code=error.code.value,
            message=error.message,
            attempts=[],
            error=error.as_dict(),
        )
        result.job.running_count -= 1
        terminal_count = result.job.succeeded_count + result.job.failed_count
        result.job.progress = terminal_count / result.job.total_count
        session.commit()


def _finish_job(database: Database, job_id: str, *, legacy_metric_compat: bool) -> None:
    with database.session() as session:
        job = get_job(session, job_id)
        terminal_status = derive_terminal_status(
            total=job.total_count,
            succeeded=job.succeeded_count,
            failed=job.failed_count,
        )
        transition_job(job, terminal_status)
        job.outcome = derive_job_outcome(
            total=job.total_count,
            succeeded=job.succeeded_count,
            failed=job.failed_count,
        )
        job.finished_at = utc_now()
        job.progress = 1.0
        sample_rows = list(
            session.scalars(
                select(EvaluationJobSample)
                .where(EvaluationJobSample.job_id == job.id)
                .order_by(EvaluationJobSample.created_at)
            )
        )
        metrics = aggregate_metric_results(
            [row.metric_results for row in sample_rows],
            total_count=job.total_count,
            succeeded_count=job.succeeded_count,
            execution_metric_version="1.0.0" if legacy_metric_compat else "2.0.0",
        )
        quality_gate = None
        if job.execution_snapshot and job.execution_snapshot.get("quality_gate"):
            quality_gate = QualityGate.model_validate(job.execution_snapshot["quality_gate"])
        quality_status, quality_verdict, quality_score = _job_quality(metrics, quality_gate)
        job.quality_status = quality_status
        job.quality_verdict = quality_verdict
        job.quality_score = quality_score
        execution_summary = {
            "outcome": job.outcome,
            "total_count": job.total_count,
            "succeeded_count": job.succeeded_count,
            "failed_count": job.failed_count,
            "success_rate": job.succeeded_count / job.total_count if job.total_count else None,
        }
        quality_summary = {
            "status": quality_status,
            "verdict": quality_verdict,
            "score": quality_score,
            "evaluated_sample_count": sum(
                row.quality_status == "evaluated" for row in sample_rows
            ),
        }
        session.add(
            EvaluationReport(
                job_id=job.id,
                status=terminal_status,
                outcome=job.outcome,
                total_count=job.total_count,
                succeeded_count=job.succeeded_count,
                failed_count=job.failed_count,
                metrics=metrics,
                schema_version="2.0",
                execution_summary=execution_summary,
                quality_summary=quality_summary,
                execution_snapshot=job.execution_snapshot,
            )
        )
        if terminal_status == "failed":
            job.failure_code = "ALL_SAMPLES_FAILED"
            job.failure_message = "All sample executions failed. Inspect persisted run errors."
        session.commit()
        logger.info(
            "job.transitioned",
            extra={"event": "job.transitioned", "job_id": job.id, "status": terminal_status},
        )


def _sample_quality_status(
    metrics: list[dict[str, Any]],
    quality_gate: dict[str, Any] | None,
) -> str:
    if quality_gate is None:
        return "not_evaluated"
    by_name = {str(metric.get("metric_name")): metric for metric in metrics}
    statuses = [by_name.get(rule["metric_name"], {}).get("status") for rule in quality_gate["rules"]]
    if "error" in statuses:
        return "error"
    if any(value != "ok" for value in statuses):
        return "partial"
    return "evaluated"


def _job_quality(
    metrics: list[dict[str, Any]],
    quality_gate: QualityGate | None,
) -> tuple[str, str, float | None]:
    if quality_gate is None:
        return "not_evaluated", "unknown", None
    by_name = {str(metric.get("metric_name")): metric for metric in metrics}
    selected = [by_name.get(rule.metric_name) for rule in quality_gate.rules]
    if any(metric and metric.get("status") == "error" for metric in selected):
        return "error", "unknown", None
    if any(metric is None or metric.get("status") != "ok" for metric in selected):
        return "partial", "unknown", None
    passed = all(
        _compare(float(metric["value"]), rule.operator, rule.threshold)
        for metric, rule in zip(selected, quality_gate.rules, strict=True)
        if metric is not None
    )
    score = None
    if quality_gate.score_metric:
        metric = by_name.get(quality_gate.score_metric)
        value = metric.get("value") if metric and metric.get("status") == "ok" else None
        if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1:
            score = float(value) * 100
    return "evaluated", "passed" if passed else "failed", score


def _compare(value: float, operator: str, threshold: float) -> bool:
    operations = {
        "gte": lambda: value >= threshold,
        "gt": lambda: value > threshold,
        "lte": lambda: value <= threshold,
        "lt": lambda: value < threshold,
        "eq": lambda: value == threshold,
    }
    return operations[operator]()


def _sample_to_response(row: EvaluationJobSample) -> EvaluationSampleResponse:
    labels = {
        "reference_answer": row.sample.reference_answer,
        "gold_document_ids": row.sample.gold_document_ids,
        "gold_evidence_ids": row.sample.gold_evidence_ids,
        "expected_diagnoses": row.sample.expected_diagnoses,
    }
    return EvaluationSampleResponse(
        id=row.id,
        sample_id=row.sample.external_id,
        question=row.sample.question,
        labels=labels,
        reference_answer=row.sample.reference_answer,
        historical_answer=row.sample.historical_answer,
        run=row.run_snapshot,
        quality_status=row.quality_status,
        status=row.status,
        answer=row.answer,
        retrieval_results=row.retrieval_results,
        metric_results=row.metric_results,
        diagnoses=row.diagnoses,
        review_status=row.review_status,
        reviewed_at=row.reviewed_at,
        latency_ms=row.latency_ms,
        failure_code=row.failure_code,
        failure_message=row.failure_message,
    )


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
    return [_sample_to_response(row) for row in rows]


def update_sample_review(
    session: Session,
    job_id: str,
    sample_id: str,
    payload: SampleReviewUpdate,
) -> EvaluationSampleResponse:
    job = get_job(session, job_id)
    if job.status not in {"completed", "failed"}:
        raise DomainError(
            "REVIEW_NOT_AVAILABLE",
            "Sample review is only available after evaluation terminates.",
            status_code=status.HTTP_409_CONFLICT,
            details={"job_id": job_id, "job_status": job.status},
            retryable=job.status in {"queued", "running"},
        )
    row = session.scalar(
        select(EvaluationJobSample)
        .join(EvaluationJobSample.sample)
        .options(joinedload(EvaluationJobSample.sample))
        .where(
            EvaluationJobSample.job_id == job_id,
            or_(EvaluationJobSample.id == sample_id, DatasetSample.external_id == sample_id),
        )
    )
    if row is None:
        raise DomainError(
            "RESOURCE_NOT_FOUND",
            "Evaluation sample not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"job_id": job_id, "sample_id": sample_id},
        )
    row.review_status = payload.review_status.value
    row.reviewed_at = None if payload.review_status.value == "pending" else utc_now()
    session.commit()
    return _sample_to_response(row)


def get_report(session: Session, job_id: str) -> EvaluationReportResponse:
    job = get_job(session, job_id)
    report = session.scalar(select(EvaluationReport).where(EvaluationReport.job_id == job_id))
    if report is None:
        raise DomainError(
            "REPORT_NOT_READY",
            "The report is not available until the job reaches a terminal state.",
            status_code=status.HTTP_409_CONFLICT,
            details={"job_id": job_id, "job_status": job.status},
            retryable=job.status in {"queued", "running"},
        )
    execution_summary = report.execution_summary or {
        "outcome": report.outcome,
        "total_count": report.total_count,
        "succeeded_count": report.succeeded_count,
        "failed_count": report.failed_count,
        "success_rate": (
            report.succeeded_count / report.total_count if report.total_count else None
        ),
    }
    quality_summary = report.quality_summary or {
        "status": "legacy_unknown",
        "verdict": "unknown",
        "score": None,
        "evaluated_sample_count": 0,
    }
    return EvaluationReportResponse(
        schema_version=report.schema_version,
        id=report.id,
        job_id=report.job_id,
        status=report.status,
        outcome=report.outcome,
        generated_at=report.generated_at,
        execution_summary=execution_summary,
        quality_summary=quality_summary,
        execution_snapshot=report.execution_snapshot,
        summary={
            "total_count": report.total_count,
            "succeeded_count": report.succeeded_count,
            "failed_count": report.failed_count,
        },
        metrics=report.metrics,
        links={
            "job": f"/api/v1/evaluation-jobs/{job_id}",
            "samples": f"/api/v1/evaluation-jobs/{job_id}/samples",
            "export": f"/api/v1/evaluation-jobs/{job_id}/report/export",
        },
    )


def export_report(session: Session, job_id: str) -> ReportExportResponse:
    job = get_job(session, job_id)
    snapshot_model = (job.execution_snapshot or {}).get("generation", {}).get("model")
    export_version = "1.0" if job.model_version != snapshot_model else "2.0"
    return ReportExportResponse(
        schema_version=export_version,
        exported_at=utc_now(),
        report=get_report(session, job_id),
        samples=list_job_samples(session, job_id),
    )


def _timestamp(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")
