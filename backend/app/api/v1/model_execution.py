from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request, status

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
    ProviderVerificationRequest,
    ProviderVerificationResponse,
)

router = APIRouter()
SettingsDep = Annotated[Settings, Depends(get_runtime_settings)]


@router.get(
    "/status",
    response_model=ModelExecutionStatusResponse,
    summary="Read public model execution configuration without probing providers",
)
def get_model_execution_status(
    request: Request, settings: SettingsDep
) -> ModelExecutionStatusResponse:
    adapter_id = settings.model_execution_adapter
    capabilities = _capabilities(adapter_id)
    configured = {
        "mock": True,
        "codex_chatgpt": settings.codex_configuration_complete,
        "openai_compatible": settings.openai_configuration_complete,
    }[adapter_id]
    execution_available = adapter_id == "mock" or bool(
        configured and settings.model_external_calls_enabled
    )
    verification = request.app.state.provider_verifications
    return ModelExecutionStatusResponse(
        backend_execution_adapter=adapter_id,
        external_calls_enabled=settings.model_external_calls_enabled,
        execution_available=execution_available,
        active_adapter={
            "adapter_id": adapter_id,
            "is_mock": adapter_id == "mock",
            "capabilities": capabilities.model_dump(mode="json"),
        },
        providers=[
            _provider_status(
                "openai_compatible",
                configured=settings.openai_configuration_complete,
                base_url_configured=settings.openai_compat_base_url is not None,
                credential_configured=settings.openai_credential_configured,
                default_model_configured=settings.openai_compat_default_model is not None,
                default_model=settings.openai_compat_default_model,
                verification=verification.get("openai_compatible"),
                provider_name=settings.openai_compat_provider_name,
                protocol="OpenAI Chat Completions",
            ),
            _provider_status(
                "codex_chatgpt",
                configured=settings.codex_configuration_complete,
                base_url_configured=settings.codex_bridge_url is not None,
                credential_configured=settings.codex_bridge_credential_configured,
                default_model_configured=settings.codex_default_model is not None,
                default_model=settings.codex_default_model,
                verification=verification.get("codex_chatgpt"),
                provider_name="Codex ChatGPT account",
                protocol="Codex App Server via authenticated host bridge",
            ),
        ],
    )


