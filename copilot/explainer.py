"""Trace-only explanations with machine-checked cycle citations."""
from __future__ import annotations

import json
from typing import Any, Dict, List


EXPLAIN_SCHEMA = {
    "name": "trace_explanation",
    "schema": {
        "type": "object",
        "properties": {
            "answer": {"type": "string"},
            "citations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "cycle": {"type": "integer", "minimum": 0},
                        "path": {"type": "string"},
                        "value": {},
                    },
                    "required": ["cycle", "path", "value"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["answer", "citations"],
        "additionalProperties": False,
    },
}


def _path_value(diff: Dict[str, Any], path: str) -> Any:
    value: Any = diff
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            raise KeyError(path)
        value = value[part]
    return value


def validate_citations(trace: List[Dict[str, Any]], citations: Any) -> Dict[str, Any]:
    warnings: List[str] = []
    verified: List[Dict[str, Any]] = []
    by_cycle = {entry.get("cycle"): entry for entry in trace}
    if not isinstance(citations, list):
        return {"verified": [], "warnings": ["The model returned no citation list."]}
    for citation in citations:
        if not isinstance(citation, dict):
            warnings.append("Ignored a malformed citation.")
            continue
        cycle = citation.get("cycle")
        path = citation.get("path")
        expected = citation.get("value")
        entry = by_cycle.get(cycle)
        if entry is None:
            warnings.append(f"Cycle {cycle} does not exist in the stored trace.")
            continue
        try:
            actual = _path_value(entry.get("diff", {}), str(path))
        except KeyError:
            warnings.append(f"Cycle {cycle} does not cite a value at {path}.")
            continue
        if actual != expected:
            warnings.append(
                f"Cycle {cycle} value mismatch for {path}: cited {expected!r}, trace has {actual!r}."
            )
            continue
        verified.append({"cycle": cycle, "path": path, "value": actual})
    return {"verified": verified, "warnings": warnings}


def explain_trace(gateway: Any, result: Dict[str, Any], question: str) -> Dict[str, Any]:
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be non-empty")
    trace = result.get("trace") or []
    response = gateway.generate(
        [{
            "role": "system",
            "content": (
                "Answer using only the supplied per-step state diffs. "
                "Every factual claim must cite a cycle and exact diff path/value. "
                "Do not infer state that is not present in a diff. Return JSON only."
            ),
        }, {
            "role": "user",
            "content": json.dumps({"question": question, "trace": trace}, separators=(",", ":")),
        }],
        json_schema=EXPLAIN_SCHEMA,
        tier="fast",
    )
    try:
        payload = json.loads(response.get("text", ""))
    except json.JSONDecodeError as exc:
        raise ValueError("trace explanation was not valid JSON") from exc
    checked = validate_citations(trace, payload.get("citations"))
    answer = str(payload.get("answer", ""))
    for citation in checked["verified"]:
        cycle_text = str(citation["cycle"])
        if cycle_text not in answer:
            checked["warnings"].append(
                f"Answer does not state verified cycle {citation['cycle']}."
            )
    return {
        "answer": answer,
        "citations": checked["verified"],
        "warnings": checked["warnings"],
        "trace_cycles": [entry.get("cycle") for entry in trace],
    }


__all__ = ["EXPLAIN_SCHEMA", "explain_trace", "validate_citations"]
