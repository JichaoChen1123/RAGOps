from __future__ import annotations

import ipaddress
import os
import re
import subprocess

import uvicorn

from app.codex_bridge.http import create_bridge_app, validate_bridge_token


MINIMUM_CODEX_VERSION = (0, 153, 4)


def validate_bind_policy(host: str, *, allow_non_loopback: bool) -> None:
    try:
        loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = host.lower() == "localhost"
    if not loopback and not allow_non_loopback:
        raise ValueError("non-loopback listening requires --allow-non-loopback")


def read_codex_version() -> tuple[int, int, int]:
    try:
        completed = subprocess.run(
            ["codex", "--version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("codex --version failed; install the official Codex CLI") from exc
    match = re.search(r"\b(\d+)\.(\d+)\.(\d+)\b", completed.stdout)
    if match is None:
        raise RuntimeError("codex --version returned an unsupported format")
    return tuple(int(part) for part in match.groups())


def run_bridge(
    *,
    host: str,
    port: int,
    allow_non_loopback: bool,
    turn_timeout_seconds: float,
) -> None:
    validate_bind_policy(host, allow_non_loopback=allow_non_loopback)
    if not 1 <= port <= 65_535:
        raise ValueError("port must be between 1 and 65535")
    if not 1 <= turn_timeout_seconds <= 600:
        raise ValueError("turn timeout must be between 1 and 600 seconds")
    token = validate_bridge_token(os.environ.get("RAGOPS_CODEX_BRIDGE_TOKEN", ""))
    version = read_codex_version()
    if version < MINIMUM_CODEX_VERSION:
        minimum = ".".join(str(part) for part in MINIMUM_CODEX_VERSION)
        raise RuntimeError(f"Codex CLI {minimum} or newer is required")
    app = create_bridge_app(token)
    uvicorn.run(
        app,
        host=host,
        port=port,
        workers=1,
        access_log=False,
        server_header=False,
    )
