from fastapi import APIRouter

from app.api.v1 import datasets, evaluation_jobs, model_execution

api_router = APIRouter()
api_router.include_router(datasets.router, prefix="/datasets", tags=["datasets"])
api_router.include_router(evaluation_jobs.router, prefix="/evaluation-jobs", tags=["evaluation-jobs"])
api_router.include_router(
    model_execution.router,
    prefix="/model-execution",
    tags=["model-execution"],
)
