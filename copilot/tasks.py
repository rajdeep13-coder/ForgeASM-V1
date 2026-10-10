"""Task loading and immutable deterministic checking for Copilot episodes."""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional


class TaskError(ValueError):
    pass


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    title: str
    nl_description: str
    isa_applicability: Any
    init: Dict[str, Any]
    expected: Dict[str, Any]
    category: str = ""
    difficulty: str = ""
    memory_arch: str = "neumann"
    reference_solutions: Dict[str, str] = field(default_factory=dict)

    @property
    def isa(self) -> str:
        if isinstance(self.isa_applicability, str):
            return self.isa_applicability.lower()
        if isinstance(self.isa_applicability, list) and len(self.isa_applicability) == 1:
            return str(self.isa_applicability[0]).lower()
        raise TaskError("Task requires one selected ISA")


def _task_paths(task_ref: str) -> list[Path]:
    root = Path(__file__).resolve().parents[1]
    ref = Path(task_ref)
    if ref.suffix in (".yaml", ".yml", ".json"):
        return [ref if ref.is_absolute() else root / ref]
    return [root / "tasks" / f"{task_ref}.yaml", root / "eval" / "tasks" / f"{task_ref}.json"]


def load_task(task_ref: str) -> TaskSpec:
    for path in _task_paths(task_ref):
        if path.is_file():
            try:
                if path.suffix == ".json":
                    raw = json.loads(path.read_text(encoding="utf-8"))
                else:
                    import yaml
                    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, ImportError) as exc:
                raise TaskError(f"Could not load task '{task_ref}': {exc}") from exc
            if not isinstance(raw, dict):
                raise TaskError(f"Malformed task '{task_ref}'")
            try:
                expected = dict(raw["expected"])
                return TaskSpec(
                    task_id=str(raw.get("id", path.stem)),
                    title=str(raw.get("title", path.stem)),
                    nl_description=str(raw.get("nl_description", raw.get("description", ""))),
                    isa_applicability=raw.get("isa_applicability", raw.get("isa")),
                    init=dict(raw.get("init", {})),
                    expected=expected,
                    category=str(raw.get("category", "")),
                    difficulty=str(raw.get("difficulty", "")),
                    memory_arch=str(raw.get("memory_arch", raw.get("memory_architecture", "neumann"))).lower(),
                    reference_solutions=dict(raw.get("reference_solutions", {})),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise TaskError(f"Malformed task '{task_ref}': {exc}") from exc
    raise TaskError(f"Unknown Copilot task: {task_ref}")


def check_result(result: Dict[str, Any], expected: Dict[str, Any]) -> Dict[str, Any]:
    """Compare only a copied task expectation; model input cannot alter it."""
    expected_copy = copy.deepcopy(expected)
    actual = {
        **result,
        "cycle_count": result.get("cycles", result.get("cycle_count")),
    }
    failures = []
    for field, wanted in expected_copy.items():
        got = actual.get(field)
        if field in ("registers", "flags", "memory"):
            got = got or {}
            for name, value in dict(wanted).items():
                if got.get(name) != value:
                    failures.append({"field": field, "name": name, "expected": value, "actual": got.get(name)})
        elif got != wanted:
            failures.append({"field": field, "expected": wanted, "actual": got})
    return {"passed": not failures, "failures": failures}


__all__ = ["TaskError", "TaskSpec", "load_task", "check_result"]
