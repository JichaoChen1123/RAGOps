from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.codex_bridge.cli import read_codex_version, run_bridge, validate_bind_policy
from app.codex_bridge.http import create_bridge_app, validate_bridge_token
from app.codex_bridge.models import (
    AccountStatus,
    BridgeStatus,
    GenerateRequest,
    GenerateResponse,
)
from app.codex_bridge.protocol import DISABLED_FEATURES, CodexAppServerClient, app_server_command
from app.codex_bridge.service import BridgeError, CodexBridgeService, safe_thread_config


TOKEN = "6VYtsb8R81M3Sg3UbdzvX2J4uf92VVyqW1WfXQe7Hyo="
FAKE_SERVER = Path(__file__).parents[1] / "fixtures" / "fake_codex_app_server.py"


def payload(**extra: object) -> dict[str, object]:
    return {
        "question": "What is retained?",
        "context": [{"position": 1, "text": "Audit logs are retained for 180 days."}],
        "prompt": "Answer from the context.",
        "model": "requested-model",
        **extra,
    }


def request_model() -> GenerateRequest:
    return GenerateRequest.model_validate(payload())


def process_factory(tmp_path: Path, scenario: str = "happy") -> tuple[object, Path]:
    log_path = tmp_path / f"{scenario}.jsonl"

    def factory() -> CodexAppServerClient:
        return CodexAppServerClient(
            command=(sys.executable, str(FAKE_SERVER)),
            environment={
                "FAKE_CODEX_SCENARIO": scenario,
                "FAKE_CODEX_LOG": str(log_path),
            },
        )

    return factory, log_path


