from __future__ import annotations

import json
import os
import queue
import subprocess
import tempfile
import threading
import time
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any, TextIO


class CodexBridgeError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


SAFE_ERRORS = {
    "CODEX_NOT_INSTALLED": (503, "Codex CLI is not installed or is not on PATH."),
    "CODEX_PROTOCOL_INCOMPATIBLE": (409, "The installed Codex App Server protocol is incompatible."),
    "CODEX_NOT_AUTHENTICATED": (409, "Codex is not signed in."),
    "CODEX_WRONG_AUTH_MODE": (409, "Codex is signed in without ChatGPT authentication."),
    "CODEX_LOGIN_EXPIRED": (401, "The Codex ChatGPT login is no longer valid."),
    "CODEX_USAGE_LIMITED": (429, "The ChatGPT account has reached a Codex usage limit."),
    "CODEX_RATE_LIMITED": (429, "Codex rate-limited the request."),
    "CODEX_TIMEOUT": (504, "Codex did not finish before the configured deadline."),
    "CODEX_CANCELLED": (409, "The Codex turn was interrupted."),
    "CODEX_ISOLATION_VIOLATION": (409, "Codex attempted a forbidden tool or loaded an instruction file."),
    "CODEX_RESPONSE_INVALID": (502, "Codex returned an invalid final response."),
    "CODEX_CONNECTION_FAILED": (502, "Codex App Server could not complete the request."),
}

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

_IGNORED_TURN_NOTIFICATIONS = {
    "config/warning",
    "deprecationNotice",
    "item/agentMessage/delta",
    "item/plan/delta",
    "item/reasoning/summaryPartAdded",
    "item/reasoning/summaryTextDelta",
    "item/reasoning/textDelta",
    "model/verification",
    "thread/started",
    "thread/status/changed",
    "turn/started",
    "warning",
}

_BLOCKED_METHOD_PREFIXES = (
    "command/",
    "item/commandExecution/",
    "item/fileChange/",
    "item/imageGeneration/",
    "item/imageView/",
    "item/mcpToolCall/",
    "item/webSearch/",
    "mcpServer/",
    "process/",
    "tool/",
)


def bridge_error(code: str) -> CodexBridgeError:
    status_code, message = SAFE_ERRORS[code]
    return CodexBridgeError(code, message, status_code=status_code)


