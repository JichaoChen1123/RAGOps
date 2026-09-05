from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import (
    BaseModel, ConfigDict, Field, ValidationError, ValidationInfo,
    field_validator, model_validator,
)
from pydantic_core import PydanticCustomError


def _field_error(model: BaseModel, field: str, message: str) -> None:
    raise ValidationError.from_exception_data(
        type(model).__name__,
        [{"type": PydanticCustomError("field_conflict", message), "loc": (field,)}],
    )


class RetrievedContextInput(BaseModel):
    """The 1.0 context shape retained for compatibility."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    rank: int = Field(ge=1)
    doc_id: str = Field(min_length=1, max_length=300)
    chunk_id: str = Field(min_length=1, max_length=300)
    evidence_ids: list[str] = Field(default_factory=list)
    text: str = ""
    score: float | None = None
    relevance_grade: int | None = Field(default=None, ge=0, le=3)
    rank_before: int | None = Field(default=None, ge=1)
    usefulness: bool | None = None


class ContextInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    origin: Literal["provided", "retrieved", "legacy_unknown"]
    rank: int = Field(ge=1)
    rank_before: int | None = Field(default=None, ge=1)
    retrieval_run_id: str | None = Field(
        default=None, min_length=1, max_length=300, validate_default=True
    )
    doc_id: str = Field(min_length=1, max_length=300)
    chunk_id: str = Field(min_length=1, max_length=300)
    evidence_ids: list[str] = Field(default_factory=list)
    text: str = Field(min_length=1, max_length=50_000)
    score: float | None = None
    relevance_grade: int | None = Field(default=None, ge=0, le=3)
    usefulness: bool | None = None

    @field_validator("doc_id", "chunk_id", "text")
    @classmethod
    def context_strings_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @field_validator("retrieval_run_id")
    @classmethod
    def retrieval_provenance_matches_origin(
        cls, value: str | None, info: ValidationInfo
    ) -> str | None:
        if value is not None:
            value = value.strip()
            if not value:
                raise ValueError("retrieval_run_id must not be blank")
        if info.data.get("origin") == "retrieved" and not value:
            raise ValueError("retrieved context requires retrieval_run_id")
        if info.data.get("origin") != "retrieved" and value is not None:
            raise ValueError("only retrieved context may include retrieval_run_id")
        return value


class CitationInput(BaseModel):
    """The 1.0 historical citation shape."""

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


class HistoricalCitationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    citation_id: str = Field(min_length=1, max_length=300)
    claim_id: str | None = Field(default=None, max_length=300)
    raw: str = Field(min_length=1, max_length=10_000)
    target_type: Literal["context_item", "document", "external"]
    target_id: str = Field(min_length=1, max_length=300)
    resolved: bool
    supports_claim: bool | None = None
    support_judge_version: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def semantic_support_requires_resolution(self) -> HistoricalCitationInput:
        if self.supports_claim is True and not self.resolved:
            raise ValueError("a citation cannot support a claim when it does not resolve")
        return self


class HistoricalOutputInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1, max_length=100_000)
    citations: list[HistoricalCitationInput] = Field(default_factory=list)
    recorded_at: datetime

    @field_validator("answer")
    @classmethod
    def answer_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("answer must not be blank")
        return value


class SampleLabelsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_answer: str | None = None
    gold_document_ids: list[str] = Field(default_factory=list)
    gold_evidence_ids: list[str] = Field(default_factory=list)
    expected_diagnoses: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def label_identifiers_are_unique(self) -> SampleLabelsInput:
        for field_name in (
            "gold_document_ids",
            "gold_evidence_ids",
            "expected_diagnoses",
        ):
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} must not contain duplicates")
        return self


class DatasetSampleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0", "2.0"] = "1.0"
    sample_id: str = Field(min_length=1, max_length=200)
    question: str = Field(min_length=1, max_length=20_000)

    # 1.0 fields
    reference_answer: str | None = None
    gold_document_ids: list[str] = Field(default_factory=list)
    gold_evidence_ids: list[str] = Field(default_factory=list)
    retrieved_contexts: list[RetrievedContextInput] = Field(default_factory=list)
    answer: str | None = None
    citations: list[CitationInput] = Field(default_factory=list)
    expected_diagnoses: list[str] = Field(default_factory=list)

    # 2.0 fields
    labels: SampleLabelsInput | None = None
    contexts: list[ContextInput] | None = None
    historical_output: HistoricalOutputInput | None = None

    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("schema_version", mode="before")
    @classmethod
    def validate_raw_version(cls, value: object) -> object:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("schema_version must be a supported non-blank value")
        return value

    @field_validator("sample_id", "question")
    @classmethod
    def non_blank_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @model_validator(mode="after")
    def validate_version_fields_and_references(self) -> DatasetSampleInput:
        old_fields = {
            "reference_answer",
            "gold_document_ids",
            "gold_evidence_ids",
            "retrieved_contexts",
            "answer",
            "citations",
            "expected_diagnoses",
        }
        new_fields = {"labels", "contexts", "historical_output"}
        if self.schema_version == "2.0" and old_fields.intersection(self.model_fields_set):
            field = sorted(old_fields.intersection(self.model_fields_set))[0]
            _field_error(self, field, "AMBIGUOUS_SCHEMA_FIELDS")
        if self.schema_version == "1.0" and new_fields.intersection(self.model_fields_set):
            field = sorted(new_fields.intersection(self.model_fields_set))[0]
            _field_error(self, field, "AMBIGUOUS_SCHEMA_FIELDS")

        ranks = [context.rank for context in self.normalized_contexts]
        if len(ranks) != len(set(ranks)):
            if self.schema_version == "1.0":
                _field_error(self, "retrieved_contexts", "retrieved context ranks must be unique")
            _field_error(self, "contexts", "context ranks must be unique")
        if self.schema_version == "2.0" and sorted(ranks) != list(range(1, len(ranks) + 1)):
            _field_error(self, "contexts", "context ranks must start at 1 and be contiguous")
        if self.schema_version == "2.0" and any(
            context.origin != "retrieved" and context.rank_before is not None
            for context in self.normalized_contexts
        ):
            raise ValueError("only retrieved context may include rank_before")
        if self.schema_version == "1.0":
            chunk_ids = {context.chunk_id for context in self.retrieved_contexts}
            missing = [
                citation.chunk_id
                for citation in self.citations
                if citation.resolved is not False and citation.chunk_id not in chunk_ids
            ]
            if missing:
                raise ValueError(f"citation targets are missing from retrieved contexts: {missing}")
        elif self.historical_output is not None:
            context_ids = {context.chunk_id for context in self.normalized_contexts}
            missing_targets = [
                citation.target_id
                for citation in self.historical_output.citations
                if citation.target_type == "context_item"
                and citation.resolved
                and citation.target_id not in context_ids
            ]
            if missing_targets:
                raise ValueError(
                    "historical citation targets are missing from contexts: "
                    f"{missing_targets}"
                )
        return self

    @property
    def normalized_labels(self) -> SampleLabelsInput:
        if self.labels is not None:
            return self.labels
        return SampleLabelsInput(
            reference_answer=self.reference_answer,
            gold_document_ids=self.gold_document_ids,
            gold_evidence_ids=self.gold_evidence_ids,
            expected_diagnoses=self.expected_diagnoses,
        )

    @property
    def normalized_contexts(self) -> list[ContextInput]:
        if self.contexts is not None:
            return self.contexts
        return [
            ContextInput(
                origin="legacy_unknown",
                rank=item.rank,
                rank_before=item.rank_before,
                retrieval_run_id=None,
                doc_id=item.doc_id,
                chunk_id=item.chunk_id,
                evidence_ids=item.evidence_ids,
                text=item.text or "(legacy context text unavailable)",
                score=item.score,
                relevance_grade=item.relevance_grade,
                usefulness=item.usefulness,
            )
            for item in self.retrieved_contexts
        ]

    @property
    def normalized_historical_answer(self) -> str | None:
        return self.historical_output.answer if self.historical_output else self.answer

    @property
    def normalized_historical_citations(self) -> list[dict[str, Any]]:
        if self.historical_output:
            return [item.model_dump(mode="json") for item in self.historical_output.citations]
        return [item.model_dump(mode="json") for item in self.citations]


class DatasetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160, examples=["customer-support-golden-set"])
    description: str | None = Field(default=None, max_length=2000)
    owner: str = Field(min_length=1, max_length=120, examples=["quality-platform"])
    version: str = Field(default="v1", min_length=1, max_length=40, examples=["v1"])
    schema_version: Literal["1.0", "2.0"] = "1.0"
    samples: list[DatasetSampleInput] = Field(default_factory=list, max_length=1000)

    @field_validator("schema_version", mode="before")
    @classmethod
    def validate_raw_version(cls, value: object) -> object:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("schema_version must be a supported non-blank value")
        return value

    @field_validator("name", "owner", "version")
    @classmethod
    def non_blank_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @model_validator(mode="after")
    def consistent_and_unique_samples(self) -> DatasetCreate:
        ids = [sample.sample_id for sample in self.samples]
        if len(ids) != len(set(ids)):
            raise ValueError("sample_id must be unique within a batch")
        mismatched = [
            sample.sample_id for sample in self.samples if sample.schema_version != self.schema_version
        ]
        if mismatched:
            raise ValueError("dataset and embedded sample schema_version must match")
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
    model_config = ConfigDict(from_attributes=True)

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
    schema_version: Literal["1.0", "2.0"]
    sample_id: str
    question: str
    labels: dict[str, Any]
    contexts: list[dict[str, Any]]
    historical_output: dict[str, Any] | None
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
