from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RetrievedContextInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int = Field(ge=1)
    doc_id: str = Field(min_length=1, max_length=300)
    chunk_id: str = Field(min_length=1, max_length=300)
    evidence_ids: list[str] = Field(default_factory=list)
    text: str = ""
    score: float | None = None
    relevance_grade: int | None = Field(default=None, ge=0, le=3)
    rank_before: int | None = Field(default=None, ge=1)
    usefulness: bool | None = None


class CitationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    citation_id: str | None = Field(default=None, min_length=1, max_length=300)
    claim_id: str | None = None
    chunk_id: str = Field(min_length=1, max_length=300)
    resolved: bool | None = None
    supports_claim: bool | None = None

    @model_validator(mode="after")
    def support_requires_resolution(self) -> CitationInput:
        if self.supports_claim is True and self.resolved is False:
            raise ValueError("a citation cannot support a claim when it does not resolve")
        return self


class DatasetSampleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    sample_id: str = Field(min_length=1, max_length=200)
    question: str = Field(min_length=1)
    reference_answer: str | None = None
    gold_document_ids: list[str] = Field(default_factory=list)
    gold_evidence_ids: list[str] = Field(default_factory=list)
    retrieved_contexts: list[RetrievedContextInput] = Field(default_factory=list)
    answer: str | None = None
    citations: list[CitationInput] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    expected_diagnoses: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("sample_id", "question")
    @classmethod
    def non_blank_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped

    @model_validator(mode="after")
    def validate_references(self) -> DatasetSampleInput:
        ranks = [context.rank for context in self.retrieved_contexts]
        if len(ranks) != len(set(ranks)):
            raise ValueError("retrieved context ranks must be unique")
        chunk_ids = {context.chunk_id for context in self.retrieved_contexts}
        missing = [
            citation.chunk_id
            for citation in self.citations
            if citation.resolved is not False and citation.chunk_id not in chunk_ids
        ]
        if missing:
            raise ValueError(f"citation targets are missing from retrieved contexts: {missing}")
        return self


class DatasetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160, examples=["customer-support-golden-set"])
    description: str | None = Field(default=None, max_length=2000)
    owner: str = Field(min_length=1, max_length=120, examples=["quality-platform"])
    version: str = Field(default="v1", min_length=1, max_length=40, examples=["v1"])
    schema_version: Literal["1.0"] = "1.0"
    samples: list[DatasetSampleInput] = Field(default_factory=list, max_length=1000)

    @field_validator("name", "owner", "version")
    @classmethod
    def non_blank_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped

    @model_validator(mode="after")
    def unique_sample_ids(self) -> DatasetCreate:
        ids = [sample.sample_id for sample in self.samples]
        if len(ids) != len(set(ids)):
            raise ValueError("sample_id must be unique within a batch")
        return self


class DatasetImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    samples: list[DatasetSampleInput] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def unique_sample_ids(self) -> DatasetImportRequest:
        ids = [sample.sample_id for sample in self.samples]
        if len(ids) != len(set(ids)):
            raise ValueError("sample_id must be unique within a batch")
        return self


class DatasetResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": "01912345-6789-7abc-8def-0123456789ab",
                    "name": "customer-support-golden-set",
                    "description": "Synthetic, de-identified support questions.",
                    "owner": "quality-platform",
                    "schema_version": "1.0",
                    "version": "v1",
                    "status": "published",
                    "sample_count": 6,
                    "content_sha256": "0" * 64,
                    "created_at": "2026-08-26T12:00:00Z",
                    "published_at": "2026-08-26T12:01:00Z",
                }
            ]
        },
    )

    id: str
    name: str
    description: str | None
    owner: str
    schema_version: str
    version: str
    status: Literal["draft", "published"]
    sample_count: int
    content_sha256: str | None
    created_at: datetime
    published_at: datetime | None


class DatasetListResponse(BaseModel):
    items: list[DatasetResponse]
    total: int
    next_cursor: str | None


class DatasetSampleResponse(BaseModel):
    sample_id: str
    question: str
    reference_answer: str | None
    retrieved_contexts: list[dict[str, Any]]
    answer: str | None
    tags: list[str]
    metadata: dict[str, Any]


class DatasetSampleListResponse(BaseModel):
    items: list[DatasetSampleResponse]
    total: int


class DatasetImportResponse(BaseModel):
    accepted: int
    rejected: int
    dataset: DatasetResponse


class DatasetCreateResponse(DatasetResponse):
    imported_samples: int
