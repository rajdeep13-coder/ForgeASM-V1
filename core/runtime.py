"""Deterministic in-process program runner for agents and evaluation."""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from api.simulation_manager import Simulation
from core.assembler.assembler import Assembler
from core.assembler.exceptions import AssemblerError
from core.isa.isa_def import ISA
from core.simulator.exceptions import SimulationError


def _snapshot(simulation: Simulation) -> Dict[str, Any]:
    state = simulation.get_state()
    return {
        "pc": state.pc,
        "registers": dict(state.registers),
        "flags": dict(state.flags),
        "halted": state.halted,
        "output": state.output,
    }


def _diff(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    changed: Dict[str, Any] = {}
    for field in ("pc", "halted", "output"):
        if before[field] != after[field]:
            changed[field] = after[field]
    for field in ("registers", "flags"):
        values = {
            key: value for key, value in after[field].items()
            if before[field].get(key) != value
        }
        if values:
            changed[field] = values
    return changed


def _memory_dump(simulation: Simulation, ranges: Iterable[Tuple[int, int]]) -> Dict[str, List[int]]:
    result: Dict[str, List[int]] = {}
    for start, end in ranges:
        if start < 0 or end < start:
            raise ValueError("memory ranges must satisfy 0 <= start <= end")
        values = [
            simulation.cpu.memory.read_data(address, 1)
            for address in range(start, end)
        ]
        result[f"{start}:{end}"] = values
    return result


def run_program(
    isa: str,
    memory_arch: str,
    source: str,
    init: Optional[Dict[str, Any]] = None,
    max_cycles: int = 10_000,
    strict: bool = True,
    memory_ranges: Optional[Iterable[Tuple[int, int]]] = None,
    trace: bool = False,
    trace_cap: int = 1_000,
) -> Dict[str, Any]:
    """Assemble and execute source without HTTP or a persistent session.

    ``init`` may contain ``registers`` and a mapping of byte ``memory`` addresses
    to values. ``memory_ranges`` uses half-open ``(start, end)`` byte ranges.
    Trace entries contain only state fields that changed after each step.
    """
    if max_cycles < 1:
        raise ValueError("max_cycles must be positive")
    if trace_cap < 0:
        raise ValueError("trace_cap must not be negative")

    errors: List[Dict[str, Any]] = []
    try:
        isa_definition = ISA(isa.lower())
        assembled = Assembler(isa_definition).assemble(source)
    except AssemblerError as exc:
        errors.append(exc.as_dict())
        return {
            "assembled": "",
            "errors": errors,
            "halted": False,
            "timed_out": False,
            "cycles": 0,
            "registers": {},
            "flags": {},
            "memory_dump": {},
            "trace": [],
        }
    except Exception as exc:
        errors.append({"kind": "setup_error", "message": str(exc)})
        return {
            "assembled": "",
            "errors": errors,
            "halted": False,
            "timed_out": False,
            "cycles": 0,
            "registers": {},
            "flags": {},
            "memory_dump": {},
            "trace": [],
        }

    simulation = Simulation(
        simulation_id="in-process",
        isa_name=isa_definition.name,
        memory_architecture=memory_arch,
        binary=assembled,
        program_start=0,
        strict=strict,
    )
    initial = init or {}
    for name, value in dict(initial.get("registers", {})).items():
        if name.upper() not in simulation.cpu.registers:
            raise ValueError(f"Unknown initial register: {name}")
        simulation.cpu.registers[name.upper()] = int(value) & 0xFFFF
    for address, value in dict(initial.get("memory", {})).items():
        simulation.cpu.memory.write_data(int(address), int(value), 1)

    trace_entries: List[Dict[str, Any]] = []
    cycles = 0
    while not simulation.cpu.halted and cycles < max_cycles:
        before = _snapshot(simulation) if trace and len(trace_entries) < trace_cap else None
        try:
            simulation.step()
        except SimulationError as exc:
            errors.append(exc.as_dict())
            break
        cycles += 1
        if before is not None:
            after = _snapshot(simulation)
            trace_entries.append({"cycle": cycles - 1, "diff": _diff(before, after)})

    return {
        "assembled": assembled,
        "errors": errors,
        "halted": simulation.cpu.halted,
        "timed_out": not simulation.cpu.halted and cycles >= max_cycles and not errors,
        "cycles": cycles,
        "registers": dict(simulation.cpu.registers),
        "flags": {
            flag: simulation.cpu.get_flag(flag)
            for flag in ("Z", "C", "O", "N")
        },
        "memory_dump": _memory_dump(simulation, memory_ranges or []),
        "trace": trace_entries if trace else None,
    }
