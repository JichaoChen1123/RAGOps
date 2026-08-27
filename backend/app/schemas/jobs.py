from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class JobOutcome(str, Enum):
    succeeded = "succeeded"
    partial_failed = "partial_failed"
    failed = "failed"


class ReviewStatus(str, Enum):
    pending = "pending"
    confirmed = "confirmed"
    dismissed = "dismissed"


class MetricConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    version: str = Field(min_length=1, max_length=40)
    parameters: dict[str, Any] = Field(default_factory=dict)


class EvaluationJobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str = Field(min_length=1)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    config_version: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
        examples=["rag-config-demo-v1"],
    )
    model_version: str = Field(default="deterministic-local", min_length=1, max_length=120)
    prompt_version: str = Field(default="prompt-v1", min_length=1, max_length=120)
    metrics: list[MetricConfig] = Field(default_factory=list)

    @field_validator("name", "config_version", "model_version", "prompt_version")
    @classmethod
    def non_blank_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped

    @property
    def resolved_config_version(self) -> str:
        return self.config_version or f"{self.model_version}:{self.prompt_version}"


class EvaluationJobResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "01912345-6789-7abc-8def-0123456789ab",
                    "dataset_id": "01912345-6789-7abc-8def-0123456789ac",
                    "name": "Support regression v1",
                    "status": "queued",
                    "outcome": None,
                    "config_version": "rag-config-demo-v1",
                    "model_version": "deterministic-local",
                    "prompt_version": "prompt-v1",
                    "metric_config": [],
                    "total_count": 6,
                    "queued_count": 6,
                    "running_count": 0,
                    "succeeded_count": 0,
                    "failed_count": 0,
                    "progress": 0.0,
                    "failure_code": None,
                    "failure_message": None,
                    "created_at": "2026-08-26T12:00:00Z",
                    "started_at": None,
                    "finished_at": None,
                    "links": {
                        "self": "/api/v1/evaluation-jobs/01912345-6789-7abc-8def-0123456789ab",
                        "samples": "/api/v1/evaluation-jobs/01912345-6789-7abc-8def-0123456789ab/samples",
                        "report": "/api/v1/evaluation-jobs/01912345-6789-7abc-8def-0123456789ab/report",
                    },
                }
            ]
        }
    )

    id: str
    dataset_id: str
    name: str
    status: JobStatus
    outcome: JobOutcome | None
    config_version: str
    model_version: str
    prompt_version: str
    metric_config: list[dict[str, Any]]
    total_count: int
    queued_count: int
    running_count: int
    succeeded_count: int
    failed_count: int
    progress: float
    failure_code: str | None
    failure_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    links: dict[str, str]


class EvaluationJobListResponse(BaseModel):
    items: list[EvaluationJobResponse]
    total: int


class EvaluationSampleResponse(BaseModel):
    id: str
    sample_id: str
    question: str
    status: str
    answer: str | None
    retrieval_results: list[dict[str, Any]]
    metric_results: list[dict[str, Any]]
    diagnoses: list[dict[str, Any]]
    review_status: ReviewStatus
    reviewed_at: datetime | None
    latency_ms: int | None
    failure_code: str | None
    failure_message: str | None


class EvaluationSampleListResponse(BaseModel):
    items: list[EvaluationSampleResponse]
    total: int


class EvaluationReportResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "01912345-6789-7abc-8def-0123456789ad",
                    "job_id": "01912345-6789-7abc-8def-0123456789ab",
                    "status": "completed",
                    "outcome": "succeeded",
                    "generated_at": "2026-08-26T12:00:01Z",
                    "summary": {"total_count": 6, "succeeded_count": 6, "failed_count": 0},
                    "metrics": [
                        {
                            "metric_name": "execution_success_rate",
                            "metric_version": "1.0.0",
                            "status": "ok",
                            "value": 1.0,
                        }
                    ],
                    "links": {
                        "job": "/api/v1/evaluation-jobs/01912345-6789-7abc-8def-0123456789ab",
                        "samples": "/api/v1/evaluation-jobs/01912345-6789-7abc-8def-0123456789ab/samples",
                        "export": "/api/v1/evaluation-jobs/01912345-6789-7abc-8def-0123456789ab/report/export",
                    },
                }
            ]
        }
    )

    id: str
    job_id: str
    status: JobStatus
    outcome: JobOutcome
    generated_at: datetime
    summary: dict[str, int]
    metrics: list[dict[str, Any]]
    links: dict[str, str]


class SampleReviewUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_status: ReviewStatus


class ReportExportResponse(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    exported_at: datetime
    report: EvaluationReportResponse
    samples: list[EvaluationSampleResponse]
