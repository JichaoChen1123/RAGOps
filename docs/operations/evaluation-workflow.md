# Evaluation workflow

1. Create a draft dataset, then import JSONL samples after client-side validation.
2. Review the draft and publish it explicitly; importing never publishes or starts a job.
3. In **New evaluation**, choose all samples or a non-empty subset, then review the model, Prompt and displayed sample count before submitting.
4. A job stores its selected dataset-sample IDs in `execution_snapshot.selection`; report and progress counts are calculated from the resulting job-sample rows only.

Browsing a report card writes `viewed_at` and `viewed_by` on that job's `evaluation_job_samples` row. The key is job + job-sample, so records are isolated between jobs. It is retained with the evaluation database lifecycle and is deliberately unrelated to `review_status`, answers, metrics, diagnoses, and quality verdicts.
