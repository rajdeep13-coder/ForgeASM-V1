from __future__ import annotations

import pytest

from api.simulation_manager import simulation_manager
from core.assembler.assembler import Assembler
from core.assembler.exceptions import AssemblerError, AssemblerErrorKind
from core.isa.isa_def import ISA
from core.runtime import run_program
from core.simulator.exceptions import SimulationError


@pytest.mark.parametrize("isa_name, opcode", [
    ("risc1", "111111"),
    ("risc2", "11111111"),
    ("risc3", "111111"),
    ("cisc", "11111111"),
])
def test_strict_unknown_opcode_reports_context(isa_name, opcode):
    sim = simulation_manager.create(isa_name, "neumann", opcode, strict=True)
    try:
        with pytest.raises(SimulationError) as raised:
            sim.step()
        error = raised.value
        assert error.kind == "unknown_opcode"
        assert error.cycle == 0
        assert error.pc == 0
        assert error.opcode == opcode
    finally:
        simulation_manager.delete(sim.simulation_id)


def test_strict_unimplemented_cisc_opcode_reports_context():
    binary = "00001011"
    sim = simulation_manager.create("cisc", "neumann", binary, strict=True)
    try:
        with pytest.raises(SimulationError) as raised:
            sim.step()
        assert raised.value.kind == "unimplemented_opcode"
        assert raised.value.opcode == binary.splitlines()[0]
    finally:
        simulation_manager.delete(sim.simulation_id)


def test_non_strict_unknown_opcode_preserves_halt_compatibility():
    sim = simulation_manager.create("risc3", "neumann", "111111", strict=False)
    try:
        sim.step()
        assert sim.cpu.halted is True
    finally:
        simulation_manager.delete(sim.simulation_id)


def test_assembler_error_has_structured_fields_and_old_message():
    with pytest.raises(AssemblerError) as raised:
        Assembler(ISA("risc3")).assemble("mov R99, 15")
    error = raised.value
    assert error.kind is AssemblerErrorKind.BAD_OPERAND
    assert error.line_number == 1
    assert error.token == "R99"
    assert error.as_dict()["message"] == "Invalid register: R99"
    assert "Line 1:" in str(error)
    assert "Invalid register: R99" in str(error)


def test_run_program_returns_timeout_and_trace():
    result = run_program("risc3", "neumann", ".loop\njmp .loop", max_cycles=2, trace=True)
    assert result["assembled"]
    assert result["timed_out"] is True
    assert result["halted"] is False
    assert result["cycles"] == 2
    assert len(result["trace"]) == 2


def test_run_program_returns_strict_error():
    result = run_program("cisc", "neumann", "load4 R00", max_cycles=3)
    assert result["errors"][0]["kind"] == "unimplemented_opcode"
    assert result["halted"] is False
