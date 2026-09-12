"""Convert the official CMRC2018 dev set to deterministic RAGOps v2 fixtures.

The converter deliberately only carries official question/answer annotations and
the corresponding source paragraph.  It never reads model outputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import unicodedata
from collections.abc import Iterable
from pathlib import Path
from typing import Any


DEBUG_NAME = "cmrc2018_debug20_v2.jsonl"
HOLDOUT_NAME = "cmrc2018_holdout30_v2.jsonl"
DEFAULT_SEED = 20260912


def _canonical(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def _digest(value: str, length: int = 24) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _legacy_exclusions(path: Path) -> tuple[set[str], set[str]]:
    questions: set[str] = set()
    contexts: set[str] = set()
    for row in _read_jsonl(path):
        if isinstance(row.get("question"), str):
            questions.add(_canonical(row["question"]))
        for context in row.get("contexts", []):
            if isinstance(context, dict) and isinstance(context.get("text"), str):
                contexts.add(_canonical(context["text"]))
    return questions, contexts


def _official_rows(source: Path) -> Iterable[dict[str, Any]]:
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload.get("data"), list):
        raise ValueError("CMRC2018 source must contain a data array")
    for article in payload["data"]:
        for paragraph in article.get("paragraphs", []):
            text = paragraph.get("context")
            if not isinstance(text, str) or not text:
                continue
            for qa in paragraph.get("qas", []):
                question, official_id = qa.get("question"), qa.get("id")
                answers = qa.get("answers", [])
                if not isinstance(question, str) or not question.strip() or not isinstance(official_id, str) or not official_id:
                    continue
                references = []
                for answer in answers:
                    value = answer.get("text") if isinstance(answer, dict) else None
                    # CMRC annotations occasionally include a malformed offset or
                    # answer text.  Only retain official annotations that can be
                    # located in this exact paragraph; do not synthesize fixes.
                    start = answer.get("answer_start") if isinstance(answer, dict) else None
                    locatable = (
                        isinstance(start, int) and text[start:start + len(value)] == value
                        if isinstance(value, str) else False
                    )
                    if isinstance(value, str) and value and locatable and value not in references:
                        references.append(value)
                if references:
                    yield {
                        "article_id": str(article.get("id", "")),
                        "title": str(article.get("title", "")),
                        "paragraph_id": str(paragraph.get("id", "")),
                        "context": text,
                        "official_id": official_id,
                        "question": question.strip(),
                        "reference_answers": references,
                    }


def _sample(row: dict[str, Any]) -> dict[str, Any]:
    context = row["context"]
    content_key = _digest(context)
    official_id = row["official_id"]
    references = row["reference_answers"]
    return {
        "schema_version": "2.0",
        "sample_id": f"cmrc2018-dev-{official_id}",
        "question": row["question"],
        "labels": {
            "reference_answer": references[0],
            "gold_document_ids": [f"cmrc2018-dev-doc-{content_key}"],
            "gold_evidence_ids": [],
            "expected_diagnoses": [],
        },
        "contexts": [{
            "origin": "provided", "rank": 1, "rank_before": None,
            "retrieval_run_id": None, "doc_id": f"cmrc2018-dev-doc-{content_key}",
            "chunk_id": f"cmrc2018-dev-chunk-{content_key}", "evidence_ids": [],
            "text": context, "score": None, "relevance_grade": None, "usefulness": None,
        }],
        "historical_output": None,
        "tags": ["cmrc2018", "dev", "provided-context", "zh-CN"],
        "metadata": {
            "source": "CMRC2018 official dev", "source_id": official_id,
            "article_id": row["article_id"], "paragraph_id": row["paragraph_id"],
            "title": row["title"], "reference_answers": references,
        },
    }


def validate_samples(debug: list[dict[str, Any]], holdout: list[dict[str, Any]],
                     excluded_questions: set[str], excluded_contexts: set[str]) -> None:
    """Validate the v2 contract and CMRC-specific split invariants."""
    if len(debug) != 20 or len(holdout) != 30:
        raise ValueError("expected exactly 20 debug samples and 30 holdout samples")
    combined = debug + holdout
    sample_ids = [sample.get("sample_id") for sample in combined]
    questions = [sample.get("question") for sample in combined]
    if len(sample_ids) != len(set(sample_ids)) or len(questions) != len(set(questions)):
        raise ValueError("sample IDs and questions must be unique")
    debug_contexts = {sample["contexts"][0]["text"] for sample in debug}
    holdout_contexts = {sample["contexts"][0]["text"] for sample in holdout}
    if debug_contexts & holdout_contexts:
        raise ValueError("debug and holdout must not share source paragraphs")
    for sample in combined:
        labels, contexts, metadata = sample.get("labels"), sample.get("contexts"), sample.get("metadata")
        if sample.get("schema_version") != "2.0" or not isinstance(labels, dict) or not isinstance(contexts, list) or not contexts:
            raise ValueError("sample has missing required v2 fields")
        context = contexts[0]
        if context.get("origin") != "provided" or context.get("text") in (None, ""):
            raise ValueError("context must be non-empty and origin=provided")
        if _canonical(sample["question"]) in excluded_questions or _canonical(context["text"]) in excluded_contexts:
            raise ValueError("legacy question or source paragraph was selected")
        references = metadata.get("reference_answers") if isinstance(metadata, dict) else None
        if not isinstance(references, list) or not references or labels.get("reference_answer") != references[0]:
            raise ValueError("reference answers do not satisfy the multi-reference contract")
        if any(not isinstance(answer, str) or not answer or answer not in context["text"] for answer in references):
            raise ValueError("every official reference answer must occur in its source paragraph")


def convert(source: Path, legacy_exclusions: Path, output_dir: Path, seed: int = DEFAULT_SEED) -> dict[str, Any]:
    excluded_questions, excluded_contexts = _legacy_exclusions(legacy_exclusions)
    groups: dict[str, list[dict[str, Any]]] = {}
    seen_questions: set[str] = set()
    for row in _official_rows(source):
        context, question = _canonical(row["context"]), _canonical(row["question"])
        if context in excluded_contexts or question in excluded_questions or question in seen_questions:
            continue
        seen_questions.add(question)
        groups.setdefault(context, []).append(row)
    group_keys = sorted(groups)
    random.Random(seed).shuffle(group_keys)
    selected: list[dict[str, Any]] = []
    debug: list[dict[str, Any]] = []
    holdout: list[dict[str, Any]] = []
    for key in group_keys:
        candidates = sorted(groups[key], key=lambda item: item["official_id"])
        # Consume each paragraph atomically: a group goes to only one split.
        target = debug if len(debug) < 20 else holdout
        needed = 20 if target is debug else 30
        if len(target) + len(candidates) <= needed:
            target.extend(candidates)
            selected.extend(candidates)
        if len(debug) == 20 and len(holdout) == 30:
            break
    if len(debug) != 20 or len(holdout) != 30:
        raise ValueError("insufficient whole paragraph groups to form 20/30 split")
    debug_samples = [_sample(row) for row in debug]
    holdout_samples = [_sample(row) for row in holdout]
    validate_samples(debug_samples, holdout_samples, excluded_questions, excluded_contexts)
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, samples in ((DEBUG_NAME, debug_samples), (HOLDOUT_NAME, holdout_samples)):
        (output_dir / name).write_text("".join(json.dumps(sample, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for sample in samples), encoding="utf-8", newline="\n")
    return {"debug": debug_samples, "holdout": holdout_samples, "source_groups": len({row["context"] for row in selected})}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="official cmrc2018_dev.json")
    parser.add_argument("--exclude", type=Path, required=True, help="legacy JSONL to exclude")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()
    result = convert(args.input, args.exclude, args.output_dir, args.seed)
    print(f"wrote {DEBUG_NAME}=20 and {HOLDOUT_NAME}=30; selected paragraph groups={result['source_groups']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
