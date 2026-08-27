from __future__ import annotations

import base64
import hashlib
import json

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.persistence.models import Dataset, DatasetSample, utc_now
from app.schemas.datasets import (
    DatasetCreate,
    DatasetImportRequest,
    DatasetResponse,
    DatasetSampleInput,
    DatasetSampleResponse,
)


def _canonical_hash(value: object) -> str:
    content = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _decode_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        decoded = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("ascii")
        offset = int(decoded)
        if offset < 0:
            raise ValueError
        return offset
    except (ValueError, UnicodeError, base64.binascii.Error) as exc:
        raise DomainError(
            "INVALID_CURSOR",
            "The pagination cursor is invalid.",
            status_code=422,
        ) from exc


def _encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode("ascii")).decode("ascii")


def _add_samples(
    session: Session,
    dataset: Dataset,
    samples: list[DatasetSampleInput],
) -> int:
    start_ordinal = dataset.sample_count
    for index, sample in enumerate(samples, start=1):
        raw = sample.model_dump(mode="json")
        session.add(
            DatasetSample(
                dataset_id=dataset.id,
                ordinal=start_ordinal + index,
                external_id=sample.sample_id,
                question=sample.question,
                reference_answer=sample.reference_answer,
                gold_document_ids=sample.gold_document_ids,
                gold_evidence_ids=sample.gold_evidence_ids,
                retrieved_contexts=[item.model_dump(mode="json") for item in sample.retrieved_contexts],
                answer=sample.answer,
                citations=[item.model_dump(mode="json") for item in sample.citations],
                tags=sample.tags,
                expected_diagnoses=sample.expected_diagnoses,
                metadata_json=sample.metadata,
                content_sha256=_canonical_hash(raw),
            )
        )
    dataset.sample_count += len(samples)
    return len(samples)


def create_dataset(session: Session, payload: DatasetCreate) -> tuple[Dataset, int]:
    dataset = Dataset(
        name=payload.name,
        description=payload.description,
        owner=payload.owner,
        version=payload.version,
        schema_version=payload.schema_version,
    )
    session.add(dataset)
    try:
        session.flush()
        imported_samples = _add_samples(session, dataset, payload.samples)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise DomainError(
            "DATASET_NAME_CONFLICT",
            "A dataset with this name already exists.",
            status_code=status.HTTP_409_CONFLICT,
            details={"name": payload.name},
        ) from exc
    return dataset, imported_samples


def get_dataset(session: Session, dataset_id: str) -> Dataset:
    dataset = session.get(Dataset, dataset_id)
    if dataset is None:
        raise DomainError(
            "RESOURCE_NOT_FOUND",
            "Dataset not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"dataset_id": dataset_id},
        )
    return dataset


def list_datasets(
    session: Session,
    *,
    limit: int,
    cursor: str | None,
) -> tuple[list[Dataset], int, str | None]:
    offset = _decode_cursor(cursor)
    total = session.scalar(select(func.count()).select_from(Dataset)) or 0
    items = list(
        session.scalars(
            select(Dataset).order_by(Dataset.created_at, Dataset.id).offset(offset).limit(limit)
        )
    )
    next_offset = offset + len(items)
    next_cursor = _encode_cursor(next_offset) if next_offset < total else None
    return items, total, next_cursor


def import_samples(
    session: Session,
    dataset_id: str,
    payload: DatasetImportRequest,
) -> tuple[Dataset, int]:
    dataset = get_dataset(session, dataset_id)
    if dataset.status != "draft":
        raise DomainError(
            "DATASET_IMMUTABLE",
            "Published datasets cannot be modified.",
            status_code=status.HTTP_409_CONFLICT,
            details={"dataset_id": dataset_id},
        )

    incoming_ids = {sample.sample_id for sample in payload.samples}
    existing_ids = set(
        session.scalars(
            select(DatasetSample.external_id).where(
                DatasetSample.dataset_id == dataset_id,
                DatasetSample.external_id.in_(incoming_ids),
            )
        )
    )
    if existing_ids:
        raise DomainError(
            "DUPLICATE_SAMPLE_ID",
            "sample_id must be unique within a dataset version.",
            status_code=status.HTTP_409_CONFLICT,
            details={"sample_ids": sorted(existing_ids)},
        )

    accepted = _add_samples(session, dataset, payload.samples)
    session.commit()
    return dataset, accepted


def publish_dataset(session: Session, dataset_id: str) -> Dataset:
    dataset = get_dataset(session, dataset_id)
    if dataset.status == "published":
        return dataset
    if dataset.sample_count == 0:
        raise DomainError(
            "DATASET_EMPTY",
            "A dataset must contain at least one sample before publication.",
            status_code=status.HTTP_409_CONFLICT,
            details={"dataset_id": dataset_id},
        )
    sample_hashes = list(
        session.scalars(
            select(DatasetSample.content_sha256)
            .where(DatasetSample.dataset_id == dataset_id)
            .order_by(DatasetSample.ordinal)
        )
    )
    dataset.content_sha256 = _canonical_hash(sample_hashes)
    dataset.status = "published"
    dataset.published_at = utc_now()
    session.commit()
    return dataset


def list_samples(session: Session, dataset_id: str) -> list[DatasetSample]:
    get_dataset(session, dataset_id)
    return list(
        session.scalars(
            select(DatasetSample)
            .where(DatasetSample.dataset_id == dataset_id)
            .order_by(DatasetSample.ordinal)
        )
    )


def to_response(dataset: Dataset) -> DatasetResponse:
    return DatasetResponse.model_validate(dataset)


def sample_to_response(sample: DatasetSample) -> DatasetSampleResponse:
    return DatasetSampleResponse(
        sample_id=sample.external_id,
        question=sample.question,
        reference_answer=sample.reference_answer,
        retrieved_contexts=sample.retrieved_contexts,
        answer=sample.answer,
        tags=sample.tags,
        metadata=sample.metadata_json,
    )
