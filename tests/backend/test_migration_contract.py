from __future__ import annotations

import json
import sqlite3

import pytest
from sqlalchemy import inspect, text

from app.persistence.db import Database


LEGACY_SCHEMA = [
    """CREATE TABLE datasets (
        id VARCHAR(36) PRIMARY KEY, name VARCHAR(160) NOT NULL UNIQUE,
        description TEXT, owner VARCHAR(120) NOT NULL, schema_version VARCHAR(20) NOT NULL,
        version VARCHAR(40) NOT NULL, status VARCHAR(20) NOT NULL, sample_count INTEGER NOT NULL,
        content_sha256 VARCHAR(64), created_at DATETIME NOT NULL, published_at DATETIME
    )""",
    """CREATE TABLE dataset_samples (
        id VARCHAR(36) PRIMARY KEY, dataset_id VARCHAR(36) NOT NULL, ordinal INTEGER NOT NULL,
        external_id VARCHAR(200) NOT NULL, question TEXT NOT NULL, reference_answer TEXT,
        gold_document_ids JSON NOT NULL, gold_evidence_ids JSON NOT NULL,
        retrieved_contexts JSON NOT NULL, answer TEXT, citations JSON NOT NULL,
        tags JSON NOT NULL, expected_diagnoses JSON NOT NULL, metadata JSON NOT NULL,
        content_sha256 VARCHAR(64) NOT NULL, created_at DATETIME NOT NULL
    )""",
    """CREATE TABLE evaluation_jobs (
        id VARCHAR(36) PRIMARY KEY, dataset_id VARCHAR(36) NOT NULL, name VARCHAR(160) NOT NULL,
        status VARCHAR(32) NOT NULL, outcome VARCHAR(32), config_version VARCHAR(120) NOT NULL,
        model_version VARCHAR(120) NOT NULL, prompt_version VARCHAR(120) NOT NULL,
        metric_config JSON NOT NULL, total_count INTEGER NOT NULL, queued_count INTEGER NOT NULL,
        running_count INTEGER NOT NULL, succeeded_count INTEGER NOT NULL, failed_count INTEGER NOT NULL,
        progress FLOAT NOT NULL, failure_code VARCHAR(80), failure_message TEXT,
        idempotency_key VARCHAR(128), request_fingerprint VARCHAR(64) NOT NULL,
        created_at DATETIME NOT NULL, started_at DATETIME, finished_at DATETIME
    )""",
    """CREATE TABLE evaluation_job_samples (
        id VARCHAR(36) PRIMARY KEY, job_id VARCHAR(36) NOT NULL, sample_id VARCHAR(36) NOT NULL,
        status VARCHAR(24) NOT NULL, answer TEXT, retrieval_results JSON NOT NULL,
        metric_results JSON NOT NULL, diagnoses JSON NOT NULL, review_status VARCHAR(20) NOT NULL,
        reviewed_at DATETIME, latency_ms INTEGER, failure_code VARCHAR(80), failure_message TEXT,
        created_at DATETIME NOT NULL, started_at DATETIME, finished_at DATETIME
    )""",
    """CREATE TABLE evaluation_reports (
        id VARCHAR(36) PRIMARY KEY, job_id VARCHAR(36) NOT NULL UNIQUE, status VARCHAR(32) NOT NULL,
        outcome VARCHAR(32) NOT NULL, total_count INTEGER NOT NULL, succeeded_count INTEGER NOT NULL,
        failed_count INTEGER NOT NULL, metrics JSON NOT NULL, generated_at DATETIME NOT NULL
    )""",
]


