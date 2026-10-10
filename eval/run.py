"""Run and replay the ForgeASM task/model evaluation matrix.

The report is deliberately generated from ``results.json``.  No metric or
finding is stored as a hand-authored number.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List

from copilot.agent import CopilotAgent
from copilot.gateway import GatewayConfigurationError, ModelGateway, ModelUnavailable, MockBackend
from copilot.tasks import TaskError, load_task
from core.runtime import run_program


ROOT = Path(__file__).resolve().parents[1]
TASK_DIR = ROOT / "eval" / "tasks"
RESULTS_PATH = ROOT / "eval" / "results.json"
REPORT_PATH = ROOT / "eval" / "RESULTS.md"
EPISODE_DIR = ROOT / "eval" / "episodes"


def task_files() -> List[Path]:
    return sorted(TASK_DIR.glob("*.json"))


def validate_references() -> List[Dict[str, Any]]:
    failures = []
    for path in task_files():
        task = load_task(str(path))
        for isa, source in task.reference_solutions.items():
            result = run_program(isa, task.memory_arch, source, task.init, 10_000, strict=True)
            from copilot.tasks import check_result
            check = check_result(result, task.expected)
            if result["errors"] or not check["passed"]:
                failures.append({"task": task.task_id, "isa": isa, "result": result, "checker": check})
    if failures:
        raise AssertionError(f"{len(failures)} reference solutions failed")
    return [{"task": load_task(str(path)).task_id, "isa": isa}
            for path in task_files() for isa in load_task(str(path)).reference_solutions]


def _classify(episode: Dict[str, Any]) -> str:
    for result in episode.get("results", []):
        for error in result.get("errors", []):
            kind = error.get("kind")
            if kind == "unknown_mnemonic":
                return "unknown_mnemonic"
            if kind in {"undefined_label", "duplicate_label", "invalid_directive"}:
                return "label_error"
            if kind == "bad_operand":
                return "bad_operand"
        if result.get("timed_out"):
            return "infinite_loop/timeout"
        failures = result.get("checker", {}).get("failures", [])
        if failures:
            return "wrong_semantics"
    if episode.get("verdict") == "no_tool_call":
        return "gave_up"
    return "gave_up" if episode.get("verdict") != "passed" else ""


def _empty_cell(task: Any, model: str, reason: str, ablation: str) -> Dict[str, Any]:
    return {"task": task.task_id, "isa": task.isa, "model": model, "ablation": ablation,
            "status": "skipped", "skip_reason": reason}


def _mock_gateway() -> ModelGateway:
    responses = []
    for _ in range(max(26, len(task_files())) * 4):
        responses.append({"tool_calls": [{"name": "submit", "arguments": {"source": "halt\n"}}],
                          "usage": {"in": 20, "out": 4}})
    gateway = ModelGateway(backend=MockBackend([{"text": "probe"}, *responses],
        capabilities={"supports_images": False, "supports_tool_calling": True,
                       "supports_json_schema": True}), telemetry_path="eval/mock_telemetry.jsonl")
    gateway.startup_check()
    return gateway


def _run_cell(task: Any, model: str, ablation: str, gateway: ModelGateway,
              reference_cycles: int) -> Dict[str, Any]:
    started = time.perf_counter()
    agent = CopilotAgent(gateway, episode_dir=str(EPISODE_DIR), tier="heavy" if model == "heavy-local" else "fast")
    variant = ablation if ablation in {"no-card", "card-no-examples"} else "full"
    telemetry_before = len(gateway.telemetry())
    episode = agent.solve(task, max_repairs=0 if ablation == "no-repair" else 4,
                          card_variant=variant)
    elapsed = (time.perf_counter() - started) * 1000
    tokens = episode.get("tokens", {"in": 0, "out": 0})
    attempts = [item for item in episode.get("results", []) if "checker" in item]
    assembled = [item for item in episode.get("results", []) if "errors" not in item or item.get("assembled")]
    return {
        "task": task.task_id, "isa": task.isa, "model": model, "ablation": ablation,
        "status": "completed", "verdict": episode.get("verdict"),
        "assemble_ok_at_1": bool(assembled[:1]) and not (assembled[0].get("errors") if assembled else []),
        "pass_at_1": bool(attempts[:1] and attempts[0].get("checker", {}).get("passed")),
        "pass_at_repair": episode.get("verdict") == "passed",
        "repair_turns": max(0, len(attempts) - 1),
        "tokens_in": tokens.get("in", 0), "tokens_out": tokens.get("out", 0),
        "latency_ms": episode.get("latency_ms", elapsed),
        "tokens_per_sec": (sum(tokens.values()) / (episode.get("latency_ms", elapsed) / 1000)
                           if episode.get("latency_ms", elapsed) else 0),
        "cycles": next((item.get("cycles", 0) for item in reversed(attempts)), 0),
        "reference_cycles": reference_cycles,
        "efficiency_ratio": (
            next((item.get("cycles", 0) for item in reversed(attempts)), 0) / reference_cycles
            if reference_cycles else 0
        ),
        "bytes_off_device": sum(record.get("bytes_off_device", 0)
                                for record in gateway.telemetry()[telemetry_before:]),
        "failure": _classify(episode),
        "episode_id": episode.get("episode_id"),
    }


def _models() -> Dict[str, str]:
    configured = {"fast-local": os.getenv("GEMMA_FAST_MODEL", "")}
    if os.getenv("GEMMA_HEAVY_MODEL"):
        configured["heavy-local"] = os.environ["GEMMA_HEAVY_MODEL"]
    if os.getenv("GEMMA_BACKEND", "LOCAL").upper() == "CLOUD" and os.getenv("GEMMA_API_KEY"):
        configured["cloud"] = os.getenv("GEMMA_FAST_MODEL", "")
    return configured


def run_matrix(use_mock: bool = False) -> Dict[str, Any]:
    references = validate_references()
    cells: List[Dict[str, Any]] = []
    tasks = [load_task(str(path)) for path in task_files()]
    models = {"mock": "mock"} if use_mock else _models()
    for model in models:
        for task in tasks:
            reference = next(iter(task.reference_solutions.values()), "halt\n")
            reference_result = run_program(task.isa, task.memory_arch, reference,
                                           task.init, 10_000, strict=True)
            reference_cycles = reference_result["cycles"]
            try:
                gateway = _mock_gateway() if model == "mock" else ModelGateway()
                if model != "mock":
                    capabilities = gateway.startup_check()
                    if not capabilities.available:
                        raise ModelUnavailable(capabilities.error or "model unavailable")
                for ablation in ("no-card", "card-no-examples", "full-card", "no-repair"):
                    cells.append(_run_cell(task, model, ablation, gateway, reference_cycles))
            except (GatewayConfigurationError, ModelUnavailable, OSError) as exc:
                for ablation in ("no-card", "card-no-examples", "full-card", "no-repair"):
                    cells.append(_empty_cell(task, model, str(exc), ablation))
    return {"schema_version": 1, "generated_at": time.time(), "references": references, "cells": cells}


def _summary(cells: Iterable[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for cell in cells:
        if cell.get("status") == "completed":
            groups.setdefault(str(cell.get(key)), []).append(cell)
    rows = []
    for name, items in sorted(groups.items()):
        rows.append({"name": name, "n": len(items),
                     "assemble_ok@1": mean(int(i["assemble_ok_at_1"]) for i in items),
                     "pass@1": mean(int(i["pass_at_1"]) for i in items),
                     "pass@repair": mean(int(i["pass_at_repair"]) for i in items),
                     "mean_repair_turns": mean(i["repair_turns"] for i in items),
                     "tokens": mean(i["tokens_in"] + i["tokens_out"] for i in items),
                     "latency_ms": mean(i["latency_ms"] for i in items),
                     "tokens/sec": mean(i["tokens_per_sec"] for i in items),
                     "efficiency_ratio": mean(i["efficiency_ratio"] for i in items),
                     "bytes_off_device": mean(i["bytes_off_device"] for i in items)})
    return rows


def _table(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return "_No completed cells._"
    keys = ["name", "n", "assemble_ok@1", "pass@1", "pass@repair", "mean_repair_turns",
            "tokens", "latency_ms", "tokens/sec", "efficiency_ratio", "bytes_off_device"]
    out = ["| " + " | ".join(keys) + " |", "|" + "|".join(["---"] * len(keys)) + "|"]
    for row in rows:
        out.append("| " + " | ".join(
            str(round(row.get(key, 0), 4)) if isinstance(row.get(key), float) else str(row.get(key, ""))
            for key in keys) + " |")
    return "\n".join(out)


def render_report(data: Dict[str, Any]) -> str:
    completed = [c for c in data["cells"] if c.get("status") == "completed"]
    skipped = len(data["cells"]) - len(completed)
    taxonomy: Dict[str, int] = {}
    for cell in completed:
        if cell.get("failure"):
            taxonomy[cell["failure"]] = taxonomy.get(cell["failure"], 0) + 1
    return "\n".join([
        "# ForgeASM Evaluation Results", "",
        f"Generated from `eval/results.json`; completed cells: {len(completed)}, skipped cells: {skipped}.", "",
        "## Per-ISA", "", _table(_summary(data["cells"], "isa")), "",
        "## Per-model", "", _table(_summary(data["cells"], "model")), "",
        "## Ablations", "", _table(_summary(data["cells"], "ablation")), "",
        "## Failure taxonomy", "", "```json", json.dumps(taxonomy, indent=2, sort_keys=True), "```", "",
        "## Findings", "",
        f"- The reference gate validated {len(data['references'])} task/ISA solutions before model scoring.",
        f"- {skipped} cells were skipped because their backend was unavailable; no unavailable backend is scored as zero.",
        f"- Completed cells used measured token, latency, throughput, cycle, and off-device-byte fields ({len(completed)} observations).",
        "- Ablation rows are generated from the same stored cell schema, so replay does not call a model.",
        "- Honest limitation: without configured local/cloud models, this run cannot claim real-model pass rates.",
    ])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replay", action="store_true")
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()
    if args.replay:
        data = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    else:
        data = run_matrix(use_mock=args.mock)
        RESULTS_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    REPORT_PATH.write_text(render_report(data) + "\n", encoding="utf-8")
    print(f"wrote {RESULTS_PATH} and {REPORT_PATH}")


if __name__ == "__main__":
    main()
