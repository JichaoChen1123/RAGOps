"""Offline line-delimited JSON-RPC substitute for Codex App Server tests."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


SCENARIO = os.environ.get("FAKE_CODEX_SCENARIO", "happy")
LOG_PATH = os.environ.get("FAKE_CODEX_LOG")


def emit(message: object) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def log(message: object) -> None:
    if LOG_PATH:
        with Path(LOG_PATH).open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(message, separators=(",", ":")) + "\n")


def respond(request_id: int, result: object) -> None:
    emit({"id": request_id, "result": result})


def rpc_error(request_id: int, error_info: object = "internalServerError") -> None:
    emit(
        {
            "id": request_id,
            "error": {
                "code": -32000,
                "message": "private synthetic error",
                "data": {"codexErrorInfo": error_info},
            },
        }
    )


def hardening_is_valid(params: dict[str, Any]) -> bool:
    cwd = Path(str(params.get("cwd", "")))
    return (
        "RAGOPS_CODEX_BRIDGE_TOKEN" not in os.environ
        and "OPENAI_API_KEY" not in os.environ
        and params.get("allowProviderModelFallback") is False
        and params.get("approvalPolicy") == "never"
        and params.get("sandbox") == "read-only"
        and params.get("ephemeral") is True
        and params.get("dynamicTools") == []
        and params.get("environments") == []
        and params.get("selectedCapabilityRoots") == []
        and params.get("config") == {"mcp_servers": {}, "web_search": "disabled"}
        and params.get("runtimeWorkspaceRoots") == [str(cwd)]
        and cwd.is_absolute()
        and cwd.is_dir()
        and not any(cwd.iterdir())
    )


def emit_turn() -> None:
    thread_id = "thread-offline"
    turn_id = "turn-offline"
    emit({"method": "turn/started", "params": {"threadId": thread_id, "turn": {"id": turn_id}}})
    emit(
        {
            "method": "item/completed",
            "params": {
                "threadId": thread_id,
                "turnId": turn_id,
                "item": {"id": "reason-1", "type": "reasoning"},
            },
        }
    )
    emit(
        {
            "method": "item/completed",
            "params": {
                "threadId": thread_id,
                "turnId": turn_id,
                "item": {
                    "id": "commentary-1",
                    "type": "agentMessage",
                    "phase": "commentary",
                    "text": "progress must not become the answer",
                },
            },
        }
    )
    if SCENARIO == "duplicate_final":
        emit(
            {
                "method": "item/completed",
                "params": {
                    "threadId": thread_id,
                    "turnId": turn_id,
                    "item": {
                        "id": "final-extra",
                        "type": "agentMessage",
                        "phase": "final_answer",
                        "text": '{"answer":"extra"}',
                    },
                },
            }
        )
    if SCENARIO != "missing_final":
        emit(
            {
                "method": "item/completed",
                "params": {
                    "threadId": thread_id,
                    "turnId": turn_id,
                    "item": {
                        "id": "final-1",
                        "type": "agentMessage",
                        "phase": "final_answer",
                        "text": '{"answer":"offline grounded answer"}',
                    },
                },
            }
        )
    emit(
        {
            "method": "thread/tokenUsage/updated",
            "params": {
                "threadId": thread_id,
                "turnId": turn_id,
                "tokenUsage": {"last": {"inputTokens": 11, "outputTokens": 4, "totalTokens": 15}},
            },
        }
    )
    if SCENARIO == "rerouted":
        emit(
            {
                "method": "model/rerouted",
                "params": {
                    "threadId": thread_id,
                    "turnId": turn_id,
                    "toModel": "account-model-rerouted",
                },
            }
        )
    emit(
        {
            "method": "turn/completed",
            "params": {
                "threadId": thread_id,
                "turn": {"id": turn_id, "status": "completed"},
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
        if method == "initialized" or method is None:
            continue
        if method == "initialize":
            respond(request_id, {"userAgent": "codex-cli/0.153.4"})
        elif method == "account/read":
            if SCENARIO == "not_authenticated":
                respond(request_id, {"account": None})
            elif SCENARIO == "wrong_auth":
                respond(request_id, {"account": {"type": "apiKey"}})
            else:
                respond(
                    request_id,
                    {
                        "account": {
                            "type": "chatgpt",
                            "planType": "plus",
                            "email": "must-not-leak@example.test",
                        }
                    },
                )
        elif method == "model/list":
            respond(
                request_id,
                {
                    "data": [
                        {
                            "model": "account-model",
                            "displayName": "Account model",
                            "isDefault": True,
                            "supportedReasoningEfforts": [{"reasoningEffort": "low"}],
                        }
                    ]
                },
            )
        elif method == "account/rateLimits/read":
            respond(
                request_id,
                {
                    "rateLimits": {
                        "primary": {
                            "usedPercent": 25,
                            "resetsAt": 1_900_000_000,
                            "windowDurationMins": 15,
                        },
                        "credits": {"balance": "must-not-leak"},
                    }
                },
            )
        elif method == "thread/start":
            if not hardening_is_valid(params):
                rpc_error(request_id)
                continue
            if SCENARIO == "server_request_during_response":
                emit({"id": 901, "method": "tool/call", "params": {"command": "must-not-log"}})
                continue
            instruction_sources = ["AGENTS.md"] if SCENARIO == "instructions" else []
            respond(
                request_id,
                {
                    "thread": {
                        "id": "thread-offline",
                        "cwd": params["cwd"],
                        "ephemeral": True,
                    },
                    "cwd": params["cwd"],
                    "model": params["model"],
                    "approvalPolicy": "never",
                    "sandbox": {"type": "readOnly", "networkAccess": False},
                    "instructionSources": instruction_sources,
                },
            )
        elif method == "turn/start":
            if SCENARIO == "rpc_error":
                rpc_error(request_id, "unauthorized")
                continue
            respond(request_id, {"turn": {"id": "turn-offline"}})
            if SCENARIO == "timeout":
                continue
            if SCENARIO == "tool":
                emit(
                    {
                        "method": "item/started",
                        "params": {
                            "threadId": "thread-offline",
                            "turnId": "turn-offline",
                            "item": {"id": "tool-1", "type": "commandExecution"},
                        },
                    }
                )
                continue
            if SCENARIO == "server_request":
                emit({"id": 900, "method": "tool/call", "params": {"command": "whoami"}})
                continue
            if SCENARIO == "invalid_json":
                sys.stdout.write("not-json\n")
                sys.stdout.flush()
                continue
            if SCENARIO == "usage_limited":
                emit(
                    {
                        "method": "turn/completed",
                        "params": {
                            "threadId": "thread-offline",
                            "turn": {
                                "id": "turn-offline",
                                "status": "failed",
                                "error": {"codexErrorInfo": "usageLimitExceeded"},
                            },
                        },
                    }
                )
                continue
            emit_turn()
        elif method == "turn/interrupt":
            respond(request_id, {})
        else:
            rpc_error(request_id)


if __name__ == "__main__":
    main()
