"""Strict, observable-based ISA translation verification."""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from copilot.gateway import ModelGateway
from copilot.spec import build_isa_card
from core.assembler.assembler import Assembler
from core.assembler.exceptions import AssemblerError
from core.isa.isa_def import ISA
from core.runtime import run_program


ISAS = {"risc1", "risc2", "risc3", "cisc"}


@dataclass(frozen=True)
class TranslationVector:
    vector_id: str
    init: Dict[str, Any] = field(default_factory=dict)
    memory_arch: str = "neumann"
    max_cycles: int = 10_000


@dataclass(frozen=True)
class TranslationSpec:
    source_isa: str
    target_isa: str
    source: str
    vectors: List[TranslationVector]
    memory_ranges: List[tuple[int, int]] = field(default_factory=list)
    observe_output: bool = True


def _instruction_count(source: str) -> int:
    return sum(
        bool(line.strip()) and not line.lstrip().startswith(("#", ";"))
        for line in source.splitlines()
    )


def _observable(result: Dict[str, Any], spec: TranslationSpec) -> Dict[str, Any]:
    values: Dict[str, Any] = {
        "output": result.get("output", "") if spec.observe_output else None,
        "halted": result.get("halted", False),
    }
    dump = result.get("memory_dump", {})
    values["memory"] = {
        key: dump.get(key, []) for key in sorted(dump)
    }
    return values


def verify_translation(spec: TranslationSpec, target_source: str) -> Dict[str, Any]:
    """Run source and target for every vector; the simulator decides verdicts."""
    vector_results: List[Dict[str, Any]] = []
    for vector in spec.vectors:
        source_result = run_program(
            spec.source_isa, vector.memory_arch, spec.source, vector.init,
            vector.max_cycles, strict=True, memory_ranges=spec.memory_ranges,
        )
        target_result = run_program(
            spec.target_isa, vector.memory_arch, target_source, vector.init,
            vector.max_cycles, strict=True, memory_ranges=spec.memory_ranges,
        )
        source_obs = _observable(source_result, spec)
        target_obs = _observable(target_result, spec)
        differences = {
            name: {"source": source_obs[name], "target": target_obs[name]}
            for name in source_obs if source_obs[name] != target_obs[name]
        }
        vector_results.append({
            "vector_id": vector.vector_id,
            "passed": not source_result["errors"] and not target_result["errors"] and not differences,
            "differences": differences,
            "source_cycles": source_result["cycles"],
            "target_cycles": target_result["cycles"],
            "source_errors": source_result["errors"],
            "target_errors": target_result["errors"],
        })
    source_count = _instruction_count(spec.source)
    target_count = _instruction_count(target_source)
    return {
        "passed": all(item["passed"] for item in vector_results),
        "source_isa": spec.source_isa,
        "target_isa": spec.target_isa,
        "target_source": target_source,
        "vectors": vector_results,
        "instruction_count_ratio": target_count / source_count if source_count else 0,
        "source_instruction_count": source_count,
        "target_instruction_count": target_count,
    }


TRANSLATE_TOOL = {
    "type": "function",
    "function": {
        "name": "translate_program",
        "description": "Return target-ISA assembly that preserves all listed observables.",
        "parameters": {
            "type": "object",
            "properties": {
                "source_isa": {"type": "string", "enum": sorted(ISAS)},
                "target_isa": {"type": "string", "enum": sorted(ISAS)},
                "source": {"type": "string"},
            },
            "required": ["source_isa", "target_isa", "source"],
            "additionalProperties": False,
        },
    },
}


def _validate_args(args: Any) -> Dict[str, str]:
    if not isinstance(args, dict) or set(args) != {"source_isa", "target_isa", "source"}:
        raise ValueError("translate_program requires source_isa, target_isa, and source")
    source_isa = str(args["source_isa"]).lower()
    target_isa = str(args["target_isa"]).lower()
    if source_isa not in ISAS or target_isa not in ISAS or source_isa == target_isa:
        raise ValueError("source_isa and target_isa must be different supported ISAs")
    if not isinstance(args["source"], str) or not args["source"].strip():
        raise ValueError("source must be non-empty assembly text")
    return {"source_isa": source_isa, "target_isa": target_isa, "source": args["source"]}


