from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.ids import uuid7_str
from app.persistence.db import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid7_str)
    name: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    owner: Mapped[str] = mapped_column(String(120), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0")
    version: Mapped[str] = mapped_column(String(40), nullable=False, default="v1")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", index=True)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    samples: Mapped[list[DatasetSample]] = relationship(
        back_populates="dataset",
        cascade="all, delete-orphan",
        order_by="DatasetSample.ordinal",
    )
    jobs: Mapped[list[EvaluationJob]] = relationship(back_populates="dataset")


class DatasetSample(Base):
    __tablename__ = "dataset_samples"
    __table_args__ = (
        UniqueConstraint("dataset_id", "external_id", name="uq_dataset_sample_external_id"),
        UniqueConstraint("dataset_id", "ordinal", name="uq_dataset_sample_ordinal"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid7_str)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), nullable=False, index=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    external_id: Mapped[str] = mapped_column(String(200), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    reference_answer: Mapped[str | None] = mapped_column(Text)
    gold_document_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    gold_evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    retrieved_contexts: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    answer: Mapped[str | None] = mapped_column(Text)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    expected_diagnoses: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False, default=dict)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    dataset: Mapped[Dataset] = relationship(back_populates="samples")
    job_results: Mapped[list[EvaluationJobSample]] = relationship(back_populates="sample")


class EvaluationJob(Base):
    __tablename__ = "evaluation_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid7_str)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", index=True)
    outcome: Mapped[str | None] = mapped_column(String(32))
    config_version: Mapped[str] = mapped_column(String(120), nullable=False)
    model_version: Mapped[str] = mapped_column(String(120), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(120), nullable=False)
    metric_config: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False)
    queued_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    running_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    succeeded_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    failure_code: Mapped[str | None] = mapped_column(String(80))
    failure_message: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    dataset: Mapped[Dataset] = relationship(back_populates="jobs")
    sample_results: Mapped[list[EvaluationJobSample]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="EvaluationJobSample.created_at",
    )
    report: Mapped[EvaluationReport | None] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        uselist=False,
    )


class EvaluationJobSample(Base):
    __tablename__ = "evaluation_job_samples"
    __table_args__ = (UniqueConstraint("job_id", "sample_id", name="uq_job_sample"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid7_str)
    job_id: Mapped[str] = mapped_column(ForeignKey("evaluation_jobs.id"), nullable=False, index=True)
    sample_id: Mapped[str] = mapped_column(ForeignKey("dataset_samples.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    answer: Mapped[str | None] = mapped_column(Text)
    retrieval_results: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    metric_results: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    diagnoses: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    review_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    failure_code: Mapped[str | None] = mapped_column(String(80))
    failure_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    job: Mapped[EvaluationJob] = relationship(back_populates="sample_results")
    sample: Mapped[DatasetSample] = relationship(back_populates="job_results")


class EvaluationReport(Base):
    __tablename__ = "evaluation_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid7_str)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("evaluation_jobs.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False)
    succeeded_count: Mapped[int] = mapped_column(Integer, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False)
    metrics: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    job: Mapped[EvaluationJob] = relationship(back_populates="report")
