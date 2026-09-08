## Answer score contract: `answer-score-v1`

`strict_em` is 1 only when the stored model answer and a reference are byte-for-byte identical: no trimming or whitespace/punctuation changes.

`normalized_em` applies Unicode NFKC, Latin `casefold`, trims/collapses whitespace, and treats ordinary prose punctuation (including a final full stop) as a boundary. It deliberately preserves numeric meaning: signs, decimal/thousands separators, `%`, and attached units remain tokens, so `1.5` is not `15`, `-2` is not `2`, `10%` is not `10`, and `10kg` is not `10g`.

`chinese_answer_f1` tokenizes the normalized string: semantic numeric chunks and Latin/ASCII words stay whole, Han characters are individual tokens, and other punctuation is a boundary. It is multiset precision/recall F1; both empty is 1 and exactly one empty is 0.

Inputs accept one reference string for compatibility or a list. Each metric independently selects its maximum reference score and persists `matched_reference_index`; the reference data is never changed. An empty reference list is `not_applicable`, not a zero score.

## Offline rescoring persistence and states

Migration `0003_answer_score_rescore` adds append-only `answer_rescores`. Every row links the original job, job sample and dataset sample, copies the stored generated answer and reference list, and carries the algorithm version and metric results. It never overwrites `evaluation_job_samples.metric_results`, answers, or references. The `ragops rescore` command only reads those records and writes these score rows; it imports neither adapter nor executor code.

Quality state is explicit: `metrics_calculated` means metrics exist and no gate was configured; `quality_gate_evaluated` has a pass/fail verdict; `quality_gate_not_configured` has no synthetic verdict. Existing API `quality_status=not_evaluated` means not a gate result, not missing metrics.
