"""Protocol substitute for Codex bridge tests; it never contacts a model."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


SCENARIO = os.environ.get("FAKE_CODEX_SCENARIO", "happy")
LOG_PATH = os.environ.get("FAKE_CODEX_LOG")


def emit(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def log(message: dict[str, Any]) -> None:
    if LOG_PATH:
        with Path(LOG_PATH).open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(message, separators=(",", ":")) + "\n")


def response(request_id: int, result: object) -> None:
    emit({"id": request_id, "result": result})


def rpc_error(request_id: int, code: int = -32602) -> None:
    emit({"id": request_id, "error": {"code": code, "message": "synthetic failure"}})


def hardening_is_valid(params: dict[str, Any]) -> bool:
    config = params.get("config", {})
    features = config.get("features", {}) if isinstance(config, dict) else {}
    required_disabled = {
        "apps",
        "browser_use",
        "memories",
        "multi_agent",
        "plugins",
        "shell_tool",
        "unified_exec",
    }
    cwd = Path(params.get("cwd", ""))
    return (
        "RAGOPS_CODEX_BRIDGE_TOKEN" not in os.environ
        and "OPENAI_API_KEY" not in os.environ
        and params.get("approvalPolicy") == "never"
        and params.get("sandbox") == "read-only"
        and params.get("ephemeral") is True
        and cwd.is_absolute()
        and cwd.is_dir()
        and not any(cwd.iterdir())
        and config.get("web_search") == "disabled"
        and config.get("mcp_servers") == {}
        and all(features.get(feature) is False for feature in required_disabled)
    )


def emit_happy_turn() -> None:
    emit(
        {
            "method": "turn/started",
            "params": {"turn": {"id": "turn-1", "status": "inProgress", "items": []}},
        }
    )
    emit(
        {
            "method": "item/completed",
            "params": {
                "threadId": "thread-1",
                "turnId": "turn-1",
                "item": {"id": "reason-1", "type": "reasoning", "summary": []},
            },
        }
    )
    emit(
        {
            "method": "item/completed",
            "params": {
                "threadId": "thread-1",
                "turnId": "turn-1",
                "item": {
                    "id": "message-progress",
                    "type": "agentMessage",
                    "phase": "commentary",
                    "text": "progress that must not escape",
                },
            },
        }
    )
    emit(
        {
            "method": "thread/tokenUsage/updated",
            "params": {
                "threadId": "thread-1",
                "turnId": "turn-1",
                "tokenUsage": {
                    "last": {
                        "inputTokens": 11,
                        "cachedInputTokens": 2,
                        "outputTokens": 7,
                        "reasoningOutputTokens": 3,
                        "totalTokens": 18,
                    },
                    "total": {
                        "inputTokens": 11,
                        "cachedInputTokens": 2,
                        "outputTokens": 7,
                        "reasoningOutputTokens": 3,
                        "totalTokens": 18,
                    },
                    "modelContextWindow": 1000,
                },
            },
        }
    )
    if SCENARIO == "rerouted":
        emit(
            {
                "method": "model/rerouted",
                "params": {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "fromModel": "requested-model",
                    "toModel": "safe-model",
                    "reason": "highRiskCyberActivity",
                },
            }
        )
    final_item = {
        "id": "message-final",
        "type": "agentMessage",
        "phase": "final_answer",
        "text": "Grounded synthetic answer.",
    }
    if SCENARIO != "no_final":
        emit(
            {
                "method": "item/completed",
                "params": {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "item": final_item,
                },
            }
        )
    items = [] if SCENARIO == "no_final" else [final_item]
    emit(
        {
            "method": "turn/completed",
            "params": {
                "threadId": "thread-1",
                "turn": {"id": "turn-1", "status": "completed", "items": items},
            },
        }
    )


def main() -> None:
    for raw_line in sys.stdin:
        message = json.loads(raw_line)
        log(message)
        method = message.get("method")
        request_id = message.get("id")
        params = message.get("params") or {}
        if method == "initialized":
            continue
        if method == "initialize":
            response(request_id, {"userAgent": "fake", "platformFamily": "windows"})
        elif method == "account/read":
            response(
                request_id,
                {
                    "account": {
                        "type": "chatgpt",
                        "email": "must-not-leak@example.test",
                        "planType": "plus",
                    },
                    "requiresOpenaiAuth": True,
                },
            )
        elif method == "model/list":
            response(
                request_id,
                {
                    "data": [
                        {
                            "id": "catalog-1",
                            "model": "requested-model",
                            "displayName": "Requested Model",
                            "description": "synthetic",
                            "isDefault": True,
                            "hidden": False,
                            "defaultReasoningEffort": "medium",
                            "supportedReasoningEfforts": [
                                {"reasoningEffort": "medium", "description": "Synthetic"}
                            ],
                        }
                    ],
                    "nextCursor": None,
                },
            )
        elif method == "account/rateLimits/read":
            response(
                request_id,
                {
                    "accountId": "must-not-leak",
                    "rateLimits": {
                        "limitId": "codex",
                        "primary": {
                            "usedPercent": 25,
                            "windowDurationMins": 15,
                            "resetsAt": 1_900_000_000,
                        },
                        "secondary": None,
                        "credits": {"balance": "secret-ish", "hasCredits": True},
                        "rateLimitReachedType": None,
                    },
                },
            )
        elif method == "thread/start":
            if not hardening_is_valid(params):
                rpc_error(request_id)
                continue
            sources = [str(Path(params["cwd"]) / "AGENTS.md")] if SCENARIO == "instructions" else []
            response(
                request_id,
                {
                    "thread": {
                        "id": "thread-1",
                        "ephemeral": True,
                        "cwd": params["cwd"],
                    },
                    "model": params["model"],
                    "modelProvider": "openai",
                    "cwd": params["cwd"],
                    "approvalPolicy": "never",
                    "approvalsReviewer": "user",
                    "sandbox": {"type": "readOnly", "networkAccess": False},
                    "instructionSources": sources,
                },
            )
        elif method == "turn/start":
            if SCENARIO == "rpc_error":
                rpc_error(request_id)
                continue
            sandbox_policy = params.get("sandboxPolicy", {})
            if (
                params.get("approvalPolicy") != "never"
                or sandbox_policy != {"type": "readOnly", "networkAccess": False}
            ):
                rpc_error(request_id)
                continue
            response(
                request_id,
                {"turn": {"id": "turn-1", "status": "inProgress", "items": []}},
            )
            if SCENARIO == "timeout":
                continue
            if SCENARIO == "tool":
                emit(
                    {
                        "method": "item/started",
                        "params": {
                            "threadId": "thread-1",
                            "turnId": "turn-1",
                            "item": {
                                "id": "tool-1",
                                "type": "commandExecution",
                                "command": "whoami",
                                "status": "inProgress",
                            },
                        },
                    }
                )
                continue
            if SCENARIO == "server_error":
                emit(
                    {
                        "method": "error",
                        "params": {
                            "threadId": "thread-1",
                            "turnId": "turn-1",
                            "willRetry": False,
                            "error": {
                                "message": "raw error must not escape",
                                "codexErrorInfo": "internalServerError",
                            },
                        },
                    }
                )
                continue
            emit_happy_turn()
        elif method == "turn/interrupt":
            response(request_id, {})
        else:
            rpc_error(request_id, -32601)


if __name__ == "__main__":
    main()