class JsonRpcProcess:
    """Line-delimited JSON-RPC connection to one short-lived App Server process."""

    def __init__(
        self,
        *,
        executable: str,
        cwd: Path,
        process_factory: Callable[..., subprocess.Popen[str]] = subprocess.Popen,
    ) -> None:
        self.executable = executable
        self.cwd = cwd
        self.process_factory = process_factory
        self.process: subprocess.Popen[str] | None = None
        self._next_id = 1
        self._messages: queue.Queue[dict[str, Any]] = queue.Queue()
        self._pending_notifications: deque[dict[str, Any]] = deque()
        self._stderr_tail: deque[str] = deque(maxlen=20)

    def __enter__(self) -> JsonRpcProcess:
        self.cwd.mkdir(parents=True, exist_ok=True)
        command = [
            self.executable,
            "app-server",
            "--stdio",
            "--strict-config",
            "-c",
            'web_search="disabled"',
            "-c",
            "mcp_servers={}",
        ]
        for feature in DISABLED_FEATURES:
            command.extend(["--disable", feature])
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        child_environment = os.environ.copy()
        for name in list(child_environment):
            if name.upper().startswith("RAGOPS_") or name.upper() in _SENSITIVE_CHILD_ENVIRONMENT:
                child_environment.pop(name, None)
        try:
            self.process = self.process_factory(
                command,
                cwd=str(self.cwd),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creationflags,
                env=child_environment,
            )
        except FileNotFoundError:
            raise bridge_error("CODEX_NOT_INSTALLED") from None
        except OSError:
            raise bridge_error("CODEX_CONNECTION_FAILED") from None
        assert self.process.stdout is not None and self.process.stderr is not None
        threading.Thread(target=self._read_stdout, args=(self.process.stdout,), daemon=True).start()
        threading.Thread(target=self._read_stderr, args=(self.process.stderr,), daemon=True).start()
        return self

    def __exit__(self, *_: object) -> None:
        process = self.process
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)

    def initialize(self, timeout_seconds: float) -> dict[str, Any]:
        result = self.request(
            "initialize",
            {
                "clientInfo": {"name": "ragops-codex-bridge", "version": "1.0.0"},
                "capabilities": {"experimentalApi": True},
            },
            timeout_seconds=timeout_seconds,
        )
        self.notify("initialized", {})
        return result

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        message: dict[str, Any] = {"method": method}
        if params is not None:
            message["params"] = params
        self._write(message)

    def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        message: dict[str, Any] = {"id": request_id, "method": method}
        if params is not None:
            message["params"] = params
        self._write(message)
        deadline = time.monotonic() + timeout_seconds
        while True:
            incoming = self._read_until(deadline)
            if incoming.get("id") == request_id:
                if "error" in incoming:
                    raise _rpc_error(incoming["error"])
                result = incoming.get("result")
                if not isinstance(result, dict):
                    raise bridge_error("CODEX_RESPONSE_INVALID")
                return result
            if "id" in incoming and isinstance(incoming.get("method"), str):
                self._reject_server_request(incoming)
                raise bridge_error("CODEX_ISOLATION_VIOLATION")
            self._pending_notifications.append(incoming)

    def next_notification(self, deadline: float) -> dict[str, Any]:
        if self._pending_notifications:
            return self._pending_notifications.popleft()
        incoming = self._read_until(deadline)
        if "id" in incoming and isinstance(incoming.get("method"), str):
            self._reject_server_request(incoming)
            raise bridge_error("CODEX_ISOLATION_VIOLATION")
        return incoming

    def interrupt(self, thread_id: str, turn_id: str) -> None:
        try:
            self.request(
                "turn/interrupt",
                {"threadId": thread_id, "turnId": turn_id},
                timeout_seconds=2,
            )
        except CodexBridgeError:
            pass

    def _write(self, message: dict[str, Any]) -> None:
        process = self.process
        if process is None or process.stdin is None or process.poll() is not None:
            raise bridge_error("CODEX_CONNECTION_FAILED")
        try:
            process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
            process.stdin.flush()
        except (BrokenPipeError, OSError):
            raise bridge_error("CODEX_CONNECTION_FAILED") from None

    def _read_until(self, deadline: float) -> dict[str, Any]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise bridge_error("CODEX_TIMEOUT")
        try:
            message = self._messages.get(timeout=remaining)
        except queue.Empty:
            raise bridge_error("CODEX_TIMEOUT") from None
        if message.get("__eof__"):
            raise bridge_error("CODEX_CONNECTION_FAILED")
        if message.get("__invalid__"):
            raise bridge_error("CODEX_PROTOCOL_INCOMPATIBLE")
        return message

    def _reject_server_request(self, message: dict[str, Any]) -> None:
        self._write(
            {
                "id": message["id"],
                "error": {"code": -32601, "message": "Client-side actions are disabled."},
            }
        )

    def _read_stdout(self, stream: TextIO) -> None:
        for raw_line in stream:
            try:
                value = json.loads(raw_line)
            except ValueError:
                self._messages.put({"__invalid__": True})
                continue
            if isinstance(value, dict):
                self._messages.put(value)
            else:
                self._messages.put({"__invalid__": True})
        self._messages.put({"__eof__": True})

    def _read_stderr(self, stream: TextIO) -> None:
        for raw_line in stream:
            self._stderr_tail.append(raw_line.rstrip()[:500])


