from __future__ import annotations

import json
import logging
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any, TextIO


logger = logging.getLogger(__name__)


class CodexBridgeError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int,
        reason_code: str | None = None,
        diagnostic_id: str | None = None,
        diagnostics: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.reason_code = reason_code
        self.diagnostic_id = diagnostic_id
        self.diagnostics = diagnostics or {}


SAFE_ERRORS = {
    "CODEX_BRIDGE_INTERNAL_ERROR": (500, "The local Codex bridge failed internally; inspect the diagnostic ID."),
    "CODEX_NOT_INSTALLED": (503, "Codex CLI is not installed or is not on PATH."),
    "CODEX_PROTOCOL_INCOMPATIBLE": (
        409,
        "The installed Codex App Server protocol is incompatible.",
    ),
    "CODEX_NOT_AUTHENTICATED": (409, "Codex is not signed in."),
    "CODEX_WRONG_AUTH_MODE": (409, "Codex is signed in without ChatGPT authentication."),
    "CODEX_LOGIN_EXPIRED": (401, "The Codex ChatGPT login is no longer valid."),
    "CODEX_USAGE_LIMITED": (429, "The ChatGPT account has reached a Codex usage limit."),
    "CODEX_RATE_LIMITED": (429, "Codex rate-limited the request."),
    "CODEX_TIMEOUT": (504, "Codex did not finish before the configured deadline."),
    "CODEX_CANCELLED": (409, "The Codex turn was interrupted."),
    "CODEX_ISOLATION_VIOLATION": (409, "Codex could not satisfy the evaluation isolation policy."),
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
    # Informational account telemetry; generation errors are handled separately.
    "account/rateLimits/updated",
    "config/warning",
    "deprecationNotice",
    "item/agentMessage/delta",
    "item/plan/delta",
    "item/reasoning/summaryPartAdded",
    "item/reasoning/summaryTextDelta",
    "item/reasoning/textDelta",
    "model/verification",
    "remoteControl/status/changed",
    "thread/started",
    "thread/status/changed",
    "turn/started",
    "warning",
    "configWarning",
}

_BLOCKED_METHOD_PREFIXES = (
    "command/",
    "item/commandExecution/",
    "item/fileChange/",
    "item/imageGeneration/",
    "item/imageView/",
    "item/mcpToolCall/",
    "item/webSearch/",
    "process/",
    "tool/",
)

_MCP_STARTUP_STATUS_METHOD = "mcpServer/startupStatus/updated"
_MCP_TOOL_METHODS = {"mcpServer/tool/call"}
_MCP_FEATURES = (
    "apps",
    "enable_mcp_apps",
    "plugin_sharing",
    "plugins",
    "recommended_plugins",
    "remote_plugin",
    "skill_mcp_dependency_install",
    "tool_call_mcp_elicitation",
)


_SAFE_DIAGNOSTIC_FIELDS = {
    "actual",
    "expected",
    "field",
    "item_type",
    "matches",
    "method",
    "phase",
    "rpc_id",
    "rpc_method",
    "server_name",
    "server_status",
    "failure_reason",
    "config_source",
    "source_count",
    "stage",
    "state",
    "thread_id",
    "turn_id",
    "value_type",
}
_SAFE_NULLABLE_DIAGNOSTIC_FIELDS = {"failure_reason", "thread_id"}
_SAFE_DIAGNOSTIC_VALUE = re.compile(r"[A-Za-z0-9_.:/-]{1,200}\Z")


