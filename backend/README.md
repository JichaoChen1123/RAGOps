# RAGOps backend MVP

This service implements the smallest persistent RAGOps loop:

`dataset -> immutable publish -> evaluation job -> sample results -> report`

The local default is SQLite plus a deterministic in-process executor. It computes auditable RAG metrics and evidence-backed MVP diagnoses without an external LLM judge. The execution contract remains isolated so a queue-backed worker can replace local orchestration later.

For full repository setup, Docker startup, environment variables, frontend usage, and troubleshooting, see [`../docs/quickstart.md`](../docs/quickstart.md).

## Requirements

- Python 3.11 or newer (the target production baseline is Python 3.12)
- [`uv`](https://docs.astral.sh/uv/) for the commands below

## Install and test

Run from the repository root:

```bash
uv sync --project backend --extra dev --frozen
uv run --project backend pytest -c backend/pyproject.toml tests/backend tests/evaluation -q
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
6. `PATCH /evaluation-jobs/{job_id}/samples/{sample_id}/review` persists a diagnosis review decision.
7. `GET /evaluation-jobs/{job_id}/report/export` returns a JSON export bundle containing the report and its sample summaries.

Creation accepts `Idempotency-Key`. Reusing the key with the same request returns the original job; reusing it with different input returns `409 IDEMPOTENCY_KEY_CONFLICT`.

## MVP write contracts

Dataset creation requires a non-blank `name` and `owner`. `description` is optional, and `version` defaults to `v1`. A small demo can create and import in one atomic request by supplying `samples`; the response reports both `sample_count` and `imported_samples`. The separate sample import endpoint remains available for larger batches.

```json
{
  "name": "support-regression",
  "description": "Synthetic support cases",
  "owner": "quality-platform",
  "version": "2026.08",
  "samples": []
}
```

Evaluation creation accepts `dataset_id`, optional `name`, `model_version`, `prompt_version`, and metric configuration. `config_version` can still be supplied by existing clients; otherwise it is derived from the model and prompt versions. API lifecycle states are `queued`, `running`, `completed`, `failed`, and `cancelled`. A completed job exposes an `outcome` of `succeeded` or `partial_failed`, so lifecycle progress is not conflated with result quality.

Review updates accept exactly one of `pending`, `confirmed`, or `dismissed`:

```json
{ "review_status": "confirmed" }
```

The update returns the persisted sample summary, including `review_status` and `reviewed_at`. Passing `pending` clears `reviewed_at`. Review is only available after the job reaches `completed`; unknown samples return `404 RESOURCE_NOT_FOUND` and premature review returns `409 REVIEW_NOT_AVAILABLE`.

The export endpoint returns structured JSON rather than storing a generated file. The frontend can download that payload as JSON or transform the same data into Markdown without another backend round trip.

All validation and domain failures use the stable envelope `error.code`, `error.message`, `error.details`, `error.request_id`, and `error.retryable`; expected bad input never produces an empty 500 response.

## Deterministic evaluation contract

`backend/app/evaluation/` computes sample-level Recall@K, reciprocal rank, NDCG@K, context precision/recall/relevance ratio, citation hit rate, and normalized reference exact match. Reports macro-average only `status=ok` values and expose evaluated/excluded counts; missing gold, citations, answers, or judgements return `not_applicable` rather than a fabricated zero.

The rules currently cover retrieval evidence missing, context pollution, citation missing, and rerank regression. Every emitted result includes a versioned rule/profile, reason, evidence, confidence, and suggestions. If required evidence such as pre-rerank rank is absent, the rule emits `not_determinable` with `missing_inputs`.

Dataset contexts may optionally supply `relevance_grade` (0-3), `usefulness`, and `rank_before`; citations may supply `resolved` and `supports_claim`. When optional judgements are absent, gold evidence/document alignment is the deterministic relevance source. Thresholds and retrieval windows live in `EvaluationProfile`, and job metric `k` parameters select the requested retrieval windows.

## MVP boundaries

- SQLite and the in-process FastAPI background task are demo implementations, not a durable production queue.
- The deterministic executor performs local auditable metrics only; it does not call an LLM or vector database.
- Report export is JSON data only; server-side PDF/Markdown rendering and object storage are deferred.
- `create_all` bootstraps a fresh local schema. Versioned migrations are required before evolving a shared or production database.

## Database initialization

`ragops init-db` creates the MVP schema from SQLAlchemy metadata. Automatic creation is enabled by default for local use and tests (`RAGOPS_AUTO_CREATE_SCHEMA=true`). Production deployment should disable it and replace this bootstrap path with versioned Alembic migrations before schema evolution begins.
