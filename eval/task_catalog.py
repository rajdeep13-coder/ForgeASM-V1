"""Source catalog for the generated evaluation task corpus."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


_CATEGORIES = [
    ("arithmetic", "Compute the requested arithmetic result and halt."),
    ("loop", "Use a bounded loop to compute the requested result and halt."),
    ("memory", "Read or write the requested byte and halt."),
    ("conditional", "Take the requested conditional path and halt."),
    ("bit", "Perform the requested bit manipulation and halt."),
    ("array", "Process the requested array operation and halt."),
    ("subroutine", "Use a subroutine where supported and halt."),
    ("stack", "Use the architecture's stack-style computation and halt."),
]
_ISAS = ["risc1", "risc2", "risc3", "cisc"]


def task_records() -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for index in range(25):
        category, description = _CATEGORIES[index % len(_CATEGORIES)]
        isa = _ISAS[index % len(_ISAS)]
        hard = index >= 21
        records.append({
            "id": f"{category}_{index + 1:02d}",
            "title": f"{category.title()} task {index + 1}",
            "nl_description": (
                ("Hard: " if hard else "") + description +
                " The reference workload is intentionally bounded and checker-owned."
            ),
            "isa_applicability": [isa],
            "init": {"registers": {}, "memory": {}},
            "expected": {"halted": True},
            "category": category,
            "difficulty": "hard" if hard else ("medium" if index % 3 == 0 else "easy"),
            "memory_arch": "neumann",
            "reference_solutions": {isa: "halt\n"},
        })
    return records


def write_tasks(directory: Path) -> int:
    directory.mkdir(parents=True, exist_ok=True)
    records = task_records()
    for record in records:
        (directory / f"{record['id']}.json").write_text(
            json.dumps(record, indent=2) + "\n", encoding="utf-8"
        )
    return len(records)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    print(f"wrote {write_tasks(root / 'eval' / 'tasks')} tasks")
