import pytest

from app.core.errors import DomainError
from app.persistence.models import EvaluationJob
from app.services.jobs import derive_job_outcome, derive_terminal_status, transition_job


@pytest.mark.parametrize(
    ("total", "succeeded", "failed", "expected"),
    [
        (3, 3, 0, "completed"),
        (3, 2, 1, "completed"),
        (3, 0, 3, "failed"),
    ],
)
def test_terminal_status_derivation(total, succeeded, failed, expected) -> None:
    assert derive_terminal_status(total=total, succeeded=succeeded, failed=failed) == expected


@pytest.mark.parametrize(
    ("succeeded", "failed", "expected"),
    [(3, 0, "succeeded"), (2, 1, "partial_failed"), (0, 3, "failed")],
)
def test_terminal_outcome_derivation(succeeded, failed, expected) -> None:
    assert derive_job_outcome(total=3, succeeded=succeeded, failed=failed) == expected


def test_terminal_job_cannot_return_to_running() -> None:
    job = EvaluationJob(
        dataset_id="dataset",
        name="test job",
        status="completed",
        config_version="config",
        model_version="model-v1",
        prompt_version="prompt-v1",
        total_count=1,
        request_fingerprint="hash",
    )

    with pytest.raises(DomainError) as exc_info:
        transition_job(job, "running")

    assert exc_info.value.code == "INVALID_JOB_TRANSITION"


def test_mvp_job_lifecycle_advances_queued_running_completed() -> None:
    job = EvaluationJob(
        dataset_id="dataset",
        name="test lifecycle",
        status="queued",
        config_version="config",
        model_version="model-v1",
        prompt_version="prompt-v1",
        total_count=1,
        request_fingerprint="hash",
    )

    transition_job(job, "running")
    assert job.status == "running"
    transition_job(job, "completed")
    assert job.status == "completed"


def test_terminal_status_requires_all_samples() -> None:
    with pytest.raises(ValueError):
        derive_terminal_status(total=3, succeeded=1, failed=1)