def _create_legacy_database(path) -> None:
    connection = sqlite3.connect(path)
    try:
        for statement in LEGACY_SCHEMA:
            connection.execute(statement)
        now = "2026-09-05 08:00:00"
        connection.execute(
            "INSERT INTO datasets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "dataset-legacy",
                "legacy dataset",
                None,
                "migration-test",
                "1.0",
                "v1",
                "published",
                1,
                "a" * 64,
                now,
                now,
            ),
        )
        connection.execute(
            "INSERT INTO dataset_samples VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "sample-row-legacy",
                "dataset-legacy",
                1,
                "sample-legacy",
                "Legacy question",
                "Legacy reference",
                json.dumps(["doc-1"]),
                json.dumps(["ev-1"]),
                json.dumps([{"rank": 1, "doc_id": "doc-1", "chunk_id": "chunk-1"}]),
                "Legacy historical answer",
                json.dumps([{"claim_id": "c1", "chunk_id": "chunk-1"}]),
                json.dumps(["legacy"]),
                json.dumps([]),
                json.dumps({"kept": True}),
                "b" * 64,
                now,
            ),
        )
        connection.execute(
            "INSERT INTO evaluation_jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "job-legacy",
                "dataset-legacy",
                "legacy job",
                "completed",
                "succeeded",
                "old-config",
                "old-model-label",
                "old-prompt",
                json.dumps([]),
                1,
                0,
                0,
                1,
                0,
                1.0,
                None,
                None,
                None,
                "c" * 64,
                now,
                now,
                now,
            ),
        )
        connection.execute(
            "INSERT INTO evaluation_job_samples VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "job-sample-legacy",
                "job-legacy",
                "sample-row-legacy",
                "succeeded",
                "Legacy run answer",
                json.dumps([]),
                json.dumps([]),
                json.dumps([]),
                "confirmed",
                now,
                4,
                None,
                None,
                now,
                now,
                now,
            ),
        )
        connection.execute(
            "INSERT INTO evaluation_reports VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "report-legacy",
                "job-legacy",
                "completed",
                "succeeded",
                1,
                1,
                0,
                json.dumps([{"metric_name": "legacy_metric", "value": 0.5}]),
                now,
            ),
        )
        connection.commit()
    finally:
        connection.close()


def test_legacy_database_upgrade_is_idempotent_and_preserves_rows(tmp_path) -> None:
    path = tmp_path / "legacy.db"
    _create_legacy_database(path)
    database = Database(f"sqlite:///{path.as_posix()}")

    first = database.migrate()
    second = database.migrate()
    database.dispose()

    assert first == ["0001_mvp_baseline", "0002_model_execution_contract"]
    assert second == []
    reopened = Database(f"sqlite:///{path.as_posix()}")
    assert reopened.migrate() == []
    with reopened.engine.connect() as connection:
        versions = connection.execute(
            text("SELECT version FROM ragops_schema_migrations ORDER BY version")
        ).scalars().all()
        sample = connection.execute(
            text(
                "SELECT normalized_schema_version, context_origin, historical_answer, "
                "historical_citations, metadata FROM dataset_samples WHERE id = 'sample-row-legacy'"
            )
        ).one()
        job = connection.execute(
            text(
                "SELECT contract_version, adapter_id, quality_status, quality_verdict, "
                "quality_score FROM evaluation_jobs WHERE id = 'job-legacy'"
            )
        ).one()
        report = connection.execute(
            text(
                "SELECT schema_version, execution_summary, quality_summary, metrics "
                "FROM evaluation_reports WHERE id = 'report-legacy'"
            )
        ).one()
        review_status = connection.execute(
            text(
                "SELECT review_status FROM evaluation_job_samples "
                "WHERE id = 'job-sample-legacy'"
            )
        ).scalar_one()
    reopened.dispose()

    assert versions == ["0001_mvp_baseline", "0002_model_execution_contract"]
    assert sample[0:3] == ("1.0", "legacy_unknown", "Legacy historical answer")
    assert json.loads(sample[3])[0]["chunk_id"] == "chunk-1"
    assert json.loads(sample[4]) == {"kept": True}
    assert job == ("1.0", "legacy_deterministic", "legacy_unknown", "unknown", None)
    assert report[0] == "1.0"
    assert json.loads(report[1])["success_rate"] == 1.0
    assert json.loads(report[2])["status"] == "legacy_unknown"
    assert json.loads(report[3])[0]["metric_name"] == "legacy_metric"
    assert review_status == "confirmed"


def test_empty_database_migrates_to_head_and_second_run_is_empty(tmp_path) -> None:
    path = tmp_path / "empty.db"
    database = Database(f"sqlite:///{path.as_posix()}")

    assert database.migrate() == ["0001_mvp_baseline", "0002_model_execution_contract"]
    assert database.migrate() == []
    tables = set(inspect(database.engine).get_table_names())
    database.dispose()

    assert {
        "datasets",
        "dataset_samples",
        "evaluation_jobs",
        "evaluation_job_samples",
        "evaluation_reports",
        "ragops_schema_migrations",
    } <= tables


def test_partial_legacy_schema_is_rejected_without_rebuild(tmp_path) -> None:
    path = tmp_path / "broken.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE datasets (id VARCHAR(36) PRIMARY KEY)")
    connection.commit()
    connection.close()
    database = Database(f"sqlite:///{path.as_posix()}")

    with pytest.raises(RuntimeError, match="missing tables"):
        database.migrate()

    assert inspect(database.engine).get_table_names() == ["datasets"]
    database.dispose()
