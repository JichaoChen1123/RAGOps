from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_runtime_settings
from app.core.config import Settings
from app.execution.adapters import MockModelAdapter, OpenAICompatibleAdapter
from app.schemas.jobs import ModelExecutionStatusResponse

router = APIRouter()
SettingsDep = Annotated[Settings, Depends(get_runtime_settings)]


@router.get(
    "/status",
    response_model=ModelExecutionStatusResponse,
    summary="Read public model execution configuration without probing providers",
)
def get_model_execution_status(settings: SettingsDep) -> ModelExecutionStatusResponse:
    configured = settings.openai_configuration_complete
    adapter_id = settings.model_execution_adapter
    capabilities = (
        MockModelAdapter.capabilities
        if adapter_id == "mock"
        else OpenAICompatibleAdapter.capabilities
    )
    execution_available = adapter_id == "mock" or (
        configured and settings.model_external_calls_enabled
    )
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
            {
                "provider_id": "openai_compatible",
                "configuration_status": (
                    "configured_unverified" if configured else "not_configured"
                ),
                "base_url_configured": settings.openai_compat_base_url is not None,
                "credential_configured": settings.openai_credential_configured,
                "default_model_configured": settings.openai_compat_default_model is not None,
                "last_verified_at": None,
                "verification_message": None,
            }
        ],
    )
