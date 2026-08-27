from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.schemas.datasets import (
    DatasetCreate,
    DatasetImportRequest,
    DatasetImportResponse,
    DatasetListResponse,
    DatasetResponse,
    DatasetSampleListResponse,
)
from app.services import datasets as service

router = APIRouter()
SessionDep = Annotated[Session, Depends(get_session)]


@router.post(
    "",
    response_model=DatasetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a draft dataset",
)
def create_dataset(payload: DatasetCreate, session: SessionDep) -> DatasetResponse:
    return service.to_response(service.create_dataset(session, payload))


@router.get("", response_model=DatasetListResponse, summary="List datasets")
def list_datasets(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: str | None = None,
) -> DatasetListResponse:
    items, total, next_cursor = service.list_datasets(session, limit=limit, cursor=cursor)
    return DatasetListResponse(
        items=[service.to_response(item) for item in items],
        total=total,
        next_cursor=next_cursor,
    )


@router.get("/{dataset_id}", response_model=DatasetResponse, summary="Get a dataset")
def get_dataset(dataset_id: str, session: SessionDep) -> DatasetResponse:
    return service.to_response(service.get_dataset(session, dataset_id))


@router.post(
    "/{dataset_id}/samples:import",
    response_model=DatasetImportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Atomically import dataset samples",
)
def import_samples(
    dataset_id: str,
    payload: DatasetImportRequest,
    session: SessionDep,
) -> DatasetImportResponse:
    dataset, accepted = service.import_samples(session, dataset_id, payload)
    return DatasetImportResponse(
        accepted=accepted,
        rejected=0,
        dataset=service.to_response(dataset),
    )


@router.post(
    "/{dataset_id}:publish",
    response_model=DatasetResponse,
    summary="Publish and freeze a dataset",
)
def publish_dataset(dataset_id: str, session: SessionDep) -> DatasetResponse:
    return service.to_response(service.publish_dataset(session, dataset_id))


@router.get(
    "/{dataset_id}/samples",
    response_model=DatasetSampleListResponse,
    summary="List dataset samples",
)
def list_samples(dataset_id: str, session: SessionDep) -> DatasetSampleListResponse:
    samples = service.list_samples(session, dataset_id)
    return DatasetSampleListResponse(
        items=[service.sample_to_response(sample) for sample in samples],
        total=len(samples),
    )
