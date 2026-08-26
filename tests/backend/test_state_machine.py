import pytest

from app.core.errors import DomainError
from app.persistence.models import EvaluationJob
from app.services.jobs import derive_terminal_status, transition_job


@pytest.mark.parametrize(
    ("total", "succeeded", "failed", "expected"),
    [
        (3, 3, 0, "succeeded"),
        (3, 2, 1, "partial_failed"),
        (3, 0, 3, "failed"),
    ],
)
def test_terminal_status_derivation(total, succeeded, failed, expected) -> None:
    assert derive_terminal_status(total=total, succeeded=succeeded, failed=failed) == expected


def test_terminal_job_cannot_return_to_running() -> None:
    job = EvaluationJob(
        dataset_id="dataset",
        status="succeeded",
        config_version="config",
        total_count=1,
        request_fingerprint="hash",
    )

    with pytest.raises(DomainError) as exc_info:
        transition_job(job, "running")

    assert exc_info.value.code == "INVALID_JOB_TRANSITION"


def test_terminal_status_requires_all_samples() -> None:
    with pytest.raises(ValueError):
        derive_terminal_status(total=3, succeeded=1, failed=1)
