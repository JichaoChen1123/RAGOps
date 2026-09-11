from __future__ import annotations

import json
import sys

from fastapi.testclient import TestClient

from app import cli
from app.core.config import Settings
from app.main import create_app
from app.persistence.models import AnswerRescore, Dataset, DatasetSample, EvaluationJob, EvaluationJobSample


def _seed(session, suffix: str, batch: str, status: str) -> tuple[str, str]:
    dataset = Dataset(name=f"d-{suffix}", owner="test", status="published")
    session.add(dataset)
    session.flush()
    sample = DatasetSample(dataset_id=dataset.id, ordinal=1, external_id=f"s-{suffix}", question="q", reference_answer="ref", content_sha256="a" * 64)
    session.add(sample)
    session.flush()
    job = EvaluationJob(dataset_id=dataset.id, name=f"j-{suffix}", config_version="c", model_version="m", prompt_version="p", total_count=1, request_fingerprint=(suffix * 64)[:64])
    session.add(job)
    session.flush()
    result = EvaluationJobSample(job_id=job.id, sample_id=sample.id, status="succeeded", answer="answer")
    session.add(result)
    session.flush()
    session.add(AnswerRescore(batch_id=batch, job_id=job.id, job_sample_id=result.id, sample_id=sample.id, algorithm_version="answer-score-v1", source_answer="answer", reference_answers=["ref"], metric_results=[{"metric_name":"strict_em","details":{"matched_reference_index":0}}], status=status, failure_reason="reason" if status != "calculated" else None))
    session.commit()
    return job.id, batch


def test_rescore_read_api_and_cli_are_scoped_and_read_only(monkeypatch, tmp_path, capsys) -> None:
    path = tmp_path / "query.db"
    settings = Settings(environment="test", database_url=f"sqlite:///{path.as_posix()}", auto_create_schema=True)
    with TestClient(create_app(settings)) as client:
        database = client.app.state.database
        with database.session() as session:
            job_one, batch_one = _seed(session, "a", "batch-one", "failed")
            _, batch_two = _seed(session, "b", "batch-two", "skipped")
            session.add(AnswerRescore(batch_id="batch-alt", job_id=job_one, job_sample_id=session.query(EvaluationJobSample).filter_by(job_id=job_one).one().id, sample_id=session.query(EvaluationJobSample).filter_by(job_id=job_one).one().sample_id, algorithm_version="answer-score-v1", source_answer="answer", reference_answers=["ref"], metric_results=[], status="calculated"))
            session.commit()
        before = path.read_bytes()
        all_rows = client.get(f"/api/v1/evaluation-jobs/{job_one}/answer-rescores")
        assert all_rows.status_code == 200 and all_rows.json()["total"] == 2
        only = client.get(f"/api/v1/evaluation-jobs/{job_one}/answer-rescores?batch_id={batch_one}").json()
        assert only["total"] == 1 and only["items"][0]["batch_id"] == batch_one
        assert client.get(f"/api/v1/evaluation-jobs/{job_one}/answer-rescores?batch_id={batch_two}").json()["total"] == 0
        assert {"job_id","job_sample_id","sample_id","algorithm_version","metric_results","status","failure_reason"} <= set(only["items"][0])
        assert client.get("/api/v1/evaluation-jobs/missing/answer-rescores").status_code == 404
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(sys, "argv", ["ragops", "rescore-list", "--job-id", job_one, "--batch-id", batch_one])
    cli.main()
    assert len(json.loads(capsys.readouterr().out)) == 1
    assert path.read_bytes() == before