class CodexAppServerRunner:
    def __init__(
        self,
        *,
        executable: str,
        sandbox_root: Path,
        timeout_seconds: float,
        connection_factory: Callable[..., JsonRpcProcess] = JsonRpcProcess,
    ) -> None:
        self.executable = executable
        self.sandbox_root = sandbox_root.resolve()
        self.timeout_seconds = timeout_seconds
        self.connection_factory = connection_factory

    def inspect(self) -> dict[str, Any]:
        with self._connection() as rpc:
            initialized = rpc.initialize(self.timeout_seconds)
            account = rpc.request(
                "account/read", {"refreshToken": True}, timeout_seconds=self.timeout_seconds
            )
            account_value = account.get("account")
            if not isinstance(account_value, dict):
                auth_status = "not_authenticated"
                auth_mode = None
                plan_type = None
                models: list[dict[str, Any]] = []
                rate_limits = None
            else:
                account_type = account_value.get("type")
                auth_mode = account_type if isinstance(account_type, str) else None
                plan_type = (
                    account_value.get("planType")
                    if isinstance(account_value.get("planType"), str)
                    else None
                )
                auth_status = "authenticated" if auth_mode == "chatgpt" else "wrong_auth_mode"
                models = self._models(rpc) if auth_mode == "chatgpt" else []
                rate_limits = self._rate_limits(rpc) if auth_mode == "chatgpt" else None
            return {
                "codex_installed": True,
                "codex_version": _safe_codex_version(initialized.get("userAgent")),
                "protocol_compatible": True,
                "authentication_status": auth_status,
                "authentication_mode": auth_mode,
                "plan_type": plan_type,
                "models": models,
                "rate_limits": rate_limits,
                "isolation": {
                    "ephemeral_session": True,
                    "approval_policy": "never",
                    "sandbox": "read_only",
                    "network_access": False,
                    "dynamic_tools": False,
                    "feature_tools_disabled": True,
                    "instruction_sources_allowed": False,
                },
            }

    def generate(self, request: dict[str, Any]) -> dict[str, Any]:
        self.sandbox_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="ragops-codex-", dir=self.sandbox_root
        ) as sandbox_dir:
            return self._generate_in_sandbox(request, Path(sandbox_dir).resolve())

    def _generate_in_sandbox(
        self, request: dict[str, Any], sandbox: Path
    ) -> dict[str, Any]:
        started = time.monotonic()
        with self._connection(sandbox) as rpc:
            rpc.initialize(self.timeout_seconds)
            account = rpc.request(
                "account/read", {"refreshToken": True}, timeout_seconds=self.timeout_seconds
            )
            account_value = account.get("account")
            if not isinstance(account_value, dict):
                raise bridge_error("CODEX_NOT_AUTHENTICATED")
            if account_value.get("type") != "chatgpt":
                raise bridge_error("CODEX_WRONG_AUTH_MODE")

            thread_response = rpc.request(
                "thread/start",
                {
                    "model": request["model"],
                    "allowProviderModelFallback": False,
                    "cwd": str(sandbox),
                    "runtimeWorkspaceRoots": [str(sandbox)],
                    "approvalPolicy": "never",
                    "sandbox": "read-only",
                    "ephemeral": True,
                    "dynamicTools": [],
                    "environments": [],
                    "selectedCapabilityRoots": [],
                    "baseInstructions": (
                        "Answer the supplied question only. Do not use tools, files, commands, "
                        "network access, plugins, MCP, memories, or other conversations."
                    ),
                    "developerInstructions": (
                        "Return one JSON object matching the requested schema. Base the answer "
                        "only on the prompt, question, and context included in the turn input."
                    ),
                    "config": {"mcp_servers": {}, "web_search": "disabled"},
                },
                timeout_seconds=self.timeout_seconds,
            )
            thread_id = _validate_thread_response(
                thread_response, sandbox=sandbox, requested_model=request["model"]
            )
            actual_model = (
                thread_response.get("model")
                if isinstance(thread_response.get("model"), str)
                else None
            )
            prompt = _generation_prompt(request)
            turn_params: dict[str, Any] = {
                "threadId": thread_id,
                "input": [{"type": "text", "text": prompt}],
                "outputSchema": {
                    "type": "object",
                    "properties": {"answer": {"type": "string"}},
                    "required": ["answer"],
                    "additionalProperties": False,
                },
                "sandboxPolicy": {"type": "readOnly", "networkAccess": False},
                "environments": [],
                "runtimeWorkspaceRoots": [str(sandbox)],
            }
            if request.get("reasoning_effort") is not None:
                turn_params["effort"] = request["reasoning_effort"]
            turn_response = rpc.request(
                "turn/start", turn_params, timeout_seconds=self.timeout_seconds
            )
            turn = turn_response.get("turn")
            turn_id = turn.get("id") if isinstance(turn, dict) else None
            if not isinstance(turn_id, str):
                raise bridge_error("CODEX_RESPONSE_INVALID")
            try:
                answer_text, usage, routed_model = self._wait_for_turn(
                    rpc, thread_id, turn_id
                )
            except CodexBridgeError as exc:
                if exc.code in {"CODEX_TIMEOUT", "CODEX_ISOLATION_VIOLATION"}:
                    rpc.interrupt(thread_id, turn_id)
                raise
            answer = _parse_final_answer(answer_text)
            return {
                "answer": answer,
                "actual_model": routed_model or actual_model,
                "finish_reason": "stop",
                "latency_ms": max(0, round((time.monotonic() - started) * 1000)),
                "usage": usage,
                "provider_request_id": turn_id,
            }

    def _wait_for_turn(
        self, rpc: JsonRpcProcess, thread_id: str, turn_id: str
    ) -> tuple[str, dict[str, int] | None, str | None]:
        deadline = time.monotonic() + self.timeout_seconds
        final_messages: dict[str, str] = {}
        usage = None
        routed_model = None
        while True:
            notification = rpc.next_notification(deadline)
            method = notification.get("method")
            params = notification.get("params")
            if not isinstance(params, dict):
                continue
            if method in {"item/started", "item/completed"}:
                if params.get("threadId") != thread_id or params.get("turnId") != turn_id:
                    continue
                item = params.get("item")
                if not isinstance(item, dict):
                    raise bridge_error("CODEX_RESPONSE_INVALID")
                item_type = item.get("type")
                if item_type not in {"userMessage", "reasoning", "agentMessage", "plan"}:
                    raise bridge_error("CODEX_ISOLATION_VIOLATION")
                if item_type == "agentMessage" and method == "item/completed":
                    phase = item.get("phase")
                    item_id = item.get("id")
                    text = item.get("text")
                    if phase == "final_answer":
                        if not isinstance(item_id, str) or not isinstance(text, str):
                            raise bridge_error("CODEX_RESPONSE_INVALID")
                        final_messages[item_id] = text
            elif method == "thread/tokenUsage/updated":
                if params.get("threadId") == thread_id and params.get("turnId") == turn_id:
                    usage = _safe_usage(params.get("tokenUsage"))
            elif method == "model/rerouted":
                if params.get("threadId") == thread_id and params.get("turnId") == turn_id:
                    candidate = params.get("toModel")
                    routed_model = candidate if isinstance(candidate, str) else routed_model
            elif method == "turn/completed":
                if params.get("threadId") != thread_id:
                    continue
                turn = params.get("turn")
                if not isinstance(turn, dict) or turn.get("id") != turn_id:
                    continue
                status = turn.get("status")
                if status == "interrupted":
                    raise bridge_error("CODEX_CANCELLED")
                if status != "completed":
                    raise _turn_error(turn.get("error"))
                if len(final_messages) != 1:
                    raise bridge_error("CODEX_RESPONSE_INVALID")
                return next(iter(final_messages.values())), usage, routed_model
            elif method == "error":
                if params.get("threadId") not in {None, thread_id}:
                    continue
                if params.get("turnId") not in {None, turn_id}:
                    continue
                raise _turn_error(params.get("error"))
            elif method in _IGNORED_TURN_NOTIFICATIONS:
                continue
            elif isinstance(method, str) and method.startswith(_BLOCKED_METHOD_PREFIXES):
                raise bridge_error("CODEX_ISOLATION_VIOLATION")
            else:
                raise bridge_error("CODEX_ISOLATION_VIOLATION")

    def _models(self, rpc: JsonRpcProcess) -> list[dict[str, Any]]:
        response = rpc.request(
            "model/list",
            {"limit": 100, "includeHidden": False},
            timeout_seconds=self.timeout_seconds,
        )
        data = response.get("data")
        if not isinstance(data, list):
            raise bridge_error("CODEX_RESPONSE_INVALID")
        models = []
        for item in data:
            if not isinstance(item, dict):
                continue
            model_id = item.get("model") or item.get("id")
            if not isinstance(model_id, str):
                continue
            efforts = item.get("supportedReasoningEfforts")
            models.append(
                {
                    "id": model_id,
                    "display_name": (
                        item.get("displayName")
                        if isinstance(item.get("displayName"), str)
                        else model_id
                    ),
                    "is_default": item.get("isDefault") is True,
                    "reasoning_efforts": [
                        effort["reasoningEffort"]
                        for effort in efforts
                        if isinstance(effort, dict)
                        and isinstance(effort.get("reasoningEffort"), str)
                    ]
                    if isinstance(efforts, list)
                    else [],
                }
            )
        return models

    def _rate_limits(self, rpc: JsonRpcProcess) -> dict[str, Any] | None:
        try:
            response = rpc.request(
                "account/rateLimits/read", {}, timeout_seconds=self.timeout_seconds
            )
        except CodexBridgeError:
            return None
        return _safe_rate_limits(response)

    def _connection(self, cwd: Path | None = None) -> JsonRpcProcess:
        return self.connection_factory(executable=self.executable, cwd=cwd or self.sandbox_root)


