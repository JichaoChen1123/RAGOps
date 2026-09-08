from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

import uvicorn

from app.codex_bridge.app import BridgeConfig, create_bridge_app
from app.core.config import get_settings
from app.persistence.db import Database
from app.services.rescore import rescore_job
from app.services.jobs import list_answer_rescores


MINIMUM_CODEX_VERSION = (0, 153, 4)


def read_codex_version(executable: str = "codex") -> tuple[int, int, int]:
    try:
        completed = subprocess.run(
            [executable, "--version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise SystemExit("Codex CLI is not installed or `codex --version` failed.") from exc
    match = re.search(r"\b(\d+)\.(\d+)\.(\d+)\b", completed.stdout)
    if match is None:
        raise SystemExit("Codex CLI returned an unsupported version format.")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def init_db() -> None:
    settings = get_settings()
    database = Database(settings.database_url)
    try:
        applied = database.migrate()
    finally:
        database.dispose()
    suffix = ", ".join(applied) if applied else "already at head"
    print(f"Initialized database schema for {settings.database_url}: {suffix}")


def run_codex_bridge(args: argparse.Namespace) -> None:
    settings = get_settings()
    if settings.codex_bridge_token is None:
        raise SystemExit("RAGOPS_CODEX_BRIDGE_TOKEN is required (minimum 32 characters).")
    if args.host not in {"127.0.0.1", "::1", "localhost"} and not args.allow_non_loopback:
        raise SystemExit("Non-loopback binding requires --allow-non-loopback and bridge authentication.")
    default_root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "RAGOps" / "codex-sandbox"
    default_codex_home = (
        Path(os.environ.get("LOCALAPPDATA", Path.home())) / "RAGOps" / "codex-bridge-home"
    )
    codex_home = Path(args.codex_home or default_codex_home).resolve()
    daily_homes = {Path.home().joinpath(".codex").resolve()}
    inherited_codex_home = os.environ.get("CODEX_HOME")
    if inherited_codex_home:
        daily_homes.add(Path(inherited_codex_home).resolve())
    if codex_home in daily_homes:
        raise SystemExit(
            "The bridge requires a dedicated CODEX_HOME; do not use the daily Codex config home."
        )
    config = BridgeConfig(
        access_token=settings.codex_bridge_token,
        sandbox_root=Path(args.sandbox_root or default_root),
        codex_home=codex_home,
        codex_executable=args.codex_executable,
        request_timeout_seconds=args.timeout_seconds,
    )
    installed_version = read_codex_version(args.codex_executable)
    if installed_version < MINIMUM_CODEX_VERSION:
        minimum = ".".join(str(part) for part in MINIMUM_CODEX_VERSION)
        raise SystemExit(f"Codex CLI {minimum} or newer is required by this bridge.")
    uvicorn.run(
        create_bridge_app(config),
        host=args.host,
        port=args.port,
        access_log=False,
        server_header=False,
    )


def run_rescore(args: argparse.Namespace) -> None:
    """Use persisted answers only; no adapter/executor is reachable from this command."""
    settings = get_settings()
    database = Database(settings.database_url)
    try:
        if args.dry_run:
            from sqlalchemy import inspect
            required = {"evaluation_jobs", "evaluation_job_samples", "dataset_samples", "answer_rescores"}
            if not required.issubset(set(inspect(database.engine).get_table_names())):
                raise SystemExit("dry-run requires an already migrated database; run ragops init-db first")
        else:
            database.migrate()
        with database.session() as session:
            summary = rescore_job(session, args.job_id, dry_run=args.dry_run)
        print(json.dumps(summary.__dict__, ensure_ascii=False, default=str))
    finally:
        database.dispose()


def run_rescore_list(args: argparse.Namespace) -> None:
    """Read-only JSON export of persisted scoring; never migrates or scores."""
    settings = get_settings()
    database = Database(settings.database_url)
    try:
        with database.session() as session:
            rows = list_answer_rescores(session, args.job_id, args.batch_id)
        print(json.dumps([row.model_dump(mode="json") for row in rows], ensure_ascii=False))
    finally:
        database.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(prog="ragops")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init-db", help="migrate the database schema to head")
    rescore = subparsers.add_parser("rescore", help="offline append-only answer scoring")
    rescore.add_argument("--job-id", required=True)
    rescore.add_argument("--dry-run", action="store_true", help="preflight without writes")
    rescore_list = subparsers.add_parser("rescore-list", help="export stored answer rescoring JSON")
    rescore_list.add_argument("--job-id", required=True)
    rescore_list.add_argument("--batch-id")
    bridge = subparsers.add_parser(
        "codex-bridge", help="run the authenticated host bridge for Codex ChatGPT access"
    )
    bridge.add_argument("--host", default="127.0.0.1")
    bridge.add_argument("--port", type=int, default=8765)
    bridge.add_argument("--sandbox-root")
    bridge.add_argument("--codex-home")
    bridge.add_argument("--codex-executable", default="codex")
    bridge.add_argument("--timeout-seconds", type=float, default=180.0)
    bridge.add_argument("--allow-non-loopback", action="store_true")
    args = parser.parse_args()

    if args.command == "init-db":
        init_db()
    elif args.command == "rescore":
        run_rescore(args)
    elif args.command == "rescore-list":
        run_rescore_list(args)
    elif args.command == "codex-bridge":
        run_codex_bridge(args)


if __name__ == "__main__":
    main()
