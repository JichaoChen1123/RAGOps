from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_database, get_runtime_settings, get_session
from app.core.config import Settings
from app.persistence.db import Database
from app.schemas.jobs import (
    EvaluationJobCreate,
    EvaluationJobListResponse,
    EvaluationJobResponse,
    EvaluationReportResponse,
    EvaluationSampleResponse,
    EvaluationSampleListResponse,
    ReportExportResponse,
    SampleReviewUpdate,
)
from app.services import jobs as service

router = APIRouter()
SessionDep = Annotated[Session, Depends(get_session)]
DatabaseDep = Annotated[Database, Depends(get_database)]
SettingsDep = Annotated[Settings, Depends(get_runtime_settings)]


@router.post(
    "",
    response_model=EvaluationJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create and enqueue an evaluation job",
)
def create_evaluation_job(
    payload: EvaluationJobCreate,
    background_tasks: BackgroundTasks,
    session: SessionDep,
    database: DatabaseDep,
    settings: SettingsDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=128)] = None,
) -> EvaluationJobResponse:
    job, created = service.create_job(
        session,
        payload,
        idempotency_key=idempotency_key,
        settings=settings,
    )
    response = service.job_to_response(job)
    if created:
        background_tasks.add_task(service.execute_job, database, job.id, settings)
    return response


@router.get("", response_model=EvaluationJobListResponse, summary="List evaluation jobs")
def list_evaluation_jobs(session: SessionDep) -> EvaluationJobListResponse:
    jobs = service.list_jobs(session)
    return EvaluationJobListResponse(
        items=[service.job_to_response(job) for job in jobs],
        total=len(jobs),
    )


@router.get(
    "/{job_id}",
    response_model=EvaluationJobResponse,
    summary="Get evaluation status and counts",
)
def get_evaluation_job(job_id: str, session: SessionDep) -> EvaluationJobResponse:
    return service.job_to_response(service.get_job(session, job_id))


@router.get(
    "/{job_id}/samples",
    response_model=EvaluationSampleListResponse,
    summary="List persisted sample results",
)
def list_evaluation_samples(job_id: str, session: SessionDep) -> EvaluationSampleListResponse:
    items = service.list_job_samples(session, job_id)
    return EvaluationSampleListResponse(items=items, total=len(items))


@router.patch(
    "/{job_id}/samples/{sample_id}/review",
    response_model=EvaluationSampleResponse,
    summary="Update a sample diagnosis review status",
)
def update_sample_review(
    job_id: str,
    sample_id: str,
    payload: SampleReviewUpdate,
    session: SessionDep,
) -> EvaluationSampleResponse:
    return service.update_sample_review(session, job_id, sample_id, payload)


@router.get(
    "/{job_id}/report",
    response_model=EvaluationReportResponse,
    summary="Read the immutable evaluation report",
)
def get_evaluation_report(job_id: str, session: SessionDep) -> EvaluationReportResponse:
    return service.get_report(session, job_id)


@router.get(
    "/{job_id}/report/export",
    response_model=ReportExportResponse,
    summary="Export a report and its sample summaries as JSON data",
)
def export_evaluation_report(job_id: str, session: SessionDep) -> ReportExportResponse:
    return service.export_report(session, job_id)
