"""Command-line entry point for a Copilot task episode."""
from __future__ import annotations

import argparse
import json
from dataclasses import replace

from copilot.agent import CopilotAgent
from copilot.gateway import ModelGateway
from copilot.tasks import load_task


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--isa", required=True, choices=["risc1", "risc2", "risc3", "cisc"])
    parser.add_argument("--task", required=True)
    parser.add_argument("--model", choices=["fast", "heavy"], default="fast")
    args = parser.parse_args()
    task = load_task(args.task)
    applicable = task.isa_applicability
    if isinstance(applicable, list):
        if args.isa not in [str(item).lower() for item in applicable]:
            parser.error(f"task is not applicable to {args.isa}")
        task = replace(task, isa_applicability=args.isa)
    elif task.isa != args.isa:
        parser.error(f"task ISA is {task.isa}, not {args.isa}")
    gateway = ModelGateway()
    gateway.startup_check()
    result = CopilotAgent(gateway, tier=args.model).solve(task)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
