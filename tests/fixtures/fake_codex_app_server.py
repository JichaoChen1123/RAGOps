"""Offline line-delimited JSON-RPC substitute for Codex App Server tests."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


SCENARIO = os.environ.get("FAKE_CODEX_SCENARIO", "happy")
LOG_PATH = os.environ.get("FAKE_CODEX_LOG")
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
            if SCENARIO == "mcp_startup":
                emit(
                    {
                        "method": "mcpServer/startupStatus/updated",
                        "params": {
                            "name": "inherited_server",
                            "status": "starting",
                            "failureReason": None,
                            "threadId": None,
                            "error": "https://secret.invalid/?token=must-not-log",
                        },
                    }
                )
            respond(request_id, {"userAgent": "codex-cli/0.153.4"})
        elif method == "config/read":
            codex_home = Path(os.environ["CODEX_HOME"])
            config_path = codex_home / "config.toml"
            inherited_mcp = config_path.exists() and "[mcp_servers." in config_path.read_text(
                encoding="utf-8"
            )
            config: dict[str, Any] = {
                "mcp_servers": {"inherited_server": {"enabled": True}}
                if inherited_mcp
                else {},
                "plugins": {},
                "features": {name: False for name in DISABLED_FEATURES},
            }
            if SCENARIO == "missing_effective_mcp":
                config.pop("mcp_servers")
            respond(
                request_id,
                {
                    "config": config,
                    "origins": {},
                    "layers": [
                        {
                            "name": {"type": "user", "file": str(config_path)},
                            "config": {},
                            "version": "test",
                        },
                        {
                            "name": {"type": "sessionFlags"},
                            "config": {},
                            "version": "test",
                        },
                    ],
                },
            )
        elif method == "mcpServerStatus/list":
            respond(
                request_id,
                {
                    "data": [
                        {
                            "name": "registered_server",
                            "runtimeStatus": "connected",
                            "pluginId": None,
                        }
                    ]
                    if SCENARIO == "mcp_registered"
                    else []
                },
            )
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
            if SCENARIO == "mcp_tool":
                emit(
                    {
                        "method": "item/started",
                        "params": {
                            "threadId": "thread-offline",
                            "turnId": "turn-offline",
                            "item": {"id": "mcp-1", "type": "mcpToolCall"},
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
            if SCENARIO == "remote_control":
                emit(
                    {
                        "method": "remoteControl/status/changed",
                        "params": {"status": "disconnected"},
                    }
                )
            emit_turn()
        elif method == "turn/interrupt":
            respond(request_id, {})
        else:
            rpc_error(request_id)


if __name__ == "__main__":
    main()
