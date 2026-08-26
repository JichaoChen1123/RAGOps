from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    partial_failed = "partial_failed"
    failed = "failed"
    cancelled = "cancelled"


class MetricConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    version: str = Field(min_length=1, max_length=40)
    parameters: dict[str, Any] = Field(default_factory=dict)


class EvaluationJobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str = Field(min_length=1)
    config_version: str = Field(min_length=1, max_length=120, examples=["rag-config-demo-v1"])
    metrics: list[MetricConfig] = Field(default_factory=list)

    @field_validator("config_version")
    @classmethod
    def non_blank_config_version(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("config_version must not be blank")
        return stripped


class EvaluationJobResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "01912345-6789-7abc-8def-0123456789ab",
                    "dataset_id": "01912345-6789-7abc-8def-0123456789ac",
                    "status": "queued",
                    "config_version": "rag-config-demo-v1",
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
    status: JobStatus
    config_version: str
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
                    "status": "succeeded",
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
                    },
                }
            ]
        }
    )

    id: str
    job_id: str
    status: JobStatus
    generated_at: datetime
    summary: dict[str, int]
    metrics: list[dict[str, Any]]
    links: dict[str, str]
