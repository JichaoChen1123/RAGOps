from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request

from app.api.dependencies import get_runtime_settings
from app.core.config import Settings
from app.core.errors import DomainError
from app.execution.adapters import (
    CodexChatGPTAdapter,
    DefaultModelAdapterFactory,
    MockModelAdapter,
    OpenAICompatibleAdapter,
)
from app.execution.model import GenerationConfig, ModelError, ModelErrorCode, ModelRequest
from app.schemas.jobs import (
    ModelExecutionStatusResponse,
    ModelExecutionVerificationResponse,
    ModelGenerationVerificationRequest,
)

router = APIRouter()
SettingsDep = Annotated[Settings, Depends(get_runtime_settings)]


@router.get(
    "/status",
    response_model=ModelExecutionStatusResponse,
    summary="Read local model execution state without probing providers",
)
def get_model_execution_status(
    request: Request,
    settings: SettingsDep,
) -> ModelExecutionStatusResponse:
    adapter_id = settings.model_execution_adapter
    capabilities = {
        "mock": MockModelAdapter.capabilities,
        "codex_chatgpt": CodexChatGPTAdapter.capabilities,
        "openai_compatible": OpenAICompatibleAdapter.capabilities,
    }[adapter_id]
    configured = {
        "mock": True,
        "codex_chatgpt": settings.codex_configuration_complete,
        "openai_compatible": settings.openai_configuration_complete,
    }[adapter_id]
    cache = _verification_cache(request)
    return ModelExecutionStatusResponse(
        backend_execution_adapter=adapter_id,
        external_calls_enabled=settings.model_external_calls_enabled,
        execution_available=(
            adapter_id == "mock"
            or (configured and settings.model_external_calls_enabled)
        ),
        active_adapter={
            "adapter_id": adapter_id,
            "is_mock": adapter_id == "mock",
            "capabilities": capabilities.model_dump(mode="json"),
        },
        providers=[
            _openai_provider_state(settings, cache.get("openai_compatible", {})),
            _codex_provider_state(settings, cache.get("codex_chatgpt", {})),
        ],
    )


@router.post(
    "/providers/codex_chatgpt/verify-login",
    response_model=ModelExecutionVerificationResponse,
    summary="Explicitly check the Codex bridge and ChatGPT login without generating",
)
def verify_codex_login(
    request: Request,
    settings: SettingsDep,
) -> ModelExecutionVerificationResponse:
    verified_at = datetime.now(UTC)
    try:
        adapter = _adapter_factory(request, settings).create("codex_chatgpt")
        if not isinstance(adapter, CodexChatGPTAdapter):
            raise ModelError(
                ModelErrorCode.response_invalid,
                "The model provider returned an invalid response.",
                retryable=False,
            )
        bridge_status = adapter.read_status()
    except ModelError as exc:
        _record_verification_failure(
            request,
            "codex_chatgpt",
            "login",
            verified_at,
            exc,
        )
        raise _domain_error(exc) from None

    record = _verification_cache(request).setdefault("codex_chatgpt", {})
    record.update(
        {
            "login_status": bridge_status.login_status,
            "last_login_checked_at": verified_at,
            "login_verification_message": "Codex bridge status check completed.",
            "codex_version": bridge_status.codex_version,
            "available_models": bridge_status.available_models,
            "rate_limits": (
                bridge_status.rate_limits.model_dump(mode="json")
                if bridge_status.rate_limits
                else None
            ),
        }
    )
    return ModelExecutionVerificationResponse(
        provider_id="codex_chatgpt",
        verification_type="login",
        verified_at=verified_at,
        login_status=bridge_status.login_status,
        generation_verified=record.get("generation_verified", False),
        codex_version=bridge_status.codex_version,
        available_models=bridge_status.available_models,
        rate_limits=record["rate_limits"],
        requested_model=None,
        actual_model=None,
        usage=None,
        cost=None,
        provider_request_id=None,
        message="Codex bridge status check completed.",
    )


@router.post(
    "/providers/{provider_id}/verify-generation",
    response_model=ModelExecutionVerificationResponse,
    summary="Explicitly run one minimal real generation that may consume quota",
)
def verify_model_generation(
    provider_id: str,
    payload: ModelGenerationVerificationRequest,
    request: Request,
    settings: SettingsDep,
) -> ModelExecutionVerificationResponse:
    if provider_id not in {"codex_chatgpt", "openai_compatible"}:
        raise DomainError(
            ModelErrorCode.adapter_not_found.value,
            "The requested model execution adapter is not available.",
            status_code=422,
        )
    default_model = (
        settings.codex_default_model
        if provider_id == "codex_chatgpt"
        else settings.openai_compat_default_model
    )
    model = payload.model or default_model
    if model is None:
        raise DomainError(
            ModelErrorCode.not_configured.value,
            "A model must be supplied for generation verification.",
            status_code=409,
        )

    verified_at = datetime.now(UTC)
    try:
        adapter = _adapter_factory(request, settings).create(provider_id)
        response = adapter.generate(
            ModelRequest(
                question="Reply with exactly OK.",
                context=[],
                prompt="This is a user-requested connection check. Reply with exactly OK.",
                generation=GenerationConfig(model=model),
            )
        )
    except ModelError as exc:
        _record_verification_failure(
            request,
            provider_id,
            "generation",
            verified_at,
            exc,
        )
        raise _domain_error(exc) from None

    usage = response.usage.model_dump(mode="json") if response.usage else None
    record = _verification_cache(request).setdefault(provider_id, {})
    record.update(
        {
            "generation_verified": True,
            "last_generation_verified_at": verified_at,
            "generation_verification_message": "Minimal generation completed.",
            "actual_model": response.actual_model,
            "usage": usage,
        }
    )
    return ModelExecutionVerificationResponse(
        provider_id=provider_id,
        verification_type="generation",
        verified_at=verified_at,
        login_status=(record.get("login_status") if provider_id == "codex_chatgpt" else None),
        generation_verified=True,
        codex_version=record.get("codex_version"),
        available_models=record.get("available_models"),
        rate_limits=record.get("rate_limits"),
        requested_model=model,
        actual_model=response.actual_model,
        usage=usage,
        cost=None,
        provider_request_id=response.provider_request_id,
        message="Minimal generation completed.",
    )