def _validate_thread_response(
    response: dict[str, Any], *, sandbox: Path, requested_model: object
) -> str:
    thread = response.get("thread")
    policy = response.get("sandbox")
    if not isinstance(thread, dict) or not isinstance(policy, dict):
        raise bridge_error("CODEX_PROTOCOL_INCOMPATIBLE")
    try:
        returned_cwd = Path(str(response.get("cwd"))).resolve()
        thread_cwd = Path(str(thread.get("cwd"))).resolve()
    except (OSError, ValueError):
        raise bridge_error("CODEX_ISOLATION_VIOLATION") from None
    if (
        response.get("instructionSources") != []
        or returned_cwd != sandbox
        or thread_cwd != sandbox
        or response.get("approvalPolicy") != "never"
        or policy.get("type") != "readOnly"
        or policy.get("networkAccess") is not False
        or thread.get("ephemeral") is not True
        or response.get("model") != requested_model
    ):
        raise bridge_error("CODEX_ISOLATION_VIOLATION")
    thread_id = thread.get("id")
    if not isinstance(thread_id, str) or not thread_id:
        raise bridge_error("CODEX_RESPONSE_INVALID")
    return thread_id


def _generation_prompt(request: dict[str, Any]) -> str:
    contexts = request.get("context")
    context_lines = []
    if isinstance(contexts, list):
        for item in contexts:
            if isinstance(item, dict):
                context_lines.append(f"[{item.get('position')}]\n{item.get('text')}")
    context = "\n\n".join(context_lines) or "(none)"
    return (
        f"Generation instruction:\n{request['prompt']}\n\n"
        f"Question:\n{request['question']}\n\nContext:\n{context}"
    )


