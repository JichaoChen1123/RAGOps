from __future__ import annotations

import asyncio
import json

import pytest
import httpx

from app.core.config import Settings
from app.execution.adapters import HttpxModelTransport, OpenAICompatibleAdapter, OpenAICompatibleConfig
from app.execution.executor import ModelEvaluationExecutor, _parse_citations
from app.execution.model import (
    GenerationConfig,
    ModelContext,
    ModelError,
    ModelErrorCode,
    ModelRequest,
    ModelTransportRequest,
    ModelTransportResponse,
)
from app.persistence.models import DatasetSample


class MemoryTransport:
    def __init__(self, scripted: list[ModelTransportResponse | Exception]) -> None:
        self.scripted = list(scripted)
        self.requests: list[ModelTransportRequest] = []

    def send(self, request: ModelTransportRequest) -> ModelTransportResponse:
        self.requests.append(request)
        item = self.scripted.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _settings(**overrides) -> Settings:
    values = dict(
        environment="test",
        database_url="sqlite://",
        model_request_timeout_ms=100,
        model_total_timeout_ms=1_000,
        model_max_attempts=3,
        model_retry_base_ms=0,
        model_retry_max_delay_ms=0,
    )
    values.update(overrides)
    return Settings(**values)


def _config() -> OpenAICompatibleConfig:
    return OpenAICompatibleConfig(
        base_url="https://provider.invalid/v1",
        auth_mode="bearer",
        api_key="test-secret-key",
        default_model="provider-default",
    )


def _request() -> ModelRequest:
    return ModelRequest(
        question="What is the policy?",
        context=[ModelContext(position=1, text="Only this safe context is visible.")],
        prompt="Use only context.",
        generation=GenerationConfig(
            model="requested-model",
            temperature=0.2,
            top_p=0.9,
            max_output_tokens=123,
            stop=["END"],
            seed=7,
        ),
    )


def _response(status_code: int, body: object, **headers: str) -> ModelTransportResponse:
    return ModelTransportResponse(
        status_code=status_code,
        headers=headers,
        body=json.dumps(body).encode(),
    )


def _adapter(transport: MemoryTransport, **settings_overrides) -> OpenAICompatibleAdapter:
    return OpenAICompatibleAdapter(
        _config(),
        _settings(**settings_overrides),
        transport=transport,
        transport_is_mock=True,
        sleeper=lambda _: None,
    )


def test_openai_compatible_maps_whitelisted_request_and_response() -> None:
    transport = MemoryTransport(
        [
            _response(
                200,
                {
                    "model": "actual-model",
                    "choices": [
                        {"message": {"content": "provider answer"}, "finish_reason": "stop"}
                    ],
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 3,
                        "total_tokens": 13,
                    },
                },
                **{"x-request-id": "provider-request-1"},
            )
        ]
    )
    adapter = _adapter(transport)

    response = adapter.generate(_request())

    sent = transport.requests[0]
    assert sent.url == "https://provider.invalid/v1/chat/completions"
    assert sent.headers["authorization"] == "Bearer test-secret-key"
    assert sent.json_body == {
        "model": "requested-model",
        "messages": [
            {"role": "system", "content": "Use only context."},
            {
                "role": "user",
                "content": (
                    "Question:\nWhat is the policy?\n\nContext:\n"
                    "[1]\nOnly this safe context is visible."
                ),
            },
        ],
        "temperature": 0.2,
        "top_p": 0.9,
        "max_tokens": 123,
        "stop": ["END"],
        "seed": 7,
    }
    assert response.answer == "provider answer"
    assert response.actual_model == "actual-model"
    assert response.finish_reason == "stop"
    assert response.usage is not None and response.usage.total_tokens == 13
    assert response.provider_request_id == "provider-request-1"
    assert response.is_mock is True
    assert len(adapter.last_attempts) == 1


def test_executor_projects_only_question_context_prompt_and_generation() -> None:
    sentinel = "DO-NOT-LEAK-LABEL-SENTINEL"
    transport = MemoryTransport(
        [
            _response(
                200,
                {"choices": [{"message": {"content": "safe answer"}}]},
            )
        ]
    )
    adapter = _adapter(transport)
    executor = ModelEvaluationExecutor(
        adapter,
        {
            "adapter_id": "openai_compatible",
            "provider_id": "openai_compatible",
            "prompt": {"version": "v2", "text": "Use only visible inputs."},
            "generation": GenerationConfig(model="test-model").model_dump(mode="json"),
            "context_policy": "dataset_contexts",
            "metric_config": [],
        },
    )
    sample = DatasetSample(
        external_id=f"sample-{sentinel}",
        question="Safe question",
        reference_answer=sentinel,
        gold_document_ids=[sentinel],
        gold_evidence_ids=[sentinel],
        retrieved_contexts=[
            {
                "origin": "provided",
                "rank": 1,
                "doc_id": sentinel,
                "chunk_id": sentinel,
                "evidence_ids": [sentinel],
                "text": "Safe model context",
                "relevance_grade": 3,
                "supports_claim": sentinel,
            }
        ],
        answer=sentinel,
        historical_answer=sentinel,
        citations=[],
        historical_citations=[],
        tags=[sentinel],
        expected_diagnoses=[sentinel],
        metadata_json={sentinel: sentinel},
        content_sha256="0" * 64,
    )

    generated = executor.generate(sample)

    serialized_payload = json.dumps(transport.requests[0].json_body)
    assert sentinel not in serialized_payload
    assert generated.response.answer == "safe answer"


