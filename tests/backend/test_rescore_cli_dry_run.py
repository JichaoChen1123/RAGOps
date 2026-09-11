from __future__ import annotations

import sqlite3
import sys

import pytest

from app import cli
from app.core.config import Settings
from app.core.errors import DomainError
from app.persistence.db import Database


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
    with pytest.raises(DomainError):
        _run(monkeypatch, path, "missing-job")
    assert path.read_bytes() == before


def test_dry_run_cli_refuses_legacy_database_without_writes(monkeypatch, tmp_path) -> None:
    path = tmp_path / "legacy.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE datasets (id TEXT PRIMARY KEY, marker TEXT)")
    connection.execute("INSERT INTO datasets VALUES ('d', 'kept')")
    connection.commit(); connection.close()
    before = path.read_bytes()
    with pytest.raises(SystemExit, match="ragops init-db"):
        _run(monkeypatch, path, "missing-job")
    assert path.read_bytes() == before


def test_dry_run_cli_does_not_create_missing_sqlite_file(monkeypatch, tmp_path) -> None:
    path = tmp_path / "missing.db"
    with pytest.raises(SystemExit, match="ragops init-db"):
        _run(monkeypatch, path, "missing-job")
    assert not path.exists()