def bridge_error(
    code: str,
    *,
    reason_code: str | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> CodexBridgeError:
    status_code, message = SAFE_ERRORS[code]
    safe_diagnostics = _safe_diagnostics(diagnostics)
    diagnostic_id = uuid.uuid4().hex if reason_code else None
    if reason_code and diagnostic_id:
        logger.warning(
            "codex_bridge.protocol_stopped %s",
            json.dumps(
                {
                    "diagnostic_id": diagnostic_id,
                    "error_code": code,
                    "reason_code": reason_code,
                    **safe_diagnostics,
                },
                ensure_ascii=True,
                sort_keys=True,
            ),
        )
    return CodexBridgeError(
        code,
        message,
        status_code=status_code,
        reason_code=reason_code,
        diagnostic_id=diagnostic_id,
        diagnostics=safe_diagnostics,
    )


def _safe_diagnostics(value: dict[str, Any] | None) -> dict[str, Any]:
    if not value:
        return {}
    result: dict[str, Any] = {}
    for key in _SAFE_DIAGNOSTIC_FIELDS:
        if key not in value:
            continue
        item = value.get(key)
        if item is None and key in _SAFE_NULLABLE_DIAGNOSTIC_FIELDS:
            result[key] = None
        elif isinstance(item, str):
            result[key] = item if _SAFE_DIAGNOSTIC_VALUE.fullmatch(item) else "<redacted>"
        elif isinstance(item, (bool, int)) and not isinstance(item, float):
            result[key] = item
    return result


def _notification_diagnostics(
    message: dict[str, Any], *, stage: str, rpc_method: str | None = None
) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {"stage": stage}
    method = message.get("method")
    if isinstance(method, str):
        diagnostics["method"] = method
    if rpc_method is not None:
        diagnostics["rpc_method"] = rpc_method
    if isinstance(message.get("id"), (str, int)):
        diagnostics["rpc_id"] = str(message["id"])
    params = message.get("params")
    if not isinstance(params, dict):
        return diagnostics
    for source, target in (("threadId", "thread_id"), ("turnId", "turn_id")):
        candidate = params.get(source)
        if isinstance(candidate, str):
            diagnostics[target] = candidate
    item = params.get("item")
    if isinstance(item, dict):
        item_type = item.get("type")
        phase = item.get("phase")
        if isinstance(item_type, str):
            diagnostics["item_type"] = item_type
        if isinstance(phase, str):
            diagnostics["phase"] = phase
    return diagnostics


def _mcp_startup_diagnostics(message: dict[str, Any], *, stage: str) -> dict[str, Any]:
    diagnostics = _notification_diagnostics(message, stage=stage)
    params = message.get("params")
    if not isinstance(params, dict):
        return diagnostics
    diagnostics["server_name"] = params.get("name")
    diagnostics["server_status"] = params.get("status")
    diagnostics["failure_reason"] = params.get("failureReason")
    diagnostics["thread_id"] = params.get("threadId")
    return diagnostics


def _raise_for_mcp_startup_notification(message: dict[str, Any], *, stage: str) -> None:
    if message.get("method") != _MCP_STARTUP_STATUS_METHOD:
        return
    raise bridge_error(
        "CODEX_ISOLATION_VIOLATION",
        reason_code="MCP_SERVER_STARTUP_STATUS_OBSERVED",
        diagnostics=_mcp_startup_diagnostics(message, stage=stage),
    )


def _forbidden_method_reason(method: object) -> str | None:
    if method in _MCP_TOOL_METHODS or (
        isinstance(method, str) and method.startswith("item/mcpToolCall/")
    ):
        return "MCP_TOOL_CALL_FORBIDDEN"
    if isinstance(method, str) and method.startswith(_BLOCKED_METHOD_PREFIXES):
        return "TURN_FORBIDDEN_METHOD"
    return None


class JsonRpcProcess:
    """Line-delimited JSON-RPC connection to one short-lived App Server process."""

    def __init__(
        self,
        *,
        executable: str,
        cwd: Path,
        codex_home: Path,
        process_factory: Callable[..., subprocess.Popen[str]] = subprocess.Popen,
    ) -> None:
        self.executable = executable
        self.cwd = cwd
        self.codex_home = codex_home.resolve()
        self.process_factory = process_factory
        self.process: subprocess.Popen[str] | None = None
        self._next_id = 1
        self._messages: queue.Queue[dict[str, Any]] = queue.Queue()
        self._pending_notifications: deque[dict[str, Any]] = deque()
        self._stderr_tail: deque[str] = deque(maxlen=20)

    def __enter__(self) -> JsonRpcProcess:
        self.cwd.mkdir(parents=True, exist_ok=True)
        self.codex_home.mkdir(parents=True, exist_ok=True)
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
        child_environment["CODEX_HOME"] = str(self.codex_home)
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
            _raise_for_mcp_startup_notification(incoming, stage="rpc_response")
            if incoming.get("id") == request_id:
                if "error" in incoming:
                    raise _rpc_error(incoming["error"])
                result = incoming.get("result")
                if not isinstance(result, dict):
                    raise bridge_error("CODEX_RESPONSE_INVALID")
                return result
            if "id" in incoming and isinstance(incoming.get("method"), str):
                self._reject_server_request(incoming)
                raise bridge_error(
                    "CODEX_ISOLATION_VIOLATION",
                    reason_code="RPC_SERVER_REQUEST_DURING_RESPONSE",
                    diagnostics=_notification_diagnostics(
                        incoming, stage="rpc_response", rpc_method=method
                    ),
                )
            self._pending_notifications.append(incoming)

    def next_notification(self, deadline: float) -> dict[str, Any]:
        if self._pending_notifications:
            return self._pending_notifications.popleft()
        incoming = self._read_until(deadline)
        _raise_for_mcp_startup_notification(incoming, stage="turn_stream")
        if "id" in incoming and isinstance(incoming.get("method"), str):
            self._reject_server_request(incoming)
            raise bridge_error(
                "CODEX_ISOLATION_VIOLATION",
                reason_code="RPC_SERVER_REQUEST_DURING_TURN",
                diagnostics=_notification_diagnostics(incoming, stage="turn_stream"),
            )
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
        codex_home: Path,
        timeout_seconds: float,
        connection_factory: Callable[..., JsonRpcProcess] = JsonRpcProcess,
    ) -> None:
        self.executable = executable
        self.sandbox_root = sandbox_root.resolve()
        self.codex_home = codex_home.resolve()
        self.timeout_seconds = timeout_seconds
        self.connection_factory = connection_factory

    def inspect(self) -> dict[str, Any]:
        with self._connection() as rpc:
            initialized = self._initialize_and_verify(rpc, self.sandbox_root)
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
        sandbox = Path(tempfile.mkdtemp(prefix="ragops-codex-", dir=self.sandbox_root)).resolve()
        try:
            return self._generate_in_sandbox(request, sandbox)
        finally:
            # Windows can briefly retain a child process's working directory.
            # Cleanup must never replace the generation result or original error.
            for attempt in range(3):
                try:
                    shutil.rmtree(sandbox)
                    break
                except FileNotFoundError:
                    break
                except OSError as exc:
                    if attempt < 2:
                        time.sleep(0.1 * (attempt + 1))
                    else:
                        logger.warning(
                            "codex_bridge.sandbox_cleanup_deferred %s",
                            json.dumps({
                                "diagnostic_id": uuid.uuid4().hex,
                                "error_type": type(exc).__name__,
                                "winerror": getattr(exc, "winerror", None),
                            }),
                        )

    def _generate_in_sandbox(self, request: dict[str, Any], sandbox: Path) -> dict[str, Any]:
        started = time.monotonic()
        with self._connection(sandbox) as rpc:
            self._initialize_and_verify(rpc, sandbox)
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
                    rpc, thread_id, turn_id, sandbox=sandbox, expected_model=request["model"]
                )
            except CodexBridgeError as exc:
                if exc.code in {
                    "CODEX_TIMEOUT",
                    "CODEX_ISOLATION_VIOLATION",
                    "CODEX_PROTOCOL_INCOMPATIBLE",
                }:
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
        self, rpc: JsonRpcProcess, thread_id: str, turn_id: str,
        *, sandbox: Path | None = None, expected_model: str | None = None,
    ) -> tuple[str, dict[str, int] | None, str | None]:
        deadline = time.monotonic() + self.timeout_seconds
        final_messages: dict[str, str] = {}
        usage = None
        routed_model = None
        while True:
            notification = rpc.next_notification(deadline)
            method = notification.get("method")
            _raise_for_mcp_startup_notification(notification, stage="turn_stream")
            params = notification.get("params")
            if not isinstance(params, dict):
                if method == "thread/settings/updated":
                    raise bridge_error(
                        "CODEX_PROTOCOL_INCOMPATIBLE",
                        reason_code="THREAD_SETTINGS_PAYLOAD_INVALID",
                        diagnostics={"stage": "turn_stream", "method": method},
                    )
                continue
            if method == "thread/settings/updated":
                if params.get("threadId") != thread_id:
                    raise bridge_error(
                        "CODEX_PROTOCOL_INCOMPATIBLE",
                        reason_code="THREAD_SETTINGS_SCOPE_INVALID",
                        diagnostics={"stage": "turn_stream", "method": method},
                    )
                settings = params.get("threadSettings")
                policy = settings.get("sandboxPolicy") if isinstance(settings, dict) else None
                safe = (
                    isinstance(settings, dict)
                    and sandbox is not None
                    and expected_model is not None
                    and settings.get("cwd") == str(sandbox)
                    and settings.get("model") == expected_model
                    and settings.get("approvalPolicy") == "never"
                    and isinstance(policy, dict)
                    and policy.get("type") == "readOnly"
                    and policy.get("networkAccess", False) is False
                )
                if not safe:
                    raise bridge_error(
                        "CODEX_ISOLATION_VIOLATION",
                        reason_code="THREAD_SETTINGS_UNSAFE_OR_INVALID",
                        diagnostics={"stage": "turn_stream", "method": method},
                    )
            elif method in {"item/started", "item/completed"}:
                if params.get("threadId") != thread_id or params.get("turnId") != turn_id:
                    continue
                item = params.get("item")
                if not isinstance(item, dict):
                    raise bridge_error("CODEX_RESPONSE_INVALID")
                item_type = item.get("type")
                if item_type not in {"userMessage", "reasoning", "agentMessage", "plan"}:
                    reason_code = (
                        "MCP_TOOL_CALL_FORBIDDEN"
                        if item_type == "mcpToolCall"
                        else "TURN_FORBIDDEN_ITEM_TYPE"
                    )
                    raise bridge_error(
                        "CODEX_ISOLATION_VIOLATION",
                        reason_code=reason_code,
                        diagnostics=_notification_diagnostics(notification, stage="turn_stream"),
                    )
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
            elif reason_code := _forbidden_method_reason(method):
                raise bridge_error(
                    "CODEX_ISOLATION_VIOLATION",
                    reason_code=reason_code,
                    diagnostics=_notification_diagnostics(notification, stage="turn_stream"),
                )
            else:
                raise bridge_error(
                    "CODEX_PROTOCOL_INCOMPATIBLE",
                    reason_code="TURN_PROTOCOL_NOTIFICATION_UNRECOGNIZED",
                    diagnostics=_notification_diagnostics(notification, stage="turn_stream"),
                )

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
        return self.connection_factory(
            executable=self.executable,
            cwd=cwd or self.sandbox_root,
            codex_home=self.codex_home,
        )

    def _initialize_and_verify(
        self, rpc: JsonRpcProcess, cwd: Path
    ) -> dict[str, Any]:
        initialized = rpc.initialize(self.timeout_seconds)
        effective = rpc.request(
            "config/read",
            {"cwd": str(cwd), "includeLayers": True},
            timeout_seconds=self.timeout_seconds,
        )
        _validate_effective_config(effective, codex_home=self.codex_home)
        registry = rpc.request(
            "mcpServerStatus/list",
            {"limit": 100, "detail": "toolsAndAuthOnly"},
            timeout_seconds=self.timeout_seconds,
        )
        _validate_mcp_registry(registry)
        return initialized


