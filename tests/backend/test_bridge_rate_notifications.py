from unittest.mock import Mock

import pytest

from app.codex_bridge.protocol import CodexAppServerRunner, CodexBridgeError


def test_rate_limit_updates_do_not_interrupt_answer_or_hide_error(tmp_path):
    runner = CodexAppServerRunner(executable="codex", sandbox_root=tmp_path,
                                  codex_home=tmp_path / "home", timeout_seconds=1)
    telemetry = {"method": "account/rateLimits/updated", "params": {
        "rateLimits": {"primary": {"usedPercent": 100}},
    }}
    rpc = Mock()
    rpc.next_notification.side_effect = [
        telemetry,
        {"method": "item/completed", "params": {
            "threadId": "t", "turnId": "u", "item": {
                "type": "agentMessage", "phase": "final_answer", "id": "m",
                "text": '{"answer":"ok"}',
            },
        }},
        telemetry,
        {"method": "turn/completed", "params": {
            "threadId": "t", "turn": {"id": "u", "status": "completed"},
        }},
    ]
    assert runner._wait_for_turn(rpc, "t", "u")[0] == '{"answer":"ok"}'
    rpc.next_notification.side_effect = [telemetry, {
        "method": "item/started", "params": {
            "threadId": "t", "turnId": "u", "item": {"type": "commandExecution"},
        },
    }]
    with pytest.raises(CodexBridgeError) as caught:
        runner._wait_for_turn(rpc, "t", "u")
    assert caught.value.code == "CODEX_ISOLATION_VIOLATION"