def logged_requests(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_production_command_pins_all_tool_surfaces_off() -> None:
    command = app_server_command()
    assert command[:4] == ("codex", "app-server", "--stdio", "--strict-config")
    assert 'web_search="disabled"' in command
    assert "mcp_servers={}" in command
    for feature in DISABLED_FEATURES:
        index = command.index(feature)
        assert command[index - 1] == "--disable"
    config = safe_thread_config()
    assert config["mcp_servers"] == {}
    assert all(value is False for value in config["features"].values())


@pytest.mark.parametrize("token", ["", "x" * 32, " too-short ", "not-random-placeholder"])
def test_bridge_token_requires_length_and_diversity(token: str) -> None:
    with pytest.raises(ValueError):
        validate_bridge_token(token)
    assert validate_bridge_token(TOKEN) == TOKEN


def test_non_loopback_bind_requires_explicit_acknowledgement() -> None:
    validate_bind_policy("127.0.0.1", allow_non_loopback=False)
    validate_bind_policy("localhost", allow_non_loopback=False)
    validate_bind_policy("0.0.0.0", allow_non_loopback=True)
    with pytest.raises(ValueError, match="allow-non-loopback"):
        validate_bind_policy("0.0.0.0", allow_non_loopback=False)


class StubService:
    async def status(self) -> BridgeStatus:
        return BridgeStatus(
            status="not_authenticated",
            account=AccountStatus(
                authenticated=False,
                account_type=None,
                plan_type=None,
            ),
            models=[],
            rate_limits=None,
        )

    async def generate(self, _request: GenerateRequest) -> GenerateResponse:
        return GenerateResponse(
            answer="stub",
            actual_model=None,
            finish_reason=None,
            latency_ms=0,
            usage=None,
        )


def test_http_requires_bearer_and_rejects_non_contract_fields() -> None:
    app = create_bridge_app(TOKEN, service=StubService())  # type: ignore[arg-type]
    with TestClient(app) as client:
        unauthorized = client.get("/v1/status")
        wrong = client.get("/v1/status", headers={"Authorization": "Bearer wrong"})
        accepted = client.get("/v1/status", headers={"Authorization": f"Bearer {TOKEN}"})
        injected = client.post(
            "/v1/generate",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json=payload(
                cwd="C:/repo",
                command="whoami",
                config={"sandbox": "off"},
                labels=["must-not-enter-model"],
                metadata={"private": True},
                reference_answer="must-not-enter-model",
                historical_answer="must-not-enter-model",
            ),
        )

    assert unauthorized.status_code == 401
    assert unauthorized.headers["www-authenticate"] == "Bearer"
    assert wrong.status_code == 401
    assert accepted.status_code == 200
    assert injected.status_code == 422
    assert injected.json() == {
        "error": {
            "code": "CODEX_BRIDGE_INVALID_REQUEST",
            "message": "The bridge request does not match the fixed contract.",
            "retryable": False,
        }
    }
    assert "whoami" not in injected.text


def test_status_uses_required_rpcs_and_redacts_account_details(tmp_path: Path) -> None:
    factory, log_path = process_factory(tmp_path)
    result = asyncio.run(CodexBridgeService(client_factory=factory).status())

    assert result.status == "ready"
    assert result.account.model_dump() == {
        "authenticated": True,
        "account_type": "chatgpt",
        "plan_type": "plus",
    }
    assert result.models[0].model_dump() == {
        "id": "requested-model",
        "display_name": "Requested Model",
        "is_default": True,
        "reasoning_efforts": ["medium"],
    }
    serialized = result.model_dump_json()
    assert "must-not-leak" not in serialized
    assert "balance" not in serialized
    methods = [row["method"] for row in logged_requests(log_path)]
    assert methods == [
        "initialize",
        "initialized",
        "account/read",
        "model/list",
        "account/rateLimits/read",
    ]


def test_generation_uses_empty_isolated_thread_and_only_final_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RAGOPS_CODEX_BRIDGE_TOKEN", TOKEN)
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-reach-codex")
    factory, log_path = process_factory(tmp_path)
    result = asyncio.run(CodexBridgeService(client_factory=factory).generate(request_model()))

    assert result.answer == "Grounded synthetic answer."
    assert "progress" not in result.answer
    assert result.actual_model is None
    assert result.finish_reason is None
    assert result.provider_request_id is None
    assert result.is_mock is False
    assert result.usage is not None
    assert result.usage.model_dump() == {
        "input_tokens": 11,
        "output_tokens": 7,
        "total_tokens": 18,
    }
    rows = logged_requests(log_path)
    thread_start = next(row for row in rows if row["method"] == "thread/start")
    turn_start = next(row for row in rows if row["method"] == "turn/start")
    sandbox_dir = Path(thread_start["params"]["cwd"])
    assert not sandbox_dir.exists()
    assert thread_start["params"]["ephemeral"] is True
    assert turn_start["params"]["cwd"] == str(sandbox_dir)
    assert turn_start["params"]["sandboxPolicy"] == {
        "type": "readOnly",
        "networkAccess": False,
    }
    input_text = turn_start["params"]["input"][0]["text"]
    assert "What is retained?" in input_text
    assert "180 days" in input_text


def test_model_reroute_is_reported_as_actual_model(tmp_path: Path) -> None:
    factory, _ = process_factory(tmp_path, "rerouted")
    result = asyncio.run(CodexBridgeService(client_factory=factory).generate(request_model()))
    assert result.actual_model == "safe-model"


@pytest.mark.parametrize(
    ("scenario", "expected_code"),
    [
        ("instructions", "CODEX_BRIDGE_ISOLATION_FAILED"),
        ("no_final", "CODEX_RESPONSE_INVALID"),
        ("rpc_error", "CODEX_BRIDGE_PROTOCOL_ERROR"),
        ("server_error", "CODEX_GENERATION_FAILED"),
    ],
)
def test_protocol_failures_are_closed_and_sanitized(
    tmp_path: Path,
    scenario: str,
    expected_code: str,
) -> None:
    factory, _ = process_factory(tmp_path, scenario)
    service = CodexBridgeService(client_factory=factory)
    with pytest.raises(BridgeError) as caught:
        asyncio.run(service.generate(request_model()))
    assert caught.value.code == expected_code
    assert "synthetic failure" not in caught.value.message
    assert "raw error" not in caught.value.message


def test_tool_event_interrupts_and_fails_the_turn(tmp_path: Path) -> None:
    factory, log_path = process_factory(tmp_path, "tool")
    with pytest.raises(BridgeError, match="forbidden tool") as caught:
        asyncio.run(CodexBridgeService(client_factory=factory).generate(request_model()))
    assert caught.value.code == "CODEX_BRIDGE_TOOL_EVENT"
    methods = [row["method"] for row in logged_requests(log_path)]
    assert methods.count("turn/start") == 1
    assert methods.count("turn/interrupt") == 1


def test_process_concurrency_is_one() -> None:
    tracker = {"active": 0, "maximum": 0}

    class CountingClient:
        async def __aenter__(self) -> CountingClient:
            tracker["active"] += 1
            tracker["maximum"] = max(tracker["maximum"], tracker["active"])
            return self

        async def __aexit__(self, *_args: object) -> None:
            tracker["active"] -= 1

        async def request(
            self,
            method: str,
            _params: object = None,
            **_kwargs: object,
        ) -> object:
            await asyncio.sleep(0.01)
            if method == "account/read":
                return {"account": None, "requiresOpenaiAuth": True}
            if method == "model/list":
                return {"data": []}
            return {"rateLimits": {"primary": None, "secondary": None}}

    async def exercise() -> None:
        service = CodexBridgeService(client_factory=CountingClient)  # type: ignore[arg-type]
        await asyncio.gather(service.status(), service.status())

    asyncio.run(exercise())
    assert tracker["maximum"] == 1


def test_timeout_interrupts_without_resubmitting(tmp_path: Path) -> None:
    factory, log_path = process_factory(tmp_path, "timeout")
    service = CodexBridgeService(client_factory=factory, turn_timeout_seconds=0.05)
    with pytest.raises(BridgeError) as caught:
        asyncio.run(service.generate(request_model()))
    assert caught.value.code == "CODEX_BRIDGE_TIMEOUT"
    methods = [row["method"] for row in logged_requests(log_path)]
    assert methods.count("turn/start") == 1
    assert methods.count("turn/interrupt") == 1


def test_cli_version_parser_and_server_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "codex-cli 0.153.4\n", ""),
    )
    assert read_codex_version() == (0, 153, 4)

    captured: dict[str, object] = {}

    def fake_run(app: object, **kwargs: object) -> None:
        captured.update(kwargs)
        captured["app"] = app

    monkeypatch.setenv("RAGOPS_CODEX_BRIDGE_TOKEN", TOKEN)
    monkeypatch.setattr("app.codex_bridge.cli.uvicorn.run", fake_run)
    run_bridge(
        host="0.0.0.0",
        port=8765,
        allow_non_loopback=True,
        turn_timeout_seconds=120,
    )
    assert captured["host"] == "0.0.0.0"
    assert captured["workers"] == 1
    assert captured["access_log"] is False
