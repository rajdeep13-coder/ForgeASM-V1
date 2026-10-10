"""Bounded assembly-writing Copilot agent and episode persistence."""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from copilot.gateway import ModelGateway
from copilot.spec import build_isa_card
from copilot.tasks import TaskSpec, check_result
from core.assembler.assembler import Assembler
from core.assembler.exceptions import AssemblerError
from core.isa.isa_def import ISA
from core.runtime import run_program


def _schema(name: str, properties: Dict[str, Any], required: List[str]) -> Dict[str, Any]:
    return {"type": "function", "function": {"name": name, "parameters": {
        "type": "object", "properties": properties, "required": required,
        "additionalProperties": False,
    }}}


TOOLS = [
    _schema("get_isa_card", {"isa": {"type": "string", "enum": ["risc1", "risc2", "risc3", "cisc"]}}, ["isa"]),
    _schema("assemble", {"isa": {"type": "string"}, "source": {"type": "string"}}, ["isa", "source"]),
    _schema("run", {"isa": {"type": "string"}, "memory_arch": {"type": "string"},
                    "source": {"type": "string"}, "init": {"type": "object"},
                    "max_cycles": {"type": "integer", "minimum": 1, "maximum": 10000}},
           ["isa", "memory_arch", "source", "init", "max_cycles"]),
    _schema("inspect", {"result_id": {"type": "string"},
                        "what": {"type": "string"}}, ["result_id", "what"]),
    _schema("submit", {"source": {"type": "string"}}, ["source"]),
]


def _validate(name: str, args: Any) -> Dict[str, Any]:
    if not isinstance(args, dict):
        raise ValueError("tool arguments must be an object")
    allowed = {
        "get_isa_card": {"isa"}, "assemble": {"isa", "source"},
        "run": {"isa", "memory_arch", "source", "init", "max_cycles"},
        "inspect": {"result_id", "what"}, "submit": {"source"},
    }[name]
    if set(args) != allowed:
        raise ValueError(f"{name} requires exactly: {', '.join(sorted(allowed))}")
    if name in ("assemble", "run", "get_isa_card") and str(args["isa"]).lower() not in {"risc1", "risc2", "risc3", "cisc"}:
        raise ValueError("isa must be risc1, risc2, risc3, or cisc")
    if name in ("assemble", "run", "submit") and (not isinstance(args.get("source"), str) or not args["source"].strip()):
        raise ValueError("source must be non-empty assembly text")
    if name == "run" and (not isinstance(args["max_cycles"], int) or isinstance(args["max_cycles"], bool) or not 1 <= args["max_cycles"] <= 10000):
        raise ValueError("max_cycles must be an integer from 1 to 10000")
    if name == "inspect":
        what = str(args["what"])
        if what not in {"registers", "flags", "memory", "trace"} and not (
            what.startswith("memory:") or what.startswith("trace:")
        ):
            raise ValueError("what must be registers, flags, memory, trace, memory:start:end, or trace:start:end")
    return args


