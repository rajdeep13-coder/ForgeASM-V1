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
- Added the generated `eval/` task corpus, reference-solution gate, measured
  model matrix, failure taxonomy, ablations, JSON results, Markdown report, and
  replay mode via `python -m eval.run`.
- Added simulator-verified ISA translation with explicit neutral observables,
  bounded repair episodes, translation API/UI, reference fixtures, and
  generated translation expansion metrics.
- Added capability-gated multimodal photo transcription with client-side
  EXIF-stripping/downscaling, user confirmation, strict checker limits, and
  prompt-injection safeguards.
- Added a trace-only explainer with verified cycle/value citations, a
  localhost-only network-guard regression test, and benchmark telemetry export
  with session totals in the Copilot performance panel.
