"""
Simulation REST routes
======================
All endpoints that control the simulation lifecycle live here.

Dependency graph:
    HTTP request
        └── Route handler  (this file)
                └── SimulationManager / Simulation  (simulation_manager.py)
                        └── CPU / Memory / IO       (core/)

The routes are deliberately thin: they validate input, delegate to the
simulation layer, and format the response.  No simulation logic lives here.
"""
from __future__ import annotations

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from api.models import (
    SimulationCreateRequest,
    SimulationCreateResponse,
    SimulationRunRequest,
    SimulationRunResponse,
    SimulationResetResponse,
    SimulationStateResponse,
    SimulationStepResponse,
    APIError,
)
from api.simulation_manager import (
    simulation_manager,
    SimulationNotFoundError,
)
from core.isa.exceptions import InvalidISAError

router = APIRouter(prefix="/api/simulations", tags=["Simulation"])


# ─── Helper ───────────────────────────────────────────────────────────────────

def _not_found(simulation_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content=APIError(
            error=f"Simulation '{simulation_id}' not found",
            code="SIMULATION_NOT_FOUND",
        ).model_dump(),
    )


def _bad_request(message: str, code: str = "BAD_REQUEST") -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=APIError(error=message, code=code).model_dump(),
    )


# ─── POST /api/simulations ────────────────────────────────────────────────────

@router.post(
    "",
    response_model=SimulationCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create and initialise a new simulation session",
    responses={
        400: {"model": APIError, "description": "Invalid ISA or binary"},
        422: {"description": "Request validation error"},
    },
)
async def create_simulation(req: SimulationCreateRequest) -> JSONResponse:
    """
    Assemble a binary into a fresh CPU and return the initial machine state.

    A unique ``simulation_id`` is returned – include it in every subsequent
    request to address this specific simulation instance.
    """
    try:
        sim = simulation_manager.create(
            isa_name=req.isa,
            memory_architecture=req.memory_architecture,
            binary=req.binary,
            program_start=req.program_start,
        )
    except InvalidISAError as exc:
        return _bad_request(str(exc), "INVALID_ISA")
    except Exception as exc:
        return _bad_request(f"Failed to initialise simulation: {exc}", "INIT_ERROR")

    return SimulationCreateResponse(
        simulation_id=sim.simulation_id,
        isa=sim.isa_name,
        memory_architecture=sim.memory_architecture,
        state=sim.get_state(),
    )


# ─── GET /api/simulations/{simulation_id} ─────────────────────────────────────

@router.get(
    "/{simulation_id}",
    response_model=SimulationStateResponse,
    summary="Get the current state of a simulation",
    responses={404: {"model": APIError}},
)
async def get_simulation(simulation_id: str) -> JSONResponse:
    """
    Return the current CPU state without executing any instructions.

    Useful for reconnecting after a page refresh or for external tooling that
    inspects simulation state independently of the frontend.
    """
    try:
        sim = simulation_manager.get_or_404(simulation_id)
    except SimulationNotFoundError:
        return _not_found(simulation_id)

    return SimulationStateResponse(
        simulation_id=simulation_id,
        isa=sim.isa_name,
        memory_architecture=sim.memory_architecture,
        state=sim.get_state(),
    )


# ─── POST /api/simulations/{simulation_id}/step ───────────────────────────────

@router.post(
    "/{simulation_id}/step",
    response_model=SimulationStepResponse,
    summary="Execute exactly one instruction",
    responses={404: {"model": APIError}},
)
async def step_simulation(simulation_id: str) -> JSONResponse:
    """
    Fetch-decode-execute a single instruction and return the resulting CPU
    state.  If the CPU is already halted, the state is returned unchanged.
    """
    try:
        sim = simulation_manager.get_or_404(simulation_id)
    except SimulationNotFoundError:
        return _not_found(simulation_id)

    try:
        last_instruction = sim.step()
    except Exception as exc:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=APIError(error=f"Step failed: {exc}", code="STEP_ERROR").model_dump(),
        )

    return SimulationStepResponse(
        simulation_id=simulation_id,
        state=sim.get_state(),
        last_instruction=last_instruction,
    )


# ─── POST /api/simulations/{simulation_id}/run ────────────────────────────────

@router.post(
    "/{simulation_id}/run",
    response_model=SimulationRunResponse,
    summary="Run the simulation for up to max_cycles instructions",
    responses={404: {"model": APIError}},
)
async def run_simulation(simulation_id: str, req: SimulationRunRequest) -> JSONResponse:
    """
    Execute instructions in a tight loop until one of the following occurs:

    - The CPU executes a HALT instruction  → ``halt_reason: "halted"``
    - ``max_cycles`` instructions are reached → ``halt_reason: "max_cycles"``
    - The CPU was already halted             → ``halt_reason: "already_halted"``

    The entire run happens synchronously inside this request; there is no
    polling or streaming required.  This keeps the API simple while avoiding
    thousands of HTTP round-trips for a bulk execution.
    """
    try:
        sim = simulation_manager.get_or_404(simulation_id)
    except SimulationNotFoundError:
        return _not_found(simulation_id)

    try:
        cycles_executed, halt_reason = sim.run(max_cycles=req.max_cycles)
    except Exception as exc:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=APIError(error=f"Run failed: {exc}", code="RUN_ERROR").model_dump(),
        )

    return SimulationRunResponse(
        simulation_id=simulation_id,
        state=sim.get_state(),
        cycles_executed=cycles_executed,
        halt_reason=halt_reason,
    )


# ─── POST /api/simulations/{simulation_id}/reset ──────────────────────────────

@router.post(
    "/{simulation_id}/reset",
    response_model=SimulationResetResponse,
    summary="Reset the simulation to its initial loaded state",
    responses={404: {"model": APIError}},
)
async def reset_simulation(simulation_id: str) -> JSONResponse:
    """
    Rebuild the CPU from scratch, reload the original binary, and return the
    initial CPU state.  Register values, flags, memory, and output buffer are
    all cleared.
    """
    try:
        sim = simulation_manager.get_or_404(simulation_id)
    except SimulationNotFoundError:
        return _not_found(simulation_id)

    try:
        sim.reset()
    except Exception as exc:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=APIError(error=f"Reset failed: {exc}", code="RESET_ERROR").model_dump(),
        )

    return SimulationResetResponse(
        simulation_id=simulation_id,
        state=sim.get_state(),
    )


# ─── DELETE /api/simulations/{simulation_id} ──────────────────────────────────

@router.delete(
    "/{simulation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a simulation session",
    responses={404: {"model": APIError}},
)
async def delete_simulation(simulation_id: str) -> JSONResponse:
    """
    Remove the simulation from the in-memory store.

    The frontend should call this when the user closes a session or navigates
    away, to prevent unbounded memory growth.
    """
    deleted = simulation_manager.delete(simulation_id)
    if not deleted:
        return _not_found(simulation_id)
    return JSONResponse(status_code=status.HTTP_204_NO_CONTENT, content=None)
