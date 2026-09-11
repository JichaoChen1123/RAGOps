from __future__ import annotations

import sqlite3
import sys
import json

import pytest

from app import cli
from app.core.config import Settings
from app.persistence.db import Database
from app.persistence.models import Dataset, DatasetSample, EvaluationJob, EvaluationJobSample


def _settings(path) -> Settings:
    return Settings(environment="test", database_url=f"sqlite:///{path.as_posix()}", auto_create_schema=False)


def _run(monkeypatch, path, job_id: str) -> None:
    monkeypatch.setattr(cli, "get_settings", lambda: _settings(path))
    monkeypatch.setattr(sys, "argv", ["ragops", "rescore", "--job-id", job_id, "--dry-run"])
    cli.main()


def test_dry_run_cli_does_not_mutate_migrated_database(monkeypatch, tmp_path) -> None:
    path = tmp_path / "migrated.db"
    database = Database(f"sqlite:///{path.as_posix()}")
    database.migrate()
    with database.engine.begin() as connection:
        connection.exec_driver_sql("INSERT INTO datasets (id,name,owner,schema_version,version,status,sample_count,created_at) VALUES ('d','d','o','1','v','published',0,CURRENT_TIMESTAMP)")
    database.dispose()
    before = path.read_bytes()
    _run(monkeypatch, path, "missing-job")
    assert path.read_bytes() == before


def test_dry_run_cli_scores_existing_answer_without_writes(monkeypatch, tmp_path, capsys) -> None:
    path = tmp_path / "scorable.db"
    database = Database(f"sqlite:///{path.as_posix()}")
    database.migrate()
    with database.session() as session:
        dataset = Dataset(name="scorable", owner="test", status="published")
        session.add(dataset)
        session.flush()
        sample = DatasetSample(dataset_id=dataset.id, ordinal=1, external_id="s", question="q", reference_answer="answer", content_sha256="a" * 64)
        session.add(sample)
        session.flush()
        job = EvaluationJob(dataset_id=dataset.id, name="job", config_version="c", model_version="m", prompt_version="p", total_count=1, request_fingerprint="b" * 64)
        session.add(job)
        session.flush()
        row = EvaluationJobSample(job_id=job.id, sample_id=sample.id, status="succeeded", answer="answer", metric_results=[{"metric_name": "old", "value": 1}])
        session.add(row)
        session.commit()
        job_id = job.id
    database.dispose()
    before = path.read_bytes()
    _run(monkeypatch, path, job_id)
    summary = json.loads(capsys.readouterr().out)
    assert summary["selected"] == 1 and summary["succeeded"] == 1
    assert path.read_bytes() == before
    reopened = Database(f"sqlite:///{path.as_posix()}")
    with reopened.session() as session:
        persisted = session.get(EvaluationJobSample, row.id)
        assert persisted is not None and persisted.answer == "answer"
        assert persisted.sample.reference_answer == "answer"
        assert persisted.metric_results == [{"metric_name": "old", "value": 1}]
    reopened.dispose()


def test_dry_run_cli_refuses_legacy_database_without_writes(monkeypatch, tmp_path) -> None:
    path = tmp_path / "legacy.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE datasets (id TEXT PRIMARY KEY, marker TEXT)")
    connection.execute("INSERT INTO datasets VALUES ('d', 'kept')")
    connection.commit()
    connection.close()
    before = path.read_bytes()
    with pytest.raises(SystemExit, match="ragops init-db"):
        _run(monkeypatch, path, "missing-job")
    assert path.read_bytes() == before


def test_dry_run_cli_does_not_create_missing_sqlite_file(monkeypatch, tmp_path) -> None:
    path = tmp_path / "missing.db"
    with pytest.raises(SystemExit, match="ragops init-db"):
        _run(monkeypatch, path, "missing-job")
    assert not path.exists()