def _validate_effective_config(response: dict[str, Any], *, codex_home: Path) -> None:
    config = response.get("config")
    if not isinstance(config, dict):
        _raise_unverifiable_config(response, "config", config)

    mcp_servers = config.get("mcp_servers")
    if not isinstance(mcp_servers, dict):
        _raise_unverifiable_config(config, "mcp_servers", mcp_servers)
    if mcp_servers:
        server_name = _first_string_key(mcp_servers)
        raise bridge_error(
            "CODEX_ISOLATION_VIOLATION",
            reason_code="MCP_EFFECTIVE_CONFIG_NOT_EMPTY",
            diagnostics={
                "stage": "effective_config_validation",
                "field": "mcp_servers",
                "state": "non_empty",
                "source_count": len(mcp_servers),
                "server_name": server_name,
                "config_source": _config_source(response.get("origins"), server_name),
            },
        )

    plugins = config.get("plugins")
    if not isinstance(plugins, dict):
        _raise_unverifiable_config(config, "plugins", plugins)
    if plugins:
        raise bridge_error(
            "CODEX_ISOLATION_VIOLATION",
            reason_code="MCP_EFFECTIVE_CONFIG_NOT_EMPTY",
            diagnostics={
                "stage": "effective_config_validation",
                "field": "plugins",
                "state": "non_empty",
                "source_count": len(plugins),
                "config_source": _config_source(response.get("origins"), "plugins"),
            },
        )

    features = config.get("features")
    if not isinstance(features, dict):
        _raise_unverifiable_config(config, "features", features)
    for name in _MCP_FEATURES:
        if name not in features:
            raise bridge_error(
                "CODEX_ISOLATION_VIOLATION",
                reason_code="MCP_EFFECTIVE_CONFIG_UNVERIFIABLE",
                diagnostics={
                    "stage": "effective_config_validation",
                    "field": f"features.{name}",
                    "state": "missing",
                },
            )
        if features[name] is not False:
            raise bridge_error(
                "CODEX_ISOLATION_VIOLATION",
                reason_code="MCP_EFFECTIVE_FEATURE_NOT_DISABLED",
                diagnostics={
                    "stage": "effective_config_validation",
                    "field": f"features.{name}",
                    "state": "mismatch",
                    "actual": features[name],
                    "expected": False,
                },
            )

    layers = response.get("layers")
    if not isinstance(layers, list):
        _raise_unverifiable_config(response, "layers", layers)
    user_layer_seen = False
    for layer in layers:
        if not isinstance(layer, dict) or not isinstance(layer.get("name"), dict):
            _raise_unverifiable_config(response, "layers.name", layer)
        source = layer["name"]
        source_type = source.get("type")
        if source_type == "project":
            raise bridge_error(
                "CODEX_ISOLATION_VIOLATION",
                reason_code="MCP_CONFIG_SOURCE_MISMATCH",
                diagnostics={
                    "stage": "effective_config_validation",
                    "field": "layers.project",
                    "state": "present",
                    "matches": False,
                    "config_source": "project",
                },
            )
        if source_type != "user":
            continue
        user_layer_seen = True
        config_file = source.get("file")
        if not isinstance(config_file, str):
            _raise_unverifiable_config(source, "layers.user.file", config_file)
        if not _path_is_within(Path(config_file), codex_home):
            raise bridge_error(
                "CODEX_ISOLATION_VIOLATION",
                reason_code="MCP_CONFIG_SOURCE_MISMATCH",
                diagnostics={
                    "stage": "effective_config_validation",
                    "field": "layers.user.file",
                    "state": "mismatch",
                    "matches": False,
                    "config_source": "user",
                },
            )
    if not user_layer_seen:
        raise bridge_error(
            "CODEX_ISOLATION_VIOLATION",
            reason_code="MCP_EFFECTIVE_CONFIG_UNVERIFIABLE",
            diagnostics={
                "stage": "effective_config_validation",
                "field": "layers.user",
                "state": "missing",
            },
        )


