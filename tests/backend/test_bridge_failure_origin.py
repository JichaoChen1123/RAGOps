"""Regression cases for misleading provider-server errors from the local bridge."""
import json

import pytest
from fastapi.testclient import TestClient

from app.codex_bridge.app import BridgeConfig, create_bridge_app
from app.codex_bridge.protocol import _map_codex_error, _rpc_error
from app.execution.adapters import _bridge_error
from app.execution.model import ModelErrorCode, ModelTransportResponse


def test_connection_failure_is_not_a_provider_server_failure():
    failure = _map_codex_error({'responseStreamDisconnected': {'message': 'SECRET'}})
    response = ModelTransportResponse(status_code=502, headers={}, body=json.dumps({
        'detail': {'code': failure.code, 'reason_code': failure.reason_code,
                   'diagnostic_id': failure.diagnostic_id}
    }).encode())
    mapped = _bridge_error(response, provider_request_id=None)
    assert mapped.code == ModelErrorCode.transport_error
    assert mapped.reason_code == 'CODEX_UPSTREAM_CONNECTION_FAILED'
    assert mapped.diagnostic_id == failure.diagnostic_id


@pytest.mark.parametrize('code', [-32600, -32601, -32602])
def test_rejected_rpc_is_protocol_error(code, caplog):
    error = _rpc_error({'code': code, 'message': 'SECRET invalid params'})
    assert error.code == 'CODEX_PROTOCOL_INCOMPATIBLE'
    assert error.reason_code == 'RPC_REQUEST_REJECTED'
    assert 'SECRET' not in caplog.text


def test_internal_failure_is_safe_and_releases_lock(tmp_path, caplog):
    class Runner:
        calls = 0

        def inspect(self):
            self.calls += 1
            if self.calls == 1:
                raise PermissionError('SECRET C:/private/auth.json')
            return {'authentication_status': 'authenticated'}

    runner = Runner()
    app = create_bridge_app(BridgeConfig(
        access_token='b' * 32, sandbox_root=tmp_path / 'sandbox',
        codex_home=tmp_path / 'home'), runner_factory=lambda: runner)
    with TestClient(app) as client:
        headers = {'Authorization': 'Bearer ' + 'b' * 32}
        response = client.get('/v1/status', headers=headers)
        assert response.status_code == 500
        detail = response.json()['detail']
        assert detail['code'] == 'CODEX_BRIDGE_INTERNAL_ERROR'
        assert detail['reason_code'] == 'BRIDGE_UNEXPECTED_EXCEPTION'
        assert detail['diagnostic_id'] in caplog.text
        assert 'PermissionError' in caplog.text
        assert 'SECRET' not in response.text + caplog.text
        assert 'auth.json' not in response.text + caplog.text
        assert client.get('/v1/status', headers=headers).status_code == 200
