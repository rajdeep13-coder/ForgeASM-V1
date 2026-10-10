"""Constrained Gemma agent loop for ForgeASM."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from api.copilot.provider import (
    ModelResponse,
    OpenAICompatibleProvider,
    ProviderConfigurationError,
    ToolCall,
)
from api.copilot.tasks import TaskSpec, check_state
from api.simulation_manager import simulation_manager
from core.assembler.assembler import Assembler
from core.isa.isa_def import ISA


TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "assemble_and_run",
        "description": "Assemble the supplied assembly and run it in the isolated ForgeASM simulator.",
        "parameters": {
            "type": "object",
            "properties": {
                "assembly": {"type": "string", "description": "Assembly source only."},
                "max_cycles": {"type": "integer", "minimum": 1, "maximum": 10000},
            },
            "required": ["assembly"],
            "additionalProperties": False,
        },
    },
}


def _isa_context(isa_name: str) -> Dict[str, Any]:
    isa = ISA(isa_name)
    return {
        "registers": [
            {"name": item.name, "encoding": item.encoding, "description": item.description}
            for item in isa.registers.values()
        ],
        "instructions": [
            {"opcode": opcode, "name": item.name, "operands": item.operands}
            for opcode, item in isa.instructions.items()
        ],
    }


def _execute_tool(task: TaskSpec, call: ToolCall) -> Dict[str, Any]:
    if call.name != "assemble_and_run":
        raise ValueError(f"Unsupported Copilot tool: {call.name}")
    assembly = call.arguments.get("assembly")
    if not isinstance(assembly, str) or not assembly.strip():
        raise ValueError("assemble_and_run requires non-empty assembly")
    if len(assembly) > 100_000:
        raise ValueError("Assembly exceeds the maximum allowed size")
    max_cycles = call.arguments.get("max_cycles", 1000)
    if not isinstance(max_cycles, int) or isinstance(max_cycles, bool) or not 1 <= max_cycles <= 10_000:
        raise ValueError("max_cycles must be an integer from 1 to 10000")

    isa = ISA(task.isa)
    binary = Assembler(isa).assemble(assembly)
    simulation = simulation_manager.create(
        isa_name=task.isa,
        memory_architecture=task.memory_architecture,
        binary=binary,
        program_start=0,
    )
    try:
        cycles, halt_reason = simulation.run(max_cycles=max_cycles)
        state = simulation.get_state().model_dump()
    finally:
        simulation_manager.delete(simulation.simulation_id)
    result = check_state(state, task.expected)
    return {
        "assembly": assembly,
        "state": state,
        "cycles_executed": cycles,
        "halt_reason": halt_reason,
        "checker": result,
    }


def run_agent(
    task: TaskSpec,
    provider: Optional[Any] = None,
    max_iterations: int = 4,
) -> Dict[str, Any]:
    if not 1 <= max_iterations <= 8:
        raise ValueError("max_iterations must be from 1 to 8")
    model = provider or OpenAICompatibleProvider()
    context = _isa_context(task.isa)
    messages: List[Dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "You are ForgeASM Copilot. Learn the supplied ISA in context. "
                "Output assembly, tool-call arguments, or a short explanation only. "
                "Never output Python, shell commands, or code outside the simulator. "
                "Use assemble_and_run to test your assembly and repair it when checker.passed is false."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Task: {task.description}\n"
                f"ISA metadata (read-only): {context}\n"
                "The deterministic checker is server-owned. Its public task criteria are the task description."
            ),
        },
    ]
    attempts: List[Dict[str, Any]] = []
    for iteration in range(max_iterations):
        response: ModelResponse = model.complete(messages, [TOOL_DEFINITION])
        if not response.tool_calls:
            return {
                "status": "explanation",
                "iterations": iteration + 1,
                "attempts": attempts,
                "explanation": response.content,
            }
        for call in response.tool_calls:
            result = _execute_tool(task, call)
            attempts.append(result)
            if result["checker"]["passed"]:
                return {
                    "status": "passed",
                    "iterations": iteration + 1,
                    "attempts": attempts,
                    "final": result,
                }
        messages.append({"role": "assistant", "tool_calls": [
            {"type": "function", "function": {"name": call.name, "arguments": json.dumps(call.arguments)}}
            for call in response.tool_calls
        ]})
        messages.append({"role": "user", "content": f"Tool results: {attempts[-1]}"})
    return {"status": "failed", "iterations": max_iterations, "attempts": attempts}


__all__ = ["ProviderConfigurationError", "run_agent"]