def _raise_unverifiable_config(
    container: dict[str, Any], field: str, value: object
) -> None:
    state = "missing" if field.rsplit(".", 1)[-1] not in container or value is None else "invalid_type"
    raise bridge_error(
        "CODEX_ISOLATION_VIOLATION",
        reason_code="MCP_EFFECTIVE_CONFIG_UNVERIFIABLE",
        diagnostics={
            "stage": "effective_config_validation",
            "field": field,
            "state": state,
            "value_type": type(value).__name__,
        },
    )


def _validate_mcp_registry(response: dict[str, Any]) -> None:
    data = response.get("data")
    if not isinstance(data, list):
        state = "missing" if "data" not in response or data is None else "invalid_type"
        raise bridge_error(
            "CODEX_ISOLATION_VIOLATION",
            reason_code="MCP_SERVER_REGISTRY_UNVERIFIABLE",
            diagnostics={
                "stage": "mcp_registry_validation",
                "field": "data",
                "state": state,
                "value_type": type(data).__name__,
            },
        )
    if not data:
        return
    first = data[0] if isinstance(data[0], dict) else {}
    raise bridge_error(
        "CODEX_ISOLATION_VIOLATION",
        reason_code="MCP_SERVER_REGISTRY_NOT_EMPTY",
        diagnostics={
            "stage": "mcp_registry_validation",
            "field": "data",
            "state": "non_empty",
            "source_count": len(data),
            "server_name": first.get("name"),
            "server_status": first.get("runtimeStatus"),
            "config_source": "plugin" if first.get("pluginId") else "configured",
        },
    )


