# Changelog

## Unreleased

- Added a local-first Gemma Copilot backend vertical slice with a constrained
  assemble-and-run tool, server-owned deterministic task checking, and a
  benchmark task seed.
- Added structured assembler diagnostics, opt-in strict opcode execution,
  in-process `run_program`, the ground-truth audit, and CI test workflow.
- Added the centralized `copilot.ModelGateway` with local/cloud routing,
  capability probes, text-protocol fallback, retry handling, telemetry, JSONL
  persistence, and deterministic mock backend tests.
- Added the bounded assembly-writing Copilot agent with verified ISA cards,
  strict assemble/run/inspect/submit tools, immutable task checking, YAML task
  loading, episode JSON persistence, repair limits, and `python -m copilot.solve`.