def _parse_final_answer(value: str) -> str:
    try:
        parsed = json.loads(value)
    except ValueError:
        raise bridge_error("CODEX_RESPONSE_INVALID") from None
    answer = parsed.get("answer") if isinstance(parsed, dict) else None
    if not isinstance(answer, str) or not answer.strip():
        raise bridge_error("CODEX_RESPONSE_INVALID")
    return answer


def _safe_usage(value: object) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    last = value.get("last")
    if not isinstance(last, dict):
        return None
    result = {
        "input_tokens": last.get("inputTokens"),
        "output_tokens": last.get("outputTokens"),
        "total_tokens": last.get("totalTokens"),
    }
    if any(not isinstance(item, int) or isinstance(item, bool) or item < 0 for item in result.values()):
        return None
    return result  # type: ignore[return-value]


def _safe_rate_limits(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    snapshot = value.get("rateLimits")
    if not isinstance(snapshot, dict):
        return None
    safe: dict[str, Any] = {}
    for key in ("primary", "secondary"):
        window = snapshot.get(key)
        if isinstance(window, dict):
            safe[key] = {
                "used_percent": window.get("usedPercent")
                if isinstance(window.get("usedPercent"), int)
                else None,
                "resets_at": window.get("resetsAt")
                if isinstance(window.get("resetsAt"), int)
                else None,
                "window_minutes": window.get("windowDurationMins")
                if isinstance(window.get("windowDurationMins"), int)
                else None,
            }
    safe["limit_reached_type"] = (
        snapshot.get("rateLimitReachedType")
        if isinstance(snapshot.get("rateLimitReachedType"), str)
        else None
    )
    safe["spend_control_reached"] = (
        snapshot.get("spendControlReached")
        if isinstance(snapshot.get("spendControlReached"), bool)
        else None
    )
    return safe


def _safe_codex_version(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return value[:120]


def _rpc_error(value: object) -> CodexBridgeError:
    if isinstance(value, dict):
        data = value.get("data")
        if isinstance(data, dict):
            return _map_codex_error(data.get("codexErrorInfo"))
    return bridge_error("CODEX_CONNECTION_FAILED")


def _turn_error(value: object) -> CodexBridgeError:
    if isinstance(value, dict):
        return _map_codex_error(value.get("codexErrorInfo"))
    return bridge_error("CODEX_CONNECTION_FAILED")


def _map_codex_error(value: object) -> CodexBridgeError:
    if value == "usageLimitExceeded":
        return bridge_error("CODEX_USAGE_LIMITED")
    if value == "rateLimitExceeded":
        return bridge_error("CODEX_RATE_LIMITED")
    if value == "unauthorized":
        return bridge_error("CODEX_LOGIN_EXPIRED")
    if isinstance(value, dict) and any(
        key in value
        for key in (
            "httpConnectionFailed",
            "responseStreamConnectionFailed",
            "responseStreamDisconnected",
            "responseTooManyFailedAttempts",
        )
    ):
        return bridge_error("CODEX_CONNECTION_FAILED")
    return bridge_error("CODEX_CONNECTION_FAILED")