def _first_string_key(value: dict[object, object]) -> str | None:
    return next((key for key in sorted(value, key=str) if isinstance(key, str)), None)


def _config_source(origins: object, key: str | None) -> str | None:
    if not isinstance(origins, dict) or key is None:
        return None
    prefixes = (key, f"mcp_servers.{key}")
    for path, metadata in origins.items():
        if not isinstance(path, str) or not path.startswith(prefixes):
            continue
        if isinstance(metadata, dict) and isinstance(metadata.get("name"), dict):
            source_type = metadata["name"].get("type")
            if isinstance(source_type, str):
                return source_type
    return None


def _path_is_within(candidate: Path, parent: Path) -> bool:
    try:
        candidate.resolve().relative_to(parent.resolve())
    except (OSError, ValueError):
        return False
    return True


def _validate_thread_response(
    response: dict[str, Any], *, sandbox: Path, requested_model: object
) -> str:
    thread = response.get("thread")
    if not isinstance(thread, dict):
        state = "missing" if "thread" not in response or thread is None else "invalid_type"
        raise bridge_error(
            "CODEX_PROTOCOL_INCOMPATIBLE",
            reason_code=(
                "THREAD_RESPONSE_FIELD_MISSING"
                if state == "missing"
                else "THREAD_RESPONSE_FIELD_INVALID"
            ),
            diagnostics={
                "stage": "thread_validation",
                "field": "thread",
                "state": state,
                "value_type": type(thread).__name__,
            },
        )
    policy = response.get("sandbox")
    if not isinstance(policy, dict):
        state = "missing" if "sandbox" not in response or policy is None else "invalid_type"
        raise bridge_error(
            "CODEX_ISOLATION_VIOLATION",
            reason_code=(
                "THREAD_SAFETY_FIELD_MISSING"
                if state == "missing"
                else "THREAD_SAFETY_FIELD_INVALID"
            ),
            diagnostics={
                "stage": "thread_validation",
                "field": "sandbox",
                "state": state,
                "value_type": type(policy).__name__,
            },
        )

    required_fields = (
        (response, "cwd", "cwd"),
        (response, "model", "model"),
        (response, "approvalPolicy", "approvalPolicy"),
        (response, "instructionSources", "instructionSources"),
        (policy, "type", "sandbox.type"),
        (policy, "networkAccess", "sandbox.networkAccess"),
        (thread, "cwd", "thread.cwd"),
        (thread, "ephemeral", "thread.ephemeral"),
    )
    for container, key, field in required_fields:
        if key not in container or container[key] is None:
            raise bridge_error(
                "CODEX_ISOLATION_VIOLATION",
                reason_code="THREAD_SAFETY_FIELD_MISSING",
                diagnostics={
                    "stage": "thread_validation",
                    "field": field,
                    "state": "missing",
                },
            )

    instruction_sources = response["instructionSources"]
    if not isinstance(instruction_sources, list):
        raise bridge_error(
            "CODEX_ISOLATION_VIOLATION",
            reason_code="THREAD_SAFETY_FIELD_INVALID",
            diagnostics={
                "stage": "thread_validation",
                "field": "instructionSources",
                "state": "invalid_type",
                "value_type": type(instruction_sources).__name__,
            },
        )
    if instruction_sources:
        raise bridge_error(
            "CODEX_ISOLATION_VIOLATION",
            reason_code="THREAD_INSTRUCTION_SOURCES_PRESENT",
            diagnostics={
                "stage": "thread_validation",
                "field": "instructionSources",
                "state": "non_empty",
                "source_count": len(instruction_sources),
            },
        )

    try:
        returned_cwd = Path(str(response["cwd"])).resolve()
        thread_cwd = Path(str(thread["cwd"])).resolve()
    except (OSError, ValueError):
        raise bridge_error(
            "CODEX_ISOLATION_VIOLATION",
            reason_code="THREAD_DIRECTORY_INVALID",
            diagnostics={
                "stage": "thread_validation",
                "field": "cwd",
                "state": "invalid",
                "matches": False,
            },
        ) from None
    for field, candidate in (("cwd", returned_cwd), ("thread.cwd", thread_cwd)):
        if candidate != sandbox:
            raise bridge_error(
                "CODEX_ISOLATION_VIOLATION",
                reason_code="THREAD_DIRECTORY_MISMATCH",
                diagnostics={
                    "stage": "thread_validation",
                    "field": field,
                    "state": "mismatch",
                    "matches": False,
                },
            )

    expected_values = (
        ("approvalPolicy", response["approvalPolicy"], "never"),
        ("sandbox.type", policy["type"], "readOnly"),
        ("sandbox.networkAccess", policy["networkAccess"], False),
        ("thread.ephemeral", thread["ephemeral"], True),
    )
    for field, actual, expected in expected_values:
        if actual != expected:
            raise bridge_error(
                "CODEX_ISOLATION_VIOLATION",
                reason_code="THREAD_PERMISSION_MISMATCH",
                diagnostics={
                    "stage": "thread_validation",
                    "field": field,
                    "state": "mismatch",
                    "actual": actual,
                    "expected": expected,
                },
            )

    if response["model"] != requested_model:
        raise bridge_error(
            "CODEX_ISOLATION_VIOLATION",
            reason_code="THREAD_MODEL_MISMATCH",
            diagnostics={
                "stage": "thread_validation",
                "field": "model",
                "state": "mismatch",
                "matches": False,
            },
        )
    thread_id = thread.get("id")
    if not isinstance(thread_id, str) or not thread_id:
        raise bridge_error(
            "CODEX_RESPONSE_INVALID",
            reason_code="THREAD_ID_MISSING",
            diagnostics={
                "stage": "thread_validation",
                "field": "thread.id",
                "state": "missing" if "id" not in thread else "invalid",
            },
        )
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
    if any(
        not isinstance(item, int) or isinstance(item, bool) or item < 0 for item in result.values()
    ):
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
    if isinstance(value, dict) and value.get("code") in {-32600, -32601, -32602}:
        return bridge_error(
            "CODEX_PROTOCOL_INCOMPATIBLE",
            reason_code="RPC_REQUEST_REJECTED",
            diagnostics={"stage": "rpc_response", "rpc_id": value["code"]},
        )
    if isinstance(value, dict):
        data = value.get("data")
        if isinstance(data, dict):
            return _map_codex_error(data.get("codexErrorInfo"))
    return bridge_error("CODEX_CONNECTION_FAILED", reason_code="RPC_ERROR_UNCLASSIFIED")


def _turn_error(value: object) -> CodexBridgeError:
    if isinstance(value, dict):
        return _map_codex_error(value.get("codexErrorInfo"))
    return bridge_error("CODEX_CONNECTION_FAILED", reason_code="TURN_ERROR_UNCLASSIFIED")


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
        kind = next(key for key in (
            "httpConnectionFailed", "responseStreamConnectionFailed",
            "responseStreamDisconnected", "responseTooManyFailedAttempts",
        ) if key in value)
        return bridge_error(
            "CODEX_CONNECTION_FAILED", reason_code="CODEX_UPSTREAM_CONNECTION_FAILED",
            diagnostics={"stage": "codex_error", "state": kind},
        )
    return bridge_error("CODEX_CONNECTION_FAILED", reason_code="CODEX_ERROR_UNCLASSIFIED")
