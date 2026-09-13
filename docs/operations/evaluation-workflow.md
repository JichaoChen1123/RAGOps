# Evaluation workflow

1. Create a draft dataset, then import JSONL samples after client-side validation.
2. Review the draft and publish it explicitly; importing never publishes or starts a job.
3. In **New evaluation**, choose all samples or a non-empty subset, then review the model, Prompt and displayed sample count before submitting.
4. A job stores its selected dataset-sample IDs in `execution_snapshot.selection`; report and progress counts are calculated from the resulting job-sample rows only.

## Local JSONL import

Use **Import data** to drop or choose a UTF-8 `.jsonl` file. The browser accepts BOM, LF and CRLF, validates every non-empty row against the v2 import shape, and shows the line number before it makes any write request. The confirmation screen shows the sample total and a short question preview. It preserves contexts, labels, `reference_answers`, historical output and source metadata. Confirmation creates a draft and imports samples; publishing remains a separate action. If the sample import is interrupted after draft creation, retry the import action to continue with the recorded dataset ID rather than create another draft.

Browsing a report card writes `viewed_at` and `viewed_by` on that job's `evaluation_job_samples` row. The key is job + job-sample, so records are isolated between jobs. It is retained with the evaluation database lifecycle and is deliberately unrelated to `review_status`, answers, metrics, diagnoses, and quality verdicts.

## Interrupted import recovery

After a draft has been created, the browser retains its ID and a normalized copy of the selected import in project-scoped local storage. Retrying first reads the server draft: a semantic match completes without another write, an empty draft may receive the retry, and a partial or different draft stops for manual review. The recovery entry is cleared only after verification or an explicit abandon action.
