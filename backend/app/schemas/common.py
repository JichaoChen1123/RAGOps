from typing import Any

from pydantic import BaseModel, ConfigDict


class ErrorPayload(BaseModel):
    code: str
    message: str
    details: dict[str, Any]
    request_id: str
    retryable: bool


class ErrorResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "error": {
                        "code": "RESOURCE_NOT_FOUND",
                        "message": "Evaluation job not found.",
                        "details": {"job_id": "01912345-6789-7abc-8def-0123456789ab"},
                        "request_id": "req_01912345-6789-7abc-8def-0123456789ab",
                        "retryable": False,
                    }
                }
            ]
        }
    )

    error: ErrorPayload