class TranslationAgent:
    def __init__(self, gateway: Any, episode_dir: str = "logs/copilot_translation",
                 card_budget: int = 1800, wall_timeout: float = 120.0,
                 tier: str = "fast"):
        self.gateway = gateway
        self.episode_dir = Path(episode_dir)
        self.card_budget = card_budget
        self.wall_timeout = wall_timeout
        self.tier = tier

    def translate(self, spec: TranslationSpec, max_repairs: int = 4) -> Dict[str, Any]:
        source_card = build_isa_card(spec.source_isa, self.card_budget)["text"]
        target_card = build_isa_card(spec.target_isa, self.card_budget)["text"]
        vectors = [{"vector_id": vector.vector_id, "init": vector.init} for vector in spec.vectors]
        messages: List[Dict[str, Any]] = [{
            "role": "system",
            "content": "Translate assembly only. Do not claim equivalence. "
                       "The harness runs both programs and decides the verdict.\n"
                       f"SOURCE ISA CARD:\n{source_card}\nTARGET ISA CARD:\n{target_card}\n"
                       f"TEST VECTORS:\n{json.dumps(vectors, separators=(',', ':'))}",
        }, {"role": "user", "content": spec.source}]
        episode: Dict[str, Any] = {
            "episode_id": str(uuid.uuid4()), "kind": "translation",
            "source_isa": spec.source_isa, "target_isa": spec.target_isa,
            "messages": [], "tool_calls": [], "results": [], "verdict": "failed",
            "tokens": {"in": 0, "out": 0}, "latency_ms": 0.0,
        }
        started = time.monotonic()
        for _ in range(max_repairs + 1):
            if time.monotonic() - started >= self.wall_timeout:
                episode["verdict"] = "timeout"
                break
            response = self.gateway.generate(messages, tools=[TRANSLATE_TOOL], tier=self.tier)
            episode["messages"].append({"messages": list(messages), "response": response})
            usage = response.get("usage", {})
            episode["tokens"]["in"] += int(usage.get("in", 0))
            episode["tokens"]["out"] += int(usage.get("out", 0))
            episode["latency_ms"] += float(response.get("latency_ms", 0))
            calls = response.get("tool_calls", [])
            if not calls:
                episode["verdict"] = "gave_up"
                break
            call = calls[0]
            try:
                args = _validate_args(call.get("arguments", {}))
                Assembler(ISA(args["target_isa"])).assemble(args["source"])
                result = verify_translation(spec, args["source"])
            except AssemblerError as exc:
                result = {"passed": False, "target_source": args.get("source", ""),
                          "vectors": [], "errors": [exc.as_dict()]}
            except (ValueError, KeyError) as exc:
                result = {"passed": False, "target_source": "", "vectors": [],
                          "errors": [{"kind": "tool_error", "message": str(exc)}]}
            episode["tool_calls"].append({"name": "translate_program", "arguments": call.get("arguments", {})})
            episode["results"].append(result)
            if result["passed"]:
                episode["verdict"] = "passed"
                break
            feedback = [
                {"vector_id": item["vector_id"], "differences": item["differences"]}
                for item in result.get("vectors", []) if not item["passed"]
            ]
            messages.append({"role": "user", "content": json.dumps(
                {"mismatches": feedback, "errors": result.get("errors", [])},
                separators=(",", ":"),
            )})
        episode["translation"] = episode["results"][-1] if episode["results"] else None
        self.episode_dir.mkdir(parents=True, exist_ok=True)
        (self.episode_dir / f"{episode['episode_id']}.json").write_text(
            json.dumps(episode, indent=2), encoding="utf-8"
        )
        return episode


__all__ = [
    "TRANSLATE_TOOL", "TranslationAgent", "TranslationSpec",
    "TranslationVector", "verify_translation",
]
