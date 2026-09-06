"""Windows-hosted Codex App Server bridge for the Docker backend."""

from app.codex_bridge.http import create_bridge_app

__all__ = ["create_bridge_app"]