@router.post(
    "/providers/{provider_id}:verify",
    response_model=ProviderVerificationResponse,
    summary="Explicitly verify one configured model channel",
)
def verify_provider(
    provider_id: Literal["codex_chatgpt", "openai_compatible"],
    payload: ProviderVerificationRequest,
    request: Request,
    settings: SettingsDep,
) -> ProviderVerificationResponse:
    checked_at = datetime.now(UTC)
    if not settings.model_external_calls_enabled:
        raise DomainError(
            ModelErrorCode.external_calls_disabled.value,
            "External model calls are disabled by server policy.",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    try:
        adapter = DefaultModelAdapterFactory(settings).create(provider_id)
        if provider_id == "codex_chatgpt":
            assert isinstance(adapter, CodexChatGPTAdapter)
            inspected = adapter.inspect()
            authentication_status = str(inspected.get("authentication_status", "unknown"))
            if authentication_status == "not_authenticated":
                raise _model_error(ModelErrorCode.not_authenticated)
            if authentication_status == "wrong_auth_mode":
                raise _model_error(ModelErrorCode.wrong_auth_mode)
            if authentication_status != "authenticated":
                raise _model_error(ModelErrorCode.not_authenticated)
            models = _safe_models(inspected.get("models"))
            generation_verified = False
            if payload.perform_generation:
                model = payload.model or settings.codex_default_model or _default_model(models)
                if model is None:
                    raise _model_error(ModelErrorCode.not_configured)
                adapter.generate(_verification_request(model, adapter_id=provider_id))
                generation_verified = True
            result = ProviderVerificationResponse(
                provider_id=provider_id,
                configuration_status=(
                    "verified" if generation_verified else "configured_unverified"
                ),
                authentication_status=authentication_status,
                generation_verified=generation_verified,
                checked_at=checked_at,
                message=(
                    "Codex generation completed with ChatGPT authentication."
                    if generation_verified
                    else "ChatGPT authentication and the Codex model catalog are available; generation has not been tested."
                ),
                models=models,
                rate_limits=(
                    inspected.get("rate_limits")
                    if isinstance(inspected.get("rate_limits"), dict)
                    else None
                ),
                codex_version=(
                    inspected.get("codex_version")
                    if isinstance(inspected.get("codex_version"), str)
                    else None
                ),
                protocol_compatible=(
                    inspected.get("protocol_compatible")
                    if isinstance(inspected.get("protocol_compatible"), bool)
                    else None
                ),
                warning=(
                    "Account limits are unknown; no remaining allowance was inferred."
                    if inspected.get("rate_limits") is None
                    else None
                ),
            )
        else:
            if not payload.perform_generation:
                raise DomainError(
                    "GENERATION_CONFIRMATION_REQUIRED",
                    "OpenAI-compatible verification requires perform_generation=true and may incur provider charges.",
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            model = payload.model or settings.openai_compat_default_model
            if model is None:
                raise _model_error(ModelErrorCode.not_configured)
            response = adapter.generate(_verification_request(model, adapter_id=provider_id))
            result = ProviderVerificationResponse(
                provider_id=provider_id,
                configuration_status="verified",
                authentication_status="authenticated",
                generation_verified=True,
                checked_at=checked_at,
                message=(
                    "OpenAI-compatible Chat Completions request succeeded"
                    + (
                        f" with model {response.actual_model}."
                        if response.actual_model
                        else "; the provider did not report the actual model."
                    )
                ),
                warning="This explicit connection test may have incurred provider charges.",
            )
    except ModelError as exc:
        request.app.state.provider_verifications[provider_id] = {
            "verification_status": "failed",
            "authentication_status": _authentication_status(provider_id, exc.code),
            "generation_verified": False,
            "checked_at": checked_at.isoformat(),
            "message": exc.message,
            "error_code": exc.code.value,
            "reason_code": exc.reason_code,
            "diagnostic_id": exc.diagnostic_id,
        }
        raise _domain_error(exc) from None
    request.app.state.provider_verifications[provider_id] = result.model_dump(mode="json")
    return result


def _provider_status(
    provider_id: str,
    *,
    configured: bool,
    base_url_configured: bool,
    credential_configured: bool,
    default_model_configured: bool,
    default_model: str | None,
    verification: dict[str, Any] | None,
    provider_name: str,
    protocol: str,
) -> dict[str, Any]:
    verified = bool(verification and verification.get("generation_verified") is True)
    return {
        "provider_id": provider_id,
        "provider_name": provider_name,
        "protocol": protocol,
        "configuration_status": (
            "verified" if verified else "configured_unverified" if configured else "not_configured"
        ),
        "base_url_configured": base_url_configured,
        "credential_configured": credential_configured,
        "default_model_configured": default_model_configured,
        "default_model": default_model,
        "authentication_status": (
            verification.get("authentication_status") if verification else "unknown"
        ),
        "verification_status": (
            verification.get("verification_status") if verification else "not_run"
        ),
        "generation_verified": verified,
        "models": verification.get("models", []) if verification else [],
        "rate_limits": verification.get("rate_limits") if verification else None,
        "codex_version": verification.get("codex_version") if verification else None,
        "protocol_compatible": (verification.get("protocol_compatible") if verification else None),
        "last_verified_at": verification.get("checked_at") if verification else None,
        "verification_message": verification.get("message") if verification else None,
        "verification_error_code": verification.get("error_code") if verification else None,
        "verification_reason_code": verification.get("reason_code") if verification else None,
        "verification_diagnostic_id": (verification.get("diagnostic_id") if verification else None),
    }


def _capabilities(adapter_id: str):  # type: ignore[no-untyped-def]
    return {
        "mock": MockModelAdapter.capabilities,
        "codex_chatgpt": CodexChatGPTAdapter.capabilities,
        "openai_compatible": OpenAICompatibleAdapter.capabilities,
    }[adapter_id]


def _verification_request(model: str, *, adapter_id: str) -> ModelRequest:
    return ModelRequest(
        question="Reply with OK.",
        context=[],
        prompt="Return only a short confirmation.",
        generation=GenerationConfig(
            model=model,
            temperature=0.0,
            top_p=1.0,
            max_output_tokens=512 if adapter_id == "codex_chatgpt" else 1,
            reasoning_effort="low" if adapter_id == "codex_chatgpt" else None,
        ),
    )


def _safe_models(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)][:100]


def _default_model(models: list[dict[str, Any]]) -> str | None:
    for item in models:
        if item.get("is_default") is True and isinstance(item.get("id"), str):
            return item["id"]
    return None


def _model_error(code: ModelErrorCode) -> ModelError:
    messages = {
        ModelErrorCode.not_authenticated: "Codex is not signed in with a ChatGPT account.",
        ModelErrorCode.wrong_auth_mode: "Codex is signed in without ChatGPT authentication.",
        ModelErrorCode.not_configured: "The selected model provider is not configured.",
    }
    return ModelError(code, messages[code], retryable=False)


def _authentication_status(provider_id: str, code: ModelErrorCode) -> str:
    if code == ModelErrorCode.not_authenticated:
        return "not_authenticated"
    if code == ModelErrorCode.wrong_auth_mode:
        return "wrong_auth_mode"
    if code == ModelErrorCode.authentication_failed:
        return "login_expired" if provider_id == "codex_chatgpt" else "authentication_failed"
    if code == ModelErrorCode.usage_limited:
        return "usage_limited"
    return "unknown"


def _domain_error(error: ModelError) -> DomainError:
    status_by_code = {
        ModelErrorCode.not_configured: status.HTTP_409_CONFLICT,
        ModelErrorCode.external_calls_disabled: status.HTTP_403_FORBIDDEN,
        ModelErrorCode.not_authenticated: status.HTTP_409_CONFLICT,
        ModelErrorCode.wrong_auth_mode: status.HTTP_409_CONFLICT,
        ModelErrorCode.codex_not_installed: status.HTTP_503_SERVICE_UNAVAILABLE,
        ModelErrorCode.protocol_incompatible: status.HTTP_409_CONFLICT,
        ModelErrorCode.authentication_failed: status.HTTP_401_UNAUTHORIZED,
        ModelErrorCode.usage_limited: status.HTTP_429_TOO_MANY_REQUESTS,
        ModelErrorCode.rate_limited: status.HTTP_429_TOO_MANY_REQUESTS,
        ModelErrorCode.capability_unsupported: status.HTTP_422_UNPROCESSABLE_ENTITY,
        ModelErrorCode.isolation_violation: status.HTTP_409_CONFLICT,
        ModelErrorCode.timeout: status.HTTP_504_GATEWAY_TIMEOUT,
    }
    return DomainError(
        error.code.value,
        error.message,
        status_code=status_by_code.get(error.code, status.HTTP_502_BAD_GATEWAY),
        details={
            key: value
            for key, value in {
                "reason_code": error.reason_code,
                "diagnostic_id": error.diagnostic_id,
            }.items()
            if value is not None
        },
        retryable=error.retryable,
    )
