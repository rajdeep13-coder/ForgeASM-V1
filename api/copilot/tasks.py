"""Server-owned Copilot tasks and deterministic checkers."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List


class TaskError(ValueError):
    """Raised when a task is missing or malformed."""


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    isa: str
    memory_architecture: str
    description: str
    expected: Dict[str, Any]


def _task_directory() -> str:
    return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "eval", "tasks")


def load_task(task_id: str) -> TaskSpec:
    if not task_id or os.path.basename(task_id) != task_id:
        raise TaskError("Invalid task id")
    path = os.path.join(_task_directory(), f"{task_id}.json")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except FileNotFoundError as exc:
        raise TaskError(f"Unknown Copilot task: {task_id}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise TaskError(f"Could not load Copilot task '{task_id}'") from exc
    try:
        return TaskSpec(
            task_id=task_id,
            isa=str(raw["isa"]).lower(),
            memory_architecture=str(raw.get("memory_architecture", "neumann")).lower(),
            description=str(raw["description"]),
            expected=dict(raw["expected"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise TaskError(f"Malformed Copilot task '{task_id}'") from exc


def check_state(state: Dict[str, Any], expected: Dict[str, Any]) -> Dict[str, Any]:
    """Compare only task-declared fields; this function is never model supplied."""
    failures: List[str] = []
    for field, expected_value in expected.items():
        actual_value = state.get(field)
        if field in ("registers", "memory", "flags"):
            for key, value in dict(expected_value).items():
                if actual_value.get(key) != value:
                    failures.append(f"{field}.{key}: expected {value!r}, got {actual_value.get(key)!r}")
        elif actual_value != expected_value:
            failures.append(f"{field}: expected {expected_value!r}, got {actual_value!r}")
    return {"passed": not failures, "failures": failures}

