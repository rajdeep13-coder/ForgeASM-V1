"""
Pydantic models for the ForgeASM Simulation REST API.

All request/response schemas live here so the route layer stays thin
and the core simulator knows nothing about HTTP.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ─── Request Models ───────────────────────────────────────────────────────────

class SimulationCreateRequest(BaseModel):
    """Create and initialise a new simulation session."""
    isa: str = Field(
        ...,
        description="ISA to use: 'risc1', 'risc2', 'risc3', or 'cisc'",
        examples=["risc3"],
    )
    memory_architecture: str = Field(
        default="neumann",
        description="Memory architecture: 'neumann' (Von Neumann) or 'harvard'",
        examples=["neumann"],
    )
    binary: str = Field(
        ...,
        description="Assembled binary output from POST /api/assemble (newline-separated bit strings)",
        examples=["0110000000001111\n0000000000000000"],
    )
    program_start: int = Field(
        default=0,
        ge=0,
        description="Byte address in memory where the program begins",
        examples=[0],
    )


class SimulationRunRequest(BaseModel):
    """Parameters for a bulk-run request."""
    max_cycles: int = Field(
        default=1000,
        ge=1,
        le=1_000_000,
        description="Maximum number of instructions to execute before stopping",
        examples=[1000],
    )


# ─── State snapshot (reused in all responses) ─────────────────────────────────

class FlagsSnapshot(BaseModel):
    Z: bool
    C: bool
    O: bool
    N: bool


class SimulationState(BaseModel):
    """Complete snapshot of the CPU state at a given moment."""
    pc: int = Field(..., description="Current program counter (instruction index)")
    registers: Dict[str, int] = Field(..., description="All register values keyed by name")
    flags: Dict[str, bool] = Field(..., description="Processor flags keyed by flag name")
    memory: List[int] = Field(..., description="First 512 bytes of data memory as integer list")
    halted: bool = Field(..., description="True when the CPU has executed a HALT or exceeded cycles")
    output: str = Field(default="", description="Captured I/O output text")
    cycle_count: int = Field(default=0, description="Total instructions executed so far")
    current_instruction: Optional[str] = Field(
        default=None,
        description="Name of the instruction at the current PC (what will execute on next step)",
    )


# ─── Response Models ──────────────────────────────────────────────────────────

class SimulationCreateResponse(BaseModel):
    """Returned when a simulation session is successfully created."""
    simulation_id: str = Field(..., description="Unique ID for this simulation session")
    isa: str
    memory_architecture: str
    state: SimulationState


class SimulationStateResponse(BaseModel):
    """Current state of an existing simulation."""
    simulation_id: str
    isa: str
    memory_architecture: str
    state: SimulationState


class SimulationStepResponse(BaseModel):
    """Result of executing a single instruction."""
    simulation_id: str
    state: SimulationState
    last_instruction: Optional[str] = Field(
        default=None,
        description="Human-readable name of the instruction that was just executed",
    )


class SimulationRunResponse(BaseModel):
    """Result of a bulk run (may execute many instructions)."""
    simulation_id: str
    state: SimulationState
    cycles_executed: int = Field(..., description="Number of instructions executed during this run")
    halt_reason: str = Field(
        ...,
        description="Why execution stopped: 'halted', 'max_cycles', or 'already_halted'",
    )


class SimulationResetResponse(BaseModel):
    """Result of resetting a simulation to its initial loaded state."""
    simulation_id: str
    state: SimulationState


# ─── Error model ──────────────────────────────────────────────────────────────

class APIError(BaseModel):
    """Structured error returned by all endpoints on failure."""
    error: str = Field(..., description="Human-readable error message")
    code: str = Field(..., description="Machine-readable error code")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"error": "Simulation not found", "code": "SIMULATION_NOT_FOUND"},
            ]
        }
    }


# ─── Existing endpoint models (kept for /api/assemble) ────────────────────────

class AssembleRequest(BaseModel):
    code: str = Field(..., description="Raw assembly source code")
    isa: str = Field(..., description="Target ISA")


class AssembleResponse(BaseModel):
    binary: str = Field(default="", description="Newline-separated binary bit strings")
    error: Optional[str] = Field(default=None, description="Error message if assembly failed")
    success: bool
