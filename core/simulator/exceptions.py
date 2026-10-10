from __future__ import annotations

from typing import Any, Dict


class SimulationError(Exception):
    """Structured execution error raised by strict simulation."""

    def __init__(self, message: str, *, cycle: int, pc: int, opcode: str, kind: str):
        self.kind = kind
        self.cycle = cycle
        self.pc = pc
        self.opcode = opcode
        self.message = message
        super().__init__(message)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "cycle": self.cycle,
            "pc": self.pc,
            "opcode": self.opcode,
            "message": self.message,
        }
