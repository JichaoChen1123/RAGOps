from __future__ import annotations

import argparse

from app.core.config import get_settings
from app.persistence.db import Database


def init_db() -> None:
    settings = get_settings()
    database = Database(settings.database_url)
    try:
        applied = database.migrate()
    finally:
        database.dispose()
    suffix = ", ".join(applied) if applied else "already at head"
    print(f"Initialized database schema for {settings.database_url}: {suffix}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="ragops")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init-db", help="migrate the database schema to head")
    bridge = subparsers.add_parser(
        "codex-bridge",
        help="run the authenticated Windows-hosted Codex App Server bridge",
    )
    bridge.add_argument("--host", default="127.0.0.1")
    bridge.add_argument("--port", type=int, default=8765)
    bridge.add_argument("--allow-non-loopback", action="store_true")
    bridge.add_argument("--turn-timeout-seconds", type=float, default=120.0)
    args = parser.parse_args()

    if args.command == "init-db":
        init_db()
    elif args.command == "codex-bridge":
        from app.codex_bridge.cli import run_bridge

        run_bridge(
            host=args.host,
            port=args.port,
            allow_non_loopback=args.allow_non_loopback,
            turn_timeout_seconds=args.turn_timeout_seconds,
        )


if __name__ == "__main__":
    main()