@pytest.mark.parametrize("status_code", [401, 403])
def test_authentication_errors_are_not_retried_or_leaked(status_code: int) -> None:
    transport = MemoryTransport(
        [
            ModelTransportResponse(
                status_code=status_code,
                headers={},
                body=b'{"secret":"raw-provider-body"}',
            )
        ]
    )
    adapter = _adapter(transport)

    with pytest.raises(ModelError) as caught:
        adapter.generate(_request())

    assert caught.value.code == ModelErrorCode.authentication_failed
    assert caught.value.attempts == 1
    assert len(transport.requests) == 1
    assert "raw-provider-body" not in caught.value.message
    assert "test-secret-key" not in caught.value.message


def test_rate_limit_and_server_error_retry_with_a_hard_attempt_cap() -> None:
    transport = MemoryTransport(
        [
            ModelTransportResponse(
                status_code=429,
                headers={"retry-after": "999"},
                body=b"limited",
            ),
            ModelTransportResponse(status_code=503, headers={}, body=b"provider secret"),
            _response(200, {"choices": [{"message": {"content": "eventual answer"}}]}),
        ]
    )
    adapter = _adapter(transport, model_total_timeout_ms=60_000)

    response = adapter.generate(_request())

    assert response.answer == "eventual answer"
    assert len(transport.requests) == 3
    assert [item.retry_delay_ms for item in adapter.last_attempts] == [5_000, 0, 0]


@pytest.mark.parametrize(
    ("scripted", "expected"),
    [
        ([TimeoutError(), TimeoutError(), TimeoutError()], ModelErrorCode.timeout),
        ([ConnectionError(), ConnectionError(), ConnectionError()], ModelErrorCode.transport_error),
        ([ModelTransportResponse(status_code=200, headers={}, body=b"")], ModelErrorCode.response_invalid),
        ([ModelTransportResponse(status_code=200, headers={}, body=b"not json")], ModelErrorCode.response_invalid),
        ([ModelTransportResponse(status_code=200, headers={}, body=b"\xff")], ModelErrorCode.response_invalid),
        ([_response(200, {"choices": []})], ModelErrorCode.response_invalid),
        ([_response(200, {"choices": [{"message": {"content": ""}}]})], ModelErrorCode.response_invalid),
    ],
)
def test_transport_and_response_failures_have_stable_errors(scripted, expected) -> None:
    transport = MemoryTransport(scripted)
    adapter = _adapter(transport)

    with pytest.raises(ModelError) as caught:
        adapter.generate(_request())

    assert caught.value.code == expected
    assert caught.value.attempts == len(transport.requests)
    assert len(transport.requests) <= 3


def test_disabled_real_network_rejects_before_transport() -> None:
    transport = MemoryTransport([_response(200, {})])
    adapter = OpenAICompatibleAdapter(
        _config(),
        _settings(model_external_calls_enabled=False),
        transport=transport,
        transport_is_mock=False,
    )

    with pytest.raises(ModelError) as caught:
        adapter.generate(_request())

    assert caught.value.code == ModelErrorCode.external_calls_disabled
    assert caught.value.attempts == 0
    assert transport.requests == []


def test_position_citation_resolves_without_claiming_semantic_support() -> None:
    citations = _parse_citations("A supported-looking answer [1] [99]", [
        {"rank": 1, "chunk_id": "private-chunk-id", "text": "Synthetic context"},
    ])
    assert citations[0]["target_id"] == "private-chunk-id"
    assert citations[0]["resolved"] is True
    assert citations[0]["supports_claim"] is None
    assert citations[1]["resolved"] is False


def test_malformed_optional_finish_reason_does_not_crash_execution() -> None:
    adapter = _adapter(MemoryTransport([
        _response(200, {"choices": [{"message": {"content": "answer"}, "finish_reason": []}]}),
    ]))
    assert adapter.generate(_request()).finish_reason is None


def test_nonfinite_retry_after_uses_bounded_retry_policy() -> None:
    adapter = _adapter(MemoryTransport([
        _response(429, {}, **{"retry-after": "Infinity"}),
        _response(200, {"choices": [{"message": {"content": "answer"}}]}),
    ]))
    assert adapter.generate(_request()).answer == "answer"
    assert len(adapter.last_attempts) == 2
    assert adapter.last_attempts[0].retry_delay_ms == 0


def test_production_transport_cancels_whole_attempt_offline(monkeypatch) -> None:
    cancelled = []

    class SlowClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, *args, **kwargs):
            try:
                await asyncio.sleep(60)
            finally:
                cancelled.append(True)

    monkeypatch.setattr(httpx, "AsyncClient", SlowClient)
    with pytest.raises(TimeoutError):
        HttpxModelTransport().send(ModelTransportRequest(
            url="https://provider.invalid", headers={}, json_body={}, timeout_ms=20,
        ))
    assert cancelled == [True]
