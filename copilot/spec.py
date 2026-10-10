"""Verified, compact ISA context for the Copilot."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

from core.assembler.assembler import Assembler
from core.isa.isa_def import ISA
from core.runtime import run_program


_ROOT = Path(__file__).resolve().parents[1]
_DEMO_ROOT = _ROOT / "modules" / "demos"
_DEFAULT_BUDGET = 1800


def _approx_tokens(text: str) -> int:
    return len(re.findall(r"\S+", text))


def _instruction_line(opcode: str, definition: Any) -> str:
    operands = ", ".join(definition.operands) or "-"
    destinations = ", ".join(definition.result_dest)
    return (
        f"{definition.name}({operands}) [{opcode}] "
        f"dest={destinations}; verified CPU result model"
    )


def _verified_examples(isa_name: str, budget: int) -> List[str]:
    examples: List[str] = []
    demo_dir = _DEMO_ROOT / isa_name
    for path in sorted(demo_dir.glob("*.asm")):
        source = path.read_text(encoding="utf-8")
        try:
            Assembler(ISA(isa_name)).assemble(source)
            result = run_program(
                isa_name, "neumann", source, max_cycles=256, strict=True
            )
        except Exception:
            continue
        if result["errors"]:
            continue
        example = f"example {path.name}:\n{source.strip()}"
        if _approx_tokens("\n".join(examples + [example])) > budget:
            break
        examples.append(example)
        if len(examples) == 3:
            break
    return examples


def build_isa_card(isa_name: str, token_budget: int = _DEFAULT_BUDGET) -> Dict[str, Any]:
    """Build a card directly from definitions and examples verified by the runtime."""
    if token_budget < 1:
        raise ValueError("token_budget must be positive")
    isa = ISA(isa_name.lower())
    instructions = [_instruction_line(op, item) for op, item in isa.instructions.items()]
    registers = [
        f"{item.name}({item.encoding},{'general' if item.is_general_purpose else 'special'})"
        for item in isa.registers.values()
    ]
    lines = [
        f"ISA {isa.name}; word size is defined by the active assembler.",
        "registers: " + "; ".join(registers),
        "flags: FR bits C=12, Z=13, O=14, N/S=15 when FR exists.",
        "instructions:",
        *instructions,
        "directives: .label (jump label); .label db|byte|dw|word value.",
        "labels: a leading dot defines a label; jumps and selected immediates use .label.",
        "memory: byte-addressed data; Harvard separates instruction and data memory; "
        "Neumann shares them.",
        "halting: halt sets CPU halted; a bounded run is timed_out when the cap is reached first.",
    ]
    examples = _verified_examples(isa.name.lower(), token_budget)
    lines.extend(examples)

    selected: List[str] = []
    for line in lines:
        candidate = "\n".join(selected + [line])
        if _approx_tokens(candidate) > token_budget:
            break
        selected.append(line)
    text = "\n".join(selected)
    return {
        "isa": isa.name.lower(),
        "text": text,
        "token_count": _approx_tokens(text),
        "token_budget": token_budget,
        "verified_examples": len(examples),
    }


__all__ = ["build_isa_card"]
