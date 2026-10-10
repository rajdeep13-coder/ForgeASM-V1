"""Gemma Copilot and ModelGateway routes."""
from __future__ import annotations

from contextlib import suppress

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from api.copilot.agent import run_agent
from api.copilot.provider import ProviderConfigurationError, ProviderRequestError
from api.copilot.tasks import TaskError, load_task
from api.models import APIError, CopilotRunRequest, CopilotRunResponse
from copilot.gateway import (
    GatewayConfigurationError,
    ModelGateway,
    ModelUnavailable,
)

router = APIRouter(prefix="/api/copilot", tags=["Copilot"])
_gateway: ModelGateway | None = None


def initialize_gateway() -> ModelGateway:
    global _gateway
    try:
        _gateway = ModelGateway()
        _gateway.startup_check()
    except GatewayConfigurationError as exc:
        _gateway = None
        # Keep the simulator API available while exposing the actionable error
        # through the capabilities endpoint and Copilot run endpoint.
        setattr(initialize_gateway, "startup_error", str(exc))
    return _gateway


def gateway() -> ModelGateway:
    if _gateway is None:
        initialize_gateway()
    if _gateway is None:
        raise GatewayConfigurationError(
            getattr(initialize_gateway, "startup_error", "ModelGateway is unavailable")
        )
    return _gateway


@router.get("/capabilities", summary="Report configured model capabilities")
async def copilot_capabilities() -> JSONResponse:
    try:
        value = gateway().capabilities_snapshot()
    except ModelUnavailable as exc:
        value = {
            "available": False,
            "backend": "LOCAL",
            "error": str(exc),
            "supports_images": False,
            "supports_tool_calling": False,
            "supports_json_schema": False,
            "installed_models": [],
            "model_id": None,
        }
    return JSONResponse(content=value)


@router.get("/telemetry", summary="Return ModelGateway telemetry records")
async def copilot_telemetry() -> JSONResponse:
    try:
        return JSONResponse(content={"records": gateway().telemetry()})
    except ModelUnavailable as exc:
        return JSONResponse(content={"records": [], "error": str(exc)})


@router.post(
    "/run",
    response_model=CopilotRunResponse,
    summary="Run the local Gemma Copilot on a server-owned task",
    responses={400: {"model": APIError}, 503: {"model": APIError}},
)
async def run_copilot(req: CopilotRunRequest, request: Request) -> JSONResponse:
    try:
        task = load_task(req.task_id)
        model_gateway = gateway()
        model_gateway.set_session_id(request.headers.get("X-Session-ID", "default"))
        result = run_agent(task, provider=model_gateway, max_iterations=req.max_iterations)
    except TaskError as exc:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=APIError(error=str(exc), code="INVALID_COPILOT_TASK").model_dump(),
        )
    except (ProviderConfigurationError, GatewayConfigurationError) as exc:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=APIError(error=str(exc), code="COPILOT_NOT_CONFIGURED").model_dump(),
        )
    except (ProviderRequestError, ModelUnavailable) as exc:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=APIError(error=str(exc), code="COPILOT_PROVIDER_ERROR").model_dump(),
        )
    except Exception as exc:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=APIError(error=str(exc), code="COPILOT_RUN_ERROR").model_dump(),
        )
    return CopilotRunResponse(task_id=req.task_id, **result)