class CopilotAgent:
    def __init__(self, gateway: Any, episode_dir: str = "logs/copilot_episodes",
                 card_budget: int = 1800, wall_timeout: float = 120.0,
                 tier: str = "fast"):
        self.gateway = gateway
        self.episode_dir = Path(episode_dir)
        self.card_budget = card_budget
        self.wall_timeout = wall_timeout
        self.tier = tier
        self.results: Dict[str, Dict[str, Any]] = {}

    def _tool(self, task: TaskSpec, name: str, raw_args: Any) -> Dict[str, Any]:
        args = _validate(name, raw_args)
        if name == "get_isa_card":
            return build_isa_card(args["isa"], self.card_budget)
        if name == "assemble":
            try:
                binary = Assembler(ISA(args["isa"])).assemble(args["source"])
                return {"ok": True, "binary_length": len(binary.replace("\n", ""))}
            except AssemblerError as exc:
                return {"ok": False, "errors": [exc.as_dict()]}
        if name == "run":
            result = run_program(args["isa"], args["memory_arch"], args["source"],
                                 args["init"], args["max_cycles"], strict=True, trace=True)
            result_id = str(uuid.uuid4())
            self.results[result_id] = result
            checker = check_result(result, task.expected)
            # Only checker-visible names and values are sent back to the model.
            diff = {"passed": checker["passed"], "failures": checker["failures"]}
            response = {"result_id": result_id, "assembled": bool(result["assembled"]),
                        "errors": result["errors"], "halted": result["halted"],
                        "timed_out": result["timed_out"], "cycles": result["cycles"],
                        "checker": diff}
            return response
        if name == "inspect":
            result = self.results.get(args["result_id"])
            if result is None:
                raise ValueError("unknown result_id")
            what = args["what"]
            if what == "memory" or what.startswith("memory:"):
                dump = result["memory_dump"]
                if ":" in what:
                    _, start, end = what.split(":", 2)
                    selected = f"{int(start)}:{int(end)}"
                    dump = {selected: dump.get(selected, [])}
                return {"memory_dump": dump}
            if what == "trace" or what.startswith("trace:"):
                trace = result.get("trace") or []
                if ":" in what:
                    _, start, end = what.split(":", 2)
                    trace = trace[int(start):int(end)]
                return {"trace": trace}
            return {what: result.get(what)}
        if name == "submit":
            return {"submitted": True, "source": args["source"]}
        raise ValueError(f"unsupported tool: {name}")

    def solve(self, task: TaskSpec, max_repairs: int = 4) -> Dict[str, Any]:
        started = time.monotonic()
        episode: Dict[str, Any] = {"episode_id": str(uuid.uuid4()), "task_id": task.task_id,
                                   "isa": task.isa, "messages": [], "tool_calls": [],
                                   "results": [], "verdict": "failed", "tokens": {"in": 0, "out": 0},
                                   "latency_ms": 0.0}
        card = build_isa_card(task.isa, self.card_budget)
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": "Write assembly only. Use tools to assemble, run, inspect, and submit. "
             "The checker is server-owned; never attempt to alter task expectations.\n" + card["text"]},
            {"role": "user", "content": task.nl_description},
        ]
        repairs = 0
        try:
            while repairs <= max_repairs and time.monotonic() - started < self.wall_timeout:
                response = self.gateway.generate(messages, tools=TOOLS, tier=self.tier)
                episode["messages"].append({"messages": list(messages), "response": response})
                usage = response.get("usage", {})
                episode["tokens"]["in"] += int(usage.get("in", 0))
                episode["tokens"]["out"] += int(usage.get("out", 0))
                episode["latency_ms"] += float(response.get("latency_ms", 0))
                calls = response.get("tool_calls", [])
                if len(calls) > 4:
                    raise ValueError("model exceeded four tool calls per turn")
                if not calls:
                    episode["verdict"] = "no_tool_call"
                    break
                for call in calls:
                    name = call.get("name")
                    args = call.get("arguments", {})
                    episode["tool_calls"].append({"name": name, "arguments": args})
                    try:
                        output = self._tool(task, name, args)
                    except (ValueError, KeyError) as exc:
                        output = {"ok": False, "error": str(exc)}
                    episode["results"].append(output)
                    if name == "submit":
                        final = self._tool(task, "run", {
                            "isa": task.isa, "memory_arch": task.memory_arch,
                            "source": args["source"], "init": task.init,
                            "max_cycles": int(task.expected.get("max_cycles", 10000)),
                        })
                        episode["results"].append(final)
                        episode["verdict"] = "passed" if final["checker"]["passed"] else "failed"
                        if episode["verdict"] == "passed":
                            return self._persist(episode)
                    if output.get("checker", {}).get("passed"):
                        episode["verdict"] = "passed"
                        return self._persist(episode)
                repairs += 1
                messages.append({"role": "user", "content": json.dumps(episode["results"][-1], separators=(",", ":"))})
        except Exception as exc:
            episode["verdict"] = "error"
            episode["error"] = str(exc)
        if time.monotonic() - started >= self.wall_timeout:
            episode["verdict"] = "timeout"
        return self._persist(episode)

    def _persist(self, episode: Dict[str, Any]) -> Dict[str, Any]:
        self.episode_dir.mkdir(parents=True, exist_ok=True)
        path = self.episode_dir / f"{episode['episode_id']}.json"
        path.write_text(json.dumps(episode, indent=2, default=str), encoding="utf-8")
        return episode


def run_agent(task: TaskSpec, provider: Optional[Any] = None, max_iterations: int = 4) -> Dict[str, Any]:
    """Compatibility wrapper retaining the prior API."""
    gateway = provider
    if gateway is None:
        gateway = ModelGateway()
    if hasattr(gateway, "complete"):
        class Adapter:
            def __init__(self, provider: Any):
                self.provider = provider
            def generate(self, messages, tools=None):
                response = self.provider.complete(messages, tools)
                return {"text": response.content, "tool_calls": [
                    {"name": call.name, "arguments": call.arguments} for call in response.tool_calls
                ], "usage": {"in": 0, "out": 0}, "latency_ms": 0, "model_id": "compat",
                        "backend": "MOCK", "bytes_off_device": 0}
        gateway = Adapter(provider)
    return CopilotAgent(gateway).solve(task, max_repairs=max_iterations)


__all__ = ["TOOLS", "CopilotAgent", "run_agent"]
