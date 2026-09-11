## Answer score contract: `answer-score-v1`

`strict_em` is 1 only when the stored model answer and a reference are byte-for-byte identical: no trimming or whitespace/punctuation changes.

`normalized_em` applies Unicode NFKC, Latin `casefold`, trims/collapses whitespace, and treats ordinary prose punctuation (including a final full stop) as a boundary. It deliberately preserves numeric meaning: signs, decimal/thousands separators, `%`, and attached units remain tokens, so `1.5` is not `15`, `-2` is not `2`, `10%` is not `10`, and `10kg` is not `10g`.

`chinese_answer_f1` tokenizes the normalized string: semantic numeric chunks and Latin/ASCII words stay whole, Han characters are individual tokens, and other punctuation is a boundary. It is multiset precision/recall F1; both empty is 1 and exactly one empty is 0.

Inputs accept one reference string for compatibility or a list. Each metric independently selects its maximum reference score and persists `matched_reference_index`; the reference data is never changed. An empty reference list is `not_applicable`, not a zero score.

## Offline rescoring persistence and states

Migration `0003_answer_score_rescore` adds append-only `answer_rescores`. Every row links the original job, job sample and dataset sample, copies the stored generated answer and reference list, and carries the algorithm version and metric results. It never overwrites `evaluation_job_samples.metric_results`, answers, or references. The `ragops rescore` command only reads those records and writes these score rows; it imports neither adapter nor executor code.

Quality state is explicit: `metrics_calculated` means stored metrics exist. `quality_gate_not_configured`, `quality_gate_configured_pending`, and `quality_gate_evaluated` respectively distinguish no configured gate, configured-but-not-yet-evaluated, and evaluated gate; no pass/fail is invented for the first two.

## Local offline operation

All commands below use the configured `RAGOPS_DATABASE_URL` and can be run from the repository root:

```powershell
# Migrate (the only command here that changes the schema)
uv run --project backend ragops init-db

# Read-only preflight. A missing or unmigrated SQLite database exits with
# "run ragops init-db first" and is not created or changed.
uv run --project backend ragops rescore --job-id <job-id> --dry-run

# Append a new score batch; existing answers and score rows remain unchanged.
uv run --project backend ragops rescore --job-id <job-id>

# JSON-only stored-result queries, optionally isolated to one batch.
uv run --project backend ragops rescore-list --job-id <job-id>
uv run --project backend ragops rescore-list --job-id <job-id> --batch-id <batch-id>
```

For API consumers, `GET /api/v1/evaluation-jobs/<job-id>/answer-rescores` accepts an optional `?batch_id=<batch-id>` and returns only that job's records; an unrelated batch ID returns an empty list rather than leaking another job. `skipped` and `failed` rows include `failure_reason`. Rescoring is append-only and uses persisted answers/references only: it never overwrites prior scores and does not invoke model adapters, executors, or external models.
