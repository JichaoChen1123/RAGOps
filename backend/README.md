# RAGOps backend MVP

This service implements the smallest persistent RAGOps loop:

`dataset -> immutable publish -> evaluation job -> sample results -> report`

The local default is SQLite plus the provider-neutral `mock` adapter. Model network calls are disabled by default, even when provider credentials happen to exist. The same execution port also includes an OpenAI-compatible adapter that is verified offline with injected in-memory HTTP transports.

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

The default database is `sqlite:///./ragops.db`. `ragops init-db` applies the idempotent `0001_mvp_baseline -> 0002_model_execution_contract` migration chain and preserves 1.0 rows. Override settings with `RAGOPS_` environment variables; see `.env.example` for the complete bounded timeout, retry, adapter, and provider configuration.

Useful endpoints:

- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`
- Swagger UI: `http://127.0.0.1:8000/docs`
- Liveness: `http://127.0.0.1:8000/health/live`
- Readiness: `http://127.0.0.1:8000/health/ready`
- Public execution status: `http://127.0.0.1:8000/api/v1/model-execution/status`

Startup, readiness, and execution-status requests never probe a model provider. The status response exposes only configuration booleans and capabilities, not the Base URL, model value, credential, or credential fingerprint.

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

New evaluation requests use `schema_version: "2.0"` and an explicit `execution` object containing the adapter, versioned Prompt, complete generation settings, and context policy. Existing requests without `schema_version` and `execution` remain compatible and normalize to `mock`; legacy model labels never become the actual-model identity. Every accepted job persists an immutable non-secret execution snapshot and an independent run record per sample.

API lifecycle states are `queued`, `running`, `completed`, `failed`, and `cancelled`; execution outcome is `succeeded`, `partial_failed`, or `failed`. Quality status/verdict/score are separate and remain `not_evaluated`/`unknown`/`null` unless an explicit quality gate can evaluate all required metrics. All-failed jobs still have a queryable report.

Review updates accept exactly one of `pending`, `confirmed`, or `dismissed`:

```json
{ "review_status": "confirmed" }
```

The update returns the persisted sample summary, including `review_status` and `reviewed_at`. Passing `pending` clears `reviewed_at`. Review is only available after the job reaches `completed`; unknown samples return `404 RESOURCE_NOT_FOUND` and premature review returns `409 REVIEW_NOT_AVAILABLE`.

The export endpoint returns structured JSON rather than storing a generated file. The frontend can download that payload as JSON or transform the same data into Markdown without another backend round trip.

All validation and domain failures use the stable envelope `error.code`, `error.message`, `error.details`, `error.request_id`, and `error.retryable`; expected bad input never produces an empty 500 response.

## Deterministic evaluation contract

`backend/app/evaluation/` computes deterministic metrics only after the current run answer is persisted. Reports macro-average only `status=ok` values and expose evaluated/excluded/status counts. Provided context is not scored as retrieval, legacy-unknown provenance stays unknown, citation resolution is separate from semantic support, and a missing semantic judge produces no support score.

The rules currently cover retrieval evidence missing, context pollution, citation missing, and rerank regression. Every emitted result includes a versioned rule/profile, reason, evidence, confidence, and suggestions. If required evidence such as pre-rerank rank is absent, the rule emits `not_determinable` with `missing_inputs`.

Dataset contexts may optionally supply `relevance_grade` (0-3), `usefulness`, and `rank_before`; citations may supply `resolved` and `supports_claim`. When optional judgements are absent, gold evidence/document alignment is the deterministic relevance source. Thresholds and retrieval windows live in `EvaluationProfile`, and job metric `k` parameters select the requested retrieval windows.

## MVP boundaries

- SQLite and the in-process FastAPI background task are demo implementations, not a durable production queue.
- `RAGOPS_MODEL_EXTERNAL_CALLS_ENABLED=false` is the safe default and rejects real transport before DNS/socket/retry work. Tests inject transport in process; that path is not selectable through API, environment, or persisted data.
- The `mock` adapter performs local deterministic generation. It never reads reference labels, historical answers, sample metadata, or internal IDs.
- Report export is JSON data only; server-side PDF/Markdown rendering and object storage are deferred.
- In-process FastAPI background tasks are not a durable production queue; Celery/RQ and Redis remain future deployment options.

## Database initialization

`ragops init-db` and automatic local initialization both run the versioned migration chain. A database without migration metadata is stamped at `0001` only after its required MVP tables and columns are verified, then upgraded to `0002`. Repeating the command is a no-op; a partial or unknown schema stops with an error and is never deleted or rebuilt. A fresh database is created directly at migration head.
