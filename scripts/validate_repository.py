"""Cross-platform validation for repository docs, fixtures, and YAML files."""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path
from urllib.parse import unquote

import yaml

ROOT = Path(__file__).resolve().parents[1]
IGNORED_PARTS = {
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "coverage",
    "dist",
    "node_modules",
}
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


class ValidationError(RuntimeError):
    """Raised when a repository contract is invalid."""


def repository_files(pattern: str) -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob(pattern)
        if not IGNORED_PARTS.intersection(path.relative_to(ROOT).parts)
    )


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def validate_markdown() -> int:
    files = repository_files("*.md")
    require(bool(files), "repository must contain Markdown documentation")

    for path in files:
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(ROOT)
        require(bool(text.strip()), f"{relative}: Markdown file is empty")
        require(text.endswith("\n"), f"{relative}: file must end with a newline")

        for line_number, line in enumerate(text.splitlines(), start=1):
            require(line == line.rstrip(), f"{relative}:{line_number}: trailing whitespace")

        for raw_target in MARKDOWN_LINK.findall(text):
            target = raw_target.strip().strip("<>").split(maxsplit=1)[0]
            if target.startswith(("#", "http://", "https://", "mailto:", "mention://")):
                continue
            file_part = unquote(target.split("#", maxsplit=1)[0])
            if not file_part:
                continue
            resolved = (path.parent / file_part).resolve()
            require(resolved.is_relative_to(ROOT), f"{relative}: link escapes repository: {target}")
            require(resolved.exists(), f"{relative}: broken local link: {target}")

    return len(files)


def validate_structured_files() -> tuple[int, int, int]:
    json_files = repository_files("*.json")
    jsonl_files = repository_files("*.jsonl")
    yaml_files = repository_files("*.yml") + repository_files("*.yaml")

    for path in json_files:
        with path.open(encoding="utf-8") as stream:
            json.load(stream)

    for path in jsonl_files:
        with path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if line.strip():
                    try:
                        json.loads(line)
                    except json.JSONDecodeError as error:
                        relative = path.relative_to(ROOT)
                        raise ValidationError(f"{relative}:{line_number}: {error}") from error

    for path in yaml_files:
        with path.open(encoding="utf-8") as stream:
            yaml.safe_load(stream)

    return len(json_files), len(jsonl_files), len(yaml_files)


def load_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def require_unique(values: list[object], name: str) -> None:
    require(len(values) == len(set(values)), f"{name} contains duplicate values")


def validate_fixtures() -> tuple[int, int, int]:
    fixture_root = ROOT / "examples" / "eval-samples"
    valid_samples = load_jsonl(fixture_root / "valid-samples.jsonl")
    invalid_cases = load_jsonl(fixture_root / "invalid-samples.jsonl")
    metric_document = json.loads((fixture_root / "metric-cases.json").read_text(encoding="utf-8"))
    metric_cases = metric_document["cases"]

    require(len(valid_samples) == 6, "valid-samples.jsonl must contain 6 baseline samples")
    require(len(invalid_cases) == 9, "invalid-samples.jsonl must contain 9 validation cases")
    require(len(metric_cases) == 8, "metric-cases.json must contain 8 metric cases")
    require_unique([sample["sample_id"] for sample in valid_samples], "sample_id")
    require_unique([case["case_id"] for case in invalid_cases], "invalid case_id")
    require_unique([case["case_id"] for case in metric_cases], "metric case_id")

    for sample in valid_samples:
        sample_id = sample["sample_id"]
        require(bool(str(sample.get("schema_version", "")).strip()), f"{sample_id}: schema_version")
        require(bool(str(sample_id).strip()), "sample_id is required")
        require(bool(str(sample.get("question", "")).strip()), f"{sample_id}: question is required")
        contexts = sample["retrieved_contexts"]
        ranks = [context["rank"] for context in contexts]
        require(ranks == list(range(1, len(ranks) + 1)), f"{sample_id}: ranks must be contiguous")
        chunk_ids = [context["chunk_id"] for context in contexts]
        require_unique(chunk_ids, f"{sample_id} chunk_id")
        for citation in sample["citations"]:
            require(citation["chunk_id"] in chunk_ids, f"{sample_id}: unresolved citation")

    for invalid_case in invalid_cases:
        case_id = invalid_case["case_id"]
        require(bool(str(invalid_case.get("expected_error", "")).strip()), f"{case_id}: expected_error")
        require(invalid_case.get("input") is not None, f"{case_id}: input is required")

    by_id = {case["case_id"]: case for case in metric_cases}
    tolerance = float(metric_document["float_tolerance"])
    ranked_mixed = by_id["ranked-mixed"]
    expected_ndcg = (1 / math.log2(3)) / (1 + 1 / math.log2(3))
    require(
        math.isclose(expected_ndcg, ranked_mixed["expected"]["at_3"]["ndcg"], abs_tol=tolerance),
        "ranked-mixed NDCG@3 oracle is inconsistent",
    )
    require(
        math.isclose(ranked_mixed["expected"]["at_4"]["recall"], 1.0, abs_tol=tolerance),
        "ranked-mixed Recall@4 oracle is inconsistent",
    )

    context_partial = by_id["context-partial"]["expected"]
    require(
        math.isclose(context_partial["context_precision"], (1 + 2 / 3) / 2, abs_tol=tolerance),
        "context precision oracle is inconsistent",
    )
    require(
        math.isclose(context_partial["context_recall"], 2 / 3, abs_tol=tolerance),
        "context recall oracle is inconsistent",
    )

    operational = by_id["latency-and-cost-missing"]["expected"]
    require(
        math.isclose(operational["latency"]["mean_ms"], (100 + 200 + 1000) / 3, abs_tol=tolerance),
        "latency mean oracle is inconsistent",
    )
    require(
        math.isclose(operational["cost"]["total_amount"], 0.01 + 0.03, abs_tol=tolerance),
        "cost oracle is inconsistent",
    )

    return len(valid_samples), len(invalid_cases), len(metric_cases)


def main() -> int:
    try:
        markdown_count = validate_markdown()
        json_count, jsonl_count, yaml_count = validate_structured_files()
        valid_count, invalid_count, metric_count = validate_fixtures()
    except (OSError, KeyError, TypeError, ValidationError, json.JSONDecodeError, yaml.YAMLError) as error:
        print(f"Repository validation failed: {error}", file=sys.stderr)
        return 1

    print(
        "Repository validation passed: "
        f"{markdown_count} Markdown, {json_count} JSON, {jsonl_count} JSONL, "
        f"{yaml_count} YAML files; fixtures={valid_count}/{invalid_count}/{metric_count}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