def _adapter_factory(request: Request, settings: Settings) -> Any:
    return getattr(
        request.app.state,
        "model_adapter_factory",
        DefaultModelAdapterFactory(settings),
    )


def _verification_cache(request: Request) -> dict[str, dict[str, Any]]:
    cache = getattr(request.app.state, "model_execution_verifications", None)
    if cache is None:
        cache = {}
        request.app.state.model_execution_verifications = cache
    return cache


def _openai_provider_state(settings: Settings, cached: dict[str, Any]) -> dict[str, Any]:
    configured = settings.openai_configuration_complete
    return {
        "provider_id": "openai_compatible",
        "configuration_status": "configured_unverified" if configured else "not_configured",
        "base_url_configured": settings.openai_compat_base_url is not None,
        "bridge_url_configured": None,
        "credential_configured": settings.openai_credential_configured,
        "default_model_configured": settings.openai_compat_default_model is not None,
        "login_status": None,
        "last_login_checked_at": None,
        "login_verification_message": None,
        "generation_verified": cached.get("generation_verified", False),
        "last_generation_verified_at": cached.get("last_generation_verified_at"),
        "generation_verification_message": cached.get("generation_verification_message"),
        "codex_version": None,
        "available_models": None,
        "rate_limits": None,
        "actual_model": cached.get("actual_model"),
        "usage": cached.get("usage"),
        "cost": None,
        "last_verified_at": cached.get("last_generation_verified_at"),
        "verification_message": cached.get("generation_verification_message"),
    }


def _codex_provider_state(settings: Settings, cached: dict[str, Any]) -> dict[str, Any]:
    configured = settings.codex_configuration_complete
    return {
        "provider_id": "codex_chatgpt",
        "configuration_status": "configured_unverified" if configured else "not_configured",
        "base_url_configured": None,
        "bridge_url_configured": settings.codex_bridge_base_url is not None,
        "credential_configured": settings.codex_bridge_credential_configured,
        "default_model_configured": settings.codex_default_model is not None,
        "login_status": cached.get("login_status", "unknown"),
        "last_login_checked_at": cached.get("last_login_checked_at"),
        "login_verification_message": cached.get("login_verification_message"),
        "generation_verified": cached.get("generation_verified", False),
        "last_generation_verified_at": cached.get("last_generation_verified_at"),
        "generation_verification_message": cached.get("generation_verification_message"),
        "codex_version": cached.get("codex_version"),
        "available_models": cached.get("available_models"),
        "rate_limits": cached.get("rate_limits"),
        "actual_model": cached.get("actual_model"),
        "usage": cached.get("usage"),
        "cost": None,
        "last_verified_at": cached.get("last_generation_verified_at"),
        "verification_message": cached.get("generation_verification_message"),
    }


def _record_verification_failure(
    request: Request,
    provider_id: str,
    verification_type: str,
    verified_at: datetime,
    error: ModelError,
) -> None:
    record = _verification_cache(request).setdefault(provider_id, {})
    if verification_type == "login":
        record.update(
            {
                "last_login_checked_at": verified_at,
                "login_verification_message": error.message,
            }
        )
    else:
        record.update(
            {
                "generation_verified": False,
                "last_generation_verified_at": verified_at,
                "generation_verification_message": error.message,
                "actual_model": None,
                "usage": None,
            }
        )


def _domain_error(error: ModelError) -> DomainError:
    status_by_code = {
        ModelErrorCode.adapter_not_found: 422,
        ModelErrorCode.capability_unsupported: 422,
        ModelErrorCode.not_configured: 409,
        ModelErrorCode.external_calls_disabled: 403,
        ModelErrorCode.not_logged_in: 409,
        ModelErrorCode.quota_exceeded: 429,
        ModelErrorCode.rate_limited: 429,
        ModelErrorCode.timeout: 504,
        ModelErrorCode.cancelled: 499,
    }
    return DomainError(
        error.code.value,
        error.message,
        status_code=status_by_code.get(error.code, 502),
        details={
            "attempts": error.attempts,
            "provider_request_id": error.provider_request_id,
            "retry_after_ms": error.retry_after_ms,
        },
        retryable=error.retryable,
    )
