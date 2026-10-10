"""Gemma Copilot route."""
from __future__ import annotations

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from api.copilot.agent import run_agent
from api.copilot.provider import ProviderConfigurationError, ProviderRequestError
from api.copilot.tasks import TaskError, load_task
from api.models import APIError, CopilotRunRequest, CopilotRunResponse

router = APIRouter(prefix="/api/copilot", tags=["Copilot"])


@router.post(
    "/run",
    response_model=CopilotRunResponse,
    summary="Run the local Gemma Copilot on a server-owned task",
    responses={400: {"model": APIError}, 503: {"model": APIError}},
)
async def run_copilot(req: CopilotRunRequest) -> JSONResponse:
    try:
        task = load_task(req.task_id)
        result = run_agent(task, max_iterations=req.max_iterations)
    except TaskError as exc:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=APIError(error=str(exc), code="INVALID_COPILOT_TASK").model_dump(),
        )
    except ProviderConfigurationError as exc:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=APIError(error=str(exc), code="COPILOT_NOT_CONFIGURED").model_dump(),
        )
    except ProviderRequestError as exc:
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
