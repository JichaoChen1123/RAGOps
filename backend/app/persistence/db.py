from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import Engine, inspect, text, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


class Database:
    def __init__(self, url: str) -> None:
        engine_options: dict[str, object] = {"pool_pre_ping": True}
        if url.startswith("sqlite"):
            engine_options["connect_args"] = {"check_same_thread": False}
        if url in {"sqlite://", "sqlite:///:memory:"}:
            engine_options["poolclass"] = StaticPool
        self.engine: Engine = create_engine(url, **engine_options)
        self.session_factory = sessionmaker(
            bind=self.engine,
            class_=Session,
            expire_on_commit=False,
            autoflush=False,
        )

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self.session_factory()
        try:
            yield session
        finally:
            session.close()

    def create_all(self) -> None:
        from app.persistence import models  # noqa: F401

        Base.metadata.create_all(self.engine)

    def migrate(self) -> list[str]:
        """Upgrade an empty, baseline, or already-upgraded database without data loss."""

        from app.persistence import models  # noqa: F401

        applied: list[str] = []
        application_tables = {
            "datasets",
            "dataset_samples",
            "evaluation_jobs",
            "evaluation_job_samples",
            "evaluation_reports",
        }
        with self.engine.begin() as connection:
            existing_tables = set(inspect(connection).get_table_names())
            present_application_tables = application_tables.intersection(existing_tables)
            if not present_application_tables:
                Base.metadata.create_all(connection)
                self._ensure_migration_table(connection)
                self._record_migration(connection, "0001_mvp_baseline")
                self._record_migration(connection, "0002_model_execution_contract")
                return ["0001_mvp_baseline", "0002_model_execution_contract"]

            if present_application_tables != application_tables:
                missing = sorted(application_tables - present_application_tables)
                raise RuntimeError(
                    "Database does not match the RAGOps MVP baseline; missing tables: "
                    + ", ".join(missing)
                )
            self._validate_baseline(connection)
            self._ensure_migration_table(connection)
            versions = {
                row[0]
                for row in connection.execute(
                    text("SELECT version FROM ragops_schema_migrations")
                )
            }
            if "0001_mvp_baseline" not in versions:
                self._record_migration(connection, "0001_mvp_baseline")
                applied.append("0001_mvp_baseline")
            if "0002_model_execution_contract" not in versions:
                self._apply_model_execution_contract(connection)
                self._record_migration(connection, "0002_model_execution_contract")
                applied.append("0002_model_execution_contract")
            else:
                self._validate_contract_columns(connection)
        return applied

    @staticmethod
    def _ensure_migration_table(connection: object) -> None:
        connection.execute(  # type: ignore[attr-defined]
            text(
                "CREATE TABLE IF NOT EXISTS ragops_schema_migrations ("
                "version VARCHAR(80) PRIMARY KEY NOT NULL, "
                "applied_at VARCHAR(40) NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
        )

    @staticmethod
    def _record_migration(connection: object, version: str) -> None:
        connection.execute(  # type: ignore[attr-defined]
            text(
                "INSERT INTO ragops_schema_migrations (version) "
                "SELECT :version WHERE NOT EXISTS ("
                "SELECT 1 FROM ragops_schema_migrations WHERE version = :version)"
            ),
            {"version": version},
        )

    @staticmethod
    def _validate_baseline(connection: object) -> None:
        required: dict[str, set[str]] = {
            "datasets": {"id", "name", "schema_version", "version", "status"},
            "dataset_samples": {
                "id",
                "dataset_id",
                "external_id",
                "question",
                "answer",
                "citations",
                "content_sha256",
            },
            "evaluation_jobs": {
                "id",
                "dataset_id",
                "status",
                "config_version",
                "model_version",
                "prompt_version",
            },
            "evaluation_job_samples": {
                "id",
                "job_id",
                "sample_id",
                "status",
                "answer",
            },
            "evaluation_reports": {
                "id",
                "job_id",
                "status",
                "outcome",
                "metrics",
            },
        }
        inspector = inspect(connection)
        for table_name, expected in required.items():
            actual = {column["name"] for column in inspector.get_columns(table_name)}
            missing = expected - actual
            if missing:
                raise RuntimeError(
                    f"Database table {table_name} does not match the MVP baseline; "
                    f"missing columns: {', '.join(sorted(missing))}"
                )

    def _apply_model_execution_contract(self, connection: object) -> None:
        additions: dict[str, dict[str, str]] = {
            "dataset_samples": {
                "normalized_schema_version": "VARCHAR(20) NOT NULL DEFAULT '1.0'",
                "context_origin": "VARCHAR(32) NOT NULL DEFAULT 'legacy_unknown'",
                "historical_answer": "TEXT",
                "historical_citations": "JSON NOT NULL DEFAULT '[]'",
            },
            "evaluation_jobs": {
                "contract_version": "VARCHAR(20) NOT NULL DEFAULT '1.0'",
                "adapter_id": "VARCHAR(80) NOT NULL DEFAULT 'legacy_deterministic'",
                "execution_snapshot": "JSON",
                "quality_status": "VARCHAR(32) NOT NULL DEFAULT 'legacy_unknown'",
                "quality_verdict": "VARCHAR(32) NOT NULL DEFAULT 'unknown'",
                "quality_score": "FLOAT",
            },
            "evaluation_job_samples": {
                "run_id": "VARCHAR(36)",
                "run_snapshot": "JSON",
                "quality_status": "VARCHAR(32) NOT NULL DEFAULT 'legacy_unknown'",
            },
            "evaluation_reports": {
                "schema_version": "VARCHAR(20) NOT NULL DEFAULT '1.0'",
                "execution_summary": "JSON",
                "quality_summary": "JSON",
                "execution_snapshot": "JSON",
            },
        }
        inspector = inspect(connection)
        for table_name, columns in additions.items():
            existing = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, definition in columns.items():
                if column_name not in existing:
                    connection.execute(  # type: ignore[attr-defined]
                        text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")
                    )

        connection.execute(  # type: ignore[attr-defined]
            text(
                "UPDATE dataset_samples SET historical_answer = answer "
                "WHERE historical_answer IS NULL AND answer IS NOT NULL"
            )
        )
        rows = connection.execute(  # type: ignore[attr-defined]
            text(
                "SELECT id, citations FROM dataset_samples "
                "WHERE historical_citations IS NULL OR historical_citations = '[]'"
            )
        ).all()
        for row in rows:
            citations = row[1] if isinstance(row[1], str) else json.dumps(row[1] or [])
            connection.execute(  # type: ignore[attr-defined]
                text(
                    "UPDATE dataset_samples SET historical_citations = :citations "
                    "WHERE id = :id"
                ),
                {"citations": citations, "id": row[0]},
            )
        report_rows = connection.execute(  # type: ignore[attr-defined]
            text(
                "SELECT id, total_count, succeeded_count, failed_count, outcome "
                "FROM evaluation_reports WHERE execution_summary IS NULL"
            )
        ).all()
        for row in report_rows:
            execution_summary = json.dumps(
                {
                    "outcome": row[4],
                    "total_count": row[1],
                    "succeeded_count": row[2],
                    "failed_count": row[3],
                    "success_rate": row[2] / row[1] if row[1] else None,
                },
                separators=(",", ":"),
            )
            quality_summary = json.dumps(
                {
                    "status": "legacy_unknown",
                    "verdict": "unknown",
                    "score": None,
                    "evaluated_sample_count": 0,
                },
                separators=(",", ":"),
            )
            connection.execute(  # type: ignore[attr-defined]
                text(
                    "UPDATE evaluation_reports SET execution_summary = :execution, "
                    "quality_summary = :quality WHERE id = :id"
                ),
                {"execution": execution_summary, "quality": quality_summary, "id": row[0]},
            )

    @staticmethod
    def _validate_contract_columns(connection: object) -> None:
        expected: dict[str, set[str]] = {
            "dataset_samples": {
                "normalized_schema_version",
                "context_origin",
                "historical_answer",
                "historical_citations",
            },
            "evaluation_jobs": {
                "contract_version",
                "adapter_id",
                "execution_snapshot",
                "quality_status",
                "quality_verdict",
                "quality_score",
            },
            "evaluation_job_samples": {"run_id", "run_snapshot", "quality_status"},
            "evaluation_reports": {
                "schema_version",
                "execution_summary",
                "quality_summary",
                "execution_snapshot",
            },
        }
        inspector = inspect(connection)
        for table_name, column_names in expected.items():
            actual = {column["name"] for column in inspector.get_columns(table_name)}
            missing = column_names - actual
            if missing:
                raise RuntimeError(
                    f"Migration 0002 is recorded but {table_name} is missing: "
                    + ", ".join(sorted(missing))
                )

    def dispose(self) -> None:
        self.engine.dispose()
