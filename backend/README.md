# RAGOps backend MVP

This service implements the smallest persistent RAGOps loop:

`dataset -> immutable publish -> evaluation job -> sample results -> report`

The local default is SQLite plus a deterministic in-process executor. The executor only proves orchestration and persistence; `execution_success_rate` is an operational placeholder, not a RAG quality metric. The execution contract is isolated so a queue-backed worker and real evaluators can replace it later.

## Requirements

- Python 3.11 or newer (the target production baseline is Python 3.12)
- [`uv`](https://docs.astral.sh/uv/) for the commands below

## Install and test

Run from the repository root:

```bash
uv sync --project backend --extra dev
uv run --project backend pytest tests/backend -q
```

Initialize a persistent local database and start the API:

```bash
uv run --project backend ragops init-db
uv run --project backend uvicorn app.main:app --app-dir backend --reload
```

The default database is `sqlite:///./ragops.db`. Override settings with `RAGOPS_` environment variables, for example `RAGOPS_DATABASE_URL` and `RAGOPS_LOG_LEVEL`.

Useful endpoints:

- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`
- Swagger UI: `http://127.0.0.1:8000/docs`
- Liveness: `http://127.0.0.1:8000/health/live`
- Readiness: `http://127.0.0.1:8000/health/ready`

## Minimal API loop

All resource APIs use the `/api/v1` prefix.

1. `POST /datasets` creates a draft dataset.
2. `POST /datasets/{dataset_id}/samples:import` atomically imports samples.
3. `POST /datasets/{dataset_id}:publish` freezes the dataset.
4. `POST /evaluation-jobs` returns `202` and a `queued` snapshot. The local background executor advances it through `running` to a terminal state.
5. `GET /evaluation-jobs/{job_id}`, `/samples`, and `/report` return persisted status and results.

Creation accepts `Idempotency-Key`. Reusing the key with the same request returns the original job; reusing it with different input returns `409 IDEMPOTENCY_KEY_CONFLICT`.

## Database initialization

`ragops init-db` creates the MVP schema from SQLAlchemy metadata. Automatic creation is enabled by default for local use and tests (`RAGOPS_AUTO_CREATE_SCHEMA=true`). Production deployment should disable it and replace this bootstrap path with versioned Alembic migrations before schema evolution begins.
