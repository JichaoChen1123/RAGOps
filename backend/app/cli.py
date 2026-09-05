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
    args = parser.parse_args()

    if args.command == "init-db":
        init_db()


if __name__ == "__main__":
    main()
