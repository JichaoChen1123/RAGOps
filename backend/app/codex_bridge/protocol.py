from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Mapping, Sequence
from typing import Any


DISABLED_FEATURES = (
    "apps",
    "auth_elicitation",
    "browser_use",
    "browser_use_external",
    "browser_use_full_cdp_access",
    "computer_use",
    "enable_mcp_apps",
    "hooks",
    "image_generation",
    "in_app_browser",
    "in_app_chat",
    "in_app_local_automation",
    "memories",
    "multi_agent",
    "multi_agent_v2",
    "plugin_sharing",
    "plugins",
    "recommended_plugins",
    "remote_plugin",
    "shell_tool",
    "skill_mcp_dependency_install",
    "skill_search",
    "sleep_tool",
    "tool_call_mcp_elicitation",
    "tool_suggest",
    "unified_exec",
    "view_image",
    "workspace_dependencies",
)
_SENSITIVE_CHILD_ENVIRONMENT = {
    "ANTHROPIC_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "OPENAI_API_KEY",
}


def app_server_command() -> tuple[str, ...]:
    command = [
        "codex",
        "app-server",
        "--stdio",
        "--strict-config",
        "-c",
        'web_search="disabled"',
        "-c",
        "mcp_servers={}",
    ]
    for feature in DISABLED_FEATURES:
        command.extend(("--disable", feature))
    return tuple(command)


class CodexProtocolError(RuntimeError):
    pass


class CodexRpcError(CodexProtocolError):
    def __init__(self, code: int | None) -> None:
        super().__init__("Codex App Server rejected the request")
        self.code = code


class CodexAppServerClient:
    """Minimal JSONL client; raw App Server output is never exposed over HTTP."""

    def __init__(
        self,
        *,
        command: Sequence[str] | None = None,
        environment: Mapping[str, str] | None = None,
        initialize_timeout_seconds: float = 10.0,
    ) -> None:
        self.command = tuple(command or app_server_command())
        self.environment = dict(environment or {})
        self.initialize_timeout_seconds = initialize_timeout_seconds
        self.process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._pending: dict[int, asyncio.Future[object]] = {}
        self._next_id = 1
        self._closing = False

    async def __aenter__(self) -> CodexAppServerClient:
        await self.start()
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.close()

    async def start(self) -> None:
        if self.process is not None:
            raise CodexProtocolError("Codex App Server client was already started")
        environment = os.environ.copy()
        environment.update(self.environment)
        for name in list(environment):
            if name.upper().startswith("RAGOPS_") or name.upper() in _SENSITIVE_CHILD_ENVIRONMENT:
                environment.pop(name, None)
        self.process = await asyncio.create_subprocess_exec(
            *self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=environment,
        )
        self._reader_task = asyncio.create_task(self._read_messages())
        self._stderr_task = asyncio.create_task(self._discard_stderr())
        try:
            await self.request(
                "initialize",
                {
                    "clientInfo": {
                        "name": "ragops_codex_bridge",
                        "title": "RAGOps Codex Bridge",
                        "version": "1.0.0",
                    },
                    "capabilities": {
                        "experimentalApi": False,
                        "requestAttestation": False,
                    },
                },
                timeout_seconds=self.initialize_timeout_seconds,
            )
            await self.notify("initialized", {})
        except Exception:
            await self.close()
            raise

    async def request(
        self,
        method: str,
        params: Mapping[str, object] | None = None,
        *,
        timeout_seconds: float = 10.0,
    ) -> object:
        process = self._require_process()
        if process.stdin is None:
            raise CodexProtocolError("Codex App Server stdin is unavailable")
        request_id = self._next_id
        self._next_id += 1
        future: asyncio.Future[object] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        message: dict[str, object] = {"method": method, "id": request_id}
        if params is not None:
            message["params"] = dict(params)
        try:
            await self._write(message)
            return await asyncio.wait_for(future, timeout=timeout_seconds)
        finally:
            self._pending.pop(request_id, None)

    async def notify(self, method: str, params: Mapping[str, object]) -> None:
        await self._write({"method": method, "params": dict(params)})

    async def read_event(self, *, timeout_seconds: float) -> dict[str, Any]:
        return await asyncio.wait_for(self._events.get(), timeout=timeout_seconds)

    async def interrupt(self, thread_id: str, turn_id: str) -> None:
        await self.request(
            "turn/interrupt",
            {"threadId": thread_id, "turnId": turn_id},
            timeout_seconds=2.0,
        )

    async def close(self) -> None:
        if self.process is None:
            return
        self._closing = True
        process = self.process
        if process.stdin is not None:
            process.stdin.close()
            try:
                await process.stdin.wait_closed()
            except (BrokenPipeError, ConnectionResetError):
                pass
        try:
            await asyncio.wait_for(process.wait(), timeout=1.0)
        except TimeoutError:
            process.terminate()
            await process.wait()
        for task in (self._reader_task, self._stderr_task):
            if task is not None and not task.done():
                task.cancel()
        self.process = None

    async def _write(self, message: Mapping[str, object]) -> None:
        process = self._require_process()
        if process.stdin is None:
            raise CodexProtocolError("Codex App Server stdin is unavailable")
        payload = json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n"
        process.stdin.write(payload.encode("utf-8"))
        try:
            await process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as exc:
            raise CodexProtocolError("Codex App Server closed its input") from exc

    async def _read_messages(self) -> None:
        process = self._require_process()
        assert process.stdout is not None
        try:
            while line := await process.stdout.readline():
                try:
                    message = json.loads(line)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    await self._events.put({"method": "_bridge/invalidMessage", "params": {}})
                    continue
                if not isinstance(message, dict):
                    await self._events.put({"method": "_bridge/invalidMessage", "params": {}})
                    continue
                request_id = message.get("id")
                if isinstance(request_id, int) and (
                    "result" in message or "error" in message
                ):
                    future = self._pending.get(request_id)
                    if future is None or future.done():
                        continue
                    if "error" in message:
                        error = message.get("error")
                        code = error.get("code") if isinstance(error, dict) else None
                        future.set_exception(CodexRpcError(code if isinstance(code, int) else None))
                    else:
                        future.set_result(message.get("result"))
                    continue
                await self._events.put(message)
        finally:
            if not self._closing:
                await self._events.put({"method": "_bridge/eof", "params": {}})
            for future in list(self._pending.values()):
                if not future.done():
                    future.set_exception(CodexProtocolError("Codex App Server exited"))

    async def _discard_stderr(self) -> None:
        process = self._require_process()
        assert process.stderr is not None
        while await process.stderr.readline():
            pass

    def _require_process(self) -> asyncio.subprocess.Process:
        if self.process is None:
            raise CodexProtocolError("Codex App Server client is not running")
        return self.process
