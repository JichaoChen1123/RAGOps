from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.execution.model import GenerationConfig


DEFAULT_PROMPT_TEXT = "Answer only from the provided context; state when evidence is insufficient."


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


class QualityStatus(str, Enum):
    not_evaluated = "not_evaluated"
    evaluated = "evaluated"
    partial = "partial"
    error = "error"
    legacy_unknown = "legacy_unknown"


class QualityVerdict(str, Enum):
    passed = "passed"
    failed = "failed"
    unknown = "unknown"


class ReviewStatus(str, Enum):
    pending = "pending"
    confirmed = "confirmed"
    dismissed = "dismissed"


class MetricConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    version: str = Field(min_length=1, max_length=40)
    parameters: dict[str, Any] = Field(default_factory=dict)


class PromptConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=50_000)

    @field_validator("version", "text")
    @classmethod
    def non_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value


class ExecutionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adapter_id: str = Field(default="mock", min_length=1, max_length=80)
    prompt: PromptConfig
    generation: GenerationConfig
    context_policy: Literal["dataset_contexts", "none", "retrieval"] = "dataset_contexts"


class QualityRule(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    metric_name: str = Field(min_length=1, max_length=120)
    operator: Literal["gte", "gt", "lte", "lt", "eq"]
    threshold: float


class QualityGate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1, max_length=40)
    rules: list[QualityRule] = Field(min_length=1, max_length=50)
    score_metric: str | None = Field(default=None, min_length=1, max_length=120)

    @model_validator(mode="after")
    def execution_rate_is_not_a_quality_metric(self) -> QualityGate:
        names = {rule.metric_name for rule in self.rules}
        if "execution_success_rate" in names or self.score_metric == "execution_success_rate":
            raise ValueError("execution_success_rate cannot be used as a quality metric")
        return self


class EvaluationJobCreate(BaseModel):
    """Frozen 2.0 request plus the documented 1.0 compatibility shape."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0", "2.0"] | None = None
    dataset_id: str = Field(min_length=1)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    execution: ExecutionConfig | None = None
    metrics: list[MetricConfig] = Field(default_factory=list)
    quality_gate: QualityGate | None = None

    config_version: str | None = Field(default=None, min_length=1, max_length=120)
    model_version: str | None = Field(default=None, min_length=1, max_length=120)
    prompt_version: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("name", "config_version", "model_version", "prompt_version")
    @classmethod
    def non_blank_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @model_validator(mode="after")
    def validate_version_shape(self) -> EvaluationJobCreate:
        legacy_fields = {"config_version", "model_version", "prompt_version"}
        legacy_supplied = bool(legacy_fields.intersection(self.model_fields_set))
        if self.execution is not None and legacy_supplied:
            raise ValueError("AMBIGUOUS_EXECUTION_CONFIG")
        if self.schema_version == "2.0" and self.execution is None:
            raise ValueError("schema_version 2.0 requires execution")
        if self.schema_version == "1.0" and self.execution is not None:
            raise ValueError("schema_version 1.0 cannot include execution")
        return self

    @property
    def is_legacy_request(self) -> bool:
        return self.execution is None

    @property
    def resolved_execution(self) -> ExecutionConfig:
        if self.execution is not None:
            return self.execution
        return ExecutionConfig(
            adapter_id="mock",
            prompt=PromptConfig(
                version=self.prompt_version or "ragops-default-v1",
                text=DEFAULT_PROMPT_TEXT,
            ),
            generation=GenerationConfig(
                model="mock-ragops-v1",
                temperature=0.0,
                top_p=1.0,
                max_output_tokens=512,
                stop=[],
                seed=None,
            ),
            context_policy="dataset_contexts",
        )

    @property
    def legacy_model_label(self) -> str | None:
        return self.model_version or ("deterministic-local" if self.is_legacy_request else None)


class EvaluationJobResponse(BaseModel):
    schema_version: Literal["2.0"] = "2.0"
    id: str
    dataset_id: str
    name: str
    status: JobStatus
    outcome: JobOutcome | None
    execution_snapshot: dict[str, Any] | None
    quality_status: QualityStatus
    quality_verdict: QualityVerdict
    quality_score: float | None
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
    schema_version: Literal["2.0"] = "2.0"
    id: str
    sample_id: str
    question: str
    labels: dict[str, Any]
    reference_answer: str | None
    historical_answer: str | None
    run: dict[str, Any] | None
    quality_status: QualityStatus
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
    schema_version: Literal["1.0", "2.0"] = "2.0"
    id: str
    job_id: str
    status: JobStatus
    outcome: JobOutcome
    generated_at: datetime
    execution_summary: dict[str, Any]
    quality_summary: dict[str, Any]
    execution_snapshot: dict[str, Any] | None
    summary: dict[str, int]
    metrics: list[dict[str, Any]]
    links: dict[str, str]


class SampleReviewUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_status: ReviewStatus


class ReportExportResponse(BaseModel):
    schema_version: Literal["1.0", "2.0"] = "2.0"
    exported_at: datetime
    report: EvaluationReportResponse
    samples: list[EvaluationSampleResponse]


class ModelExecutionStatusResponse(BaseModel):
    schema_version: Literal["2.0"] = "2.0"
    backend_execution_adapter: str
    external_calls_enabled: bool
    execution_available: bool
    active_adapter: dict[str, Any]
    providers: list[dict[str, Any]]
