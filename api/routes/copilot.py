"""Gemma Copilot and ModelGateway routes."""
from __future__ import annotations

from contextlib import suppress
import json
from pathlib import Path

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from api.copilot.agent import run_agent
from api.copilot.provider import ProviderConfigurationError, ProviderRequestError
from api.copilot.tasks import TaskError, load_task
from api.models import (
    APIError, CopilotRunRequest, CopilotRunResponse,
    CopilotTranslateRequest, CopilotTranslateResponse,
    CopilotMultimodalRequest, CopilotMultimodalResponse,
)
from copilot.gateway import (
    GatewayConfigurationError,
    ModelGateway,
    ModelUnavailable,
)
from copilot.translation import TranslationAgent, TranslationSpec, TranslationVector
from copilot.multimodal import solve_confirmed_spec, transcribe_image

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


@router.get("/telemetry/export", summary="Export benchmark telemetry JSON")
async def copilot_telemetry_export(request: Request) -> JSONResponse:
    try:
        session_id = request.headers.get("X-Session-ID")
        return JSONResponse(content=gateway().benchmark_export(session_id))
    except ModelUnavailable as exc:
        return JSONResponse(content={"records": [], "error": str(exc)})


@router.get("/episodes", summary="Return cached Copilot episodes for the logbook")
async def copilot_episodes() -> JSONResponse:
    episode_dir = Path(__file__).resolve().parents[2] / "logs" / "copilot_episodes"
    episodes = []
    if episode_dir.is_dir():
        for path in sorted(episode_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
            try:
                episodes.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
    return JSONResponse(content={"episodes": episodes[:100]})


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


@router.post(
    "/translate",
    response_model=CopilotTranslateResponse,
    summary="Translate assembly and verify ISA-neutral observables",
)
async def translate_copilot(req: CopilotTranslateRequest, request: Request) -> JSONResponse:
    try:
        source_isa = req.source_isa.lower()
        target_isa = req.target_isa.lower()
        model_gateway = gateway()
        model_gateway.set_session_id(request.headers.get("X-Session-ID", "default"))
        spec = TranslationSpec(
            source_isa=source_isa,
            target_isa=target_isa,
            source=req.source,
            vectors=[TranslationVector("default")],
            observe_output=True,
        )
        result = TranslationAgent(model_gateway).translate(spec, req.max_repairs)
    except (ValueError, GatewayConfigurationError) as exc:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=APIError(error=str(exc), code="INVALID_TRANSLATION").model_dump(),
        )
    except (ProviderRequestError, ModelUnavailable) as exc:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=APIError(error=str(exc), code="COPILOT_PROVIDER_ERROR").model_dump(),
        )
    return CopilotTranslateResponse(
        episode_id=result["episode_id"],
        verdict=result["verdict"],
        translation=result.get("translation"),
        results=result["results"],
    )


@router.get("/translation-episodes", summary="Return cached translation episodes")
async def translation_episodes() -> JSONResponse:
    episode_dir = Path(__file__).resolve().parents[2] / "logs" / "copilot_translation"
    episodes = []
    if episode_dir.is_dir():
        for path in sorted(episode_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
            try:
                episodes.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
    return JSONResponse(content={"episodes": episodes[:100]})


@router.post(
    "/multimodal",
    response_model=CopilotMultimodalResponse,
    summary="Transcribe a user image, or solve its user-confirmed specification",
)
async def copilot_multimodal(req: CopilotMultimodalRequest, request: Request) -> JSONResponse:
    try:
        model_gateway = gateway()
        model_gateway.set_session_id(request.headers.get("X-Session-ID", "default"))
        if req.confirmed_spec is not None:
            result = solve_confirmed_spec(
                model_gateway, req.isa.lower(), req.confirmed_spec, req.max_repairs,
            )
            return CopilotMultimodalResponse(
                stage="solved", result=result,
                checker_basis="user_confirmed_spec",
            )
        if not req.image_data_url:
            raise ValueError("image_data_url is required before confirmation")
        transcription = transcribe_image(model_gateway, req.image_data_url)
        return CopilotMultimodalResponse(
            stage="confirm", spec=transcription["spec"], model=transcription["model"],
        )
    except RuntimeError as exc:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=APIError(error=str(exc), code="IMAGE_INPUT_UNAVAILABLE").model_dump(),
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=APIError(error=str(exc), code="INVALID_MULTIMODAL_INPUT").model_dump(),
        )
    except GatewayConfigurationError as exc:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=APIError(error=str(exc), code="COPILOT_NOT_CONFIGURED").model_dump(),
        )
    except (ProviderRequestError, ModelUnavailable) as exc:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=APIError(error=str(exc), code="COPILOT_PROVIDER_ERROR").model_dump(),
        )
