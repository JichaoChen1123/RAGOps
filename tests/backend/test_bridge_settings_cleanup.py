from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.codex_bridge import protocol


def runner(tmp_path):
    return protocol.CodexAppServerRunner(
        executable="codex", sandbox_root=tmp_path / "sandbox",
        codex_home=tmp_path / "home", timeout_seconds=1,
    )


def settings(tmp_path):
    return {
        "cwd": str(tmp_path), "model": "test-model", "approvalPolicy": "never",
        "sandboxPolicy": {"type": "readOnly", "networkAccess": False},
    }


def rpc_with_settings(value):
    rpc = Mock()
    rpc.next_notification.side_effect = [
        {"method": "thread/settings/updated", "params": {
            "threadId": "thread", "threadSettings": value,
        }},
        {"method": "item/completed", "params": {
            "threadId": "thread", "turnId": "turn", "item": {
                "type": "agentMessage", "phase": "final_answer", "id": "message",
                "text": '{"answer":"ok"}',
            },
        }},
        {"method": "turn/completed", "params": {
            "threadId": "thread", "turn": {"id": "turn", "status": "completed"},
        }},
    ]
    return rpc


@pytest.mark.parametrize("explicit_network", [True, False])
def test_settings_notification_allows_safe_generation(tmp_path, explicit_network):
    value = settings(tmp_path)
    if not explicit_network:
        del value["sandboxPolicy"]["networkAccess"]
    answer, _, _ = runner(tmp_path)._wait_for_turn(
        rpc_with_settings(value), "thread", "turn",
        sandbox=tmp_path, expected_model="test-model",
    )
    assert answer == '{"answer":"ok"}'


@pytest.mark.parametrize("change", [
    {"cwd": "elsewhere"}, {"model": "other"}, {"approvalPolicy": "on-request"},
    {"sandboxPolicy": {"type": "dangerFullAccess"}},
    {"sandboxPolicy": {"type": "readOnly", "networkAccess": True}},
    {"sandboxPolicy": None},
])
def test_settings_notification_rejects_permission_or_context_drift(tmp_path, change):
    value = deepcopy(settings(tmp_path))
    value.update(change)
    with pytest.raises(protocol.CodexBridgeError) as caught:
        runner(tmp_path)._wait_for_turn(
            rpc_with_settings(value), "thread", "turn",
            sandbox=tmp_path, expected_model="test-model",
        )
    assert caught.value.code == "CODEX_ISOLATION_VIOLATION"
    assert caught.value.reason_code == "THREAD_SETTINGS_UNSAFE_OR_INVALID"


@pytest.mark.parametrize("generation_fails", [True, False])
def test_busy_directory_does_not_mask_generation(tmp_path, monkeypatch, caplog, generation_fails):
    instance = runner(tmp_path)
    original = protocol.bridge_error("CODEX_PROTOCOL_INCOMPATIBLE")
    generate = Mock(side_effect=original) if generation_fails else Mock(return_value={"answer": "ok"})
    monkeypatch.setattr(instance, "_generate_in_sandbox", generate)
    remove = Mock(side_effect=PermissionError("SECRET-WINDOWS-PATH"))
    monkeypatch.setattr(protocol.shutil, "rmtree", remove)
    monkeypatch.setattr(protocol.time, "sleep", lambda _: None)
    if generation_fails:
        with pytest.raises(protocol.CodexBridgeError) as caught:
            instance.generate({})
        assert caught.value is original
    else:
        assert instance.generate({}) == {"answer": "ok"}
    assert remove.call_count == 3
    assert "sandbox_cleanup_deferred" in caplog.text
    assert "SECRET-WINDOWS-PATH" not in caplog.text


def test_cleanup_retries_transient_directory_lock(tmp_path, monkeypatch):
    instance = runner(tmp_path)
    monkeypatch.setattr(instance, "_generate_in_sandbox", lambda *_: {"answer": "ok"})
    original_remove = protocol.shutil.rmtree
    attempts = []

    def remove(path):
        attempts.append(path)
        if len(attempts) == 1:
            raise PermissionError("busy")
        original_remove(path)

    monkeypatch.setattr(protocol.shutil, "rmtree", remove)
    monkeypatch.setattr(protocol.time, "sleep", lambda _: None)
    assert instance.generate({}) == {"answer": "ok"}
    assert len(attempts) == 2
    assert not Path(attempts[-1]).exists()


@pytest.mark.parametrize("params, reason", [
    (None, "THREAD_SETTINGS_PAYLOAD_INVALID"),
    ({"threadId": "other", "threadSettings": {}}, "THREAD_SETTINGS_SCOPE_INVALID"),
])
def test_settings_rejects_malformed_or_unrelated_notification(tmp_path, params, reason):
    rpc = Mock()
    rpc.next_notification.return_value = {"method": "thread/settings/updated", "params": params}
    with pytest.raises(protocol.CodexBridgeError) as caught:
        runner(tmp_path)._wait_for_turn(
            rpc, "thread", "turn", sandbox=tmp_path, expected_model="test-model",
        )
    assert caught.value.reason_code == reason
