"""Generate judge-facing docs from eval/results.json."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / "eval" / "results.json").read_text(encoding="utf-8"))
RESULTS = (ROOT / "eval" / "RESULTS.md").read_text(encoding="utf-8")

def metric_table(section: str) -> str:
    start = RESULTS.index(f"## {section}")
    rest = RESULTS[start:].splitlines()
    rows = []
    for line in rest[2:]:
        if not line.startswith("|"):
            break
        rows.append(line)
    return "\n".join(rows)

def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text.rstrip() + "\n", encoding="utf-8")

write("README.md", f"""# ForgeASM

ForgeASM is a local-first hardware architecture lab where Gemma learns a custom ISA in context, writes assembly, repairs it through assembler/simulator tools, and earns a pass only from a deterministic checker.

## 30-second demo

The demo capture should show: describe a task → inspect the repair loop in
Copilot Logbook → see the verified pass badge. Capture instructions are in
[docs/DEMO.md](docs/DEMO.md); benchmark numbers below are generated from
`eval/results.json`. No unrecorded GIF is presented as evidence.

## Why Gemma 4

Gemma is a strong fit for constrained, local-first reasoning: the model must learn one of four unusual ISAs from a compact card, emit only assembly/tool arguments, and recover from concrete assembler and simulator feedback. Open weights make the same experiment reproducible in classrooms and private labs.

## Quick start

```bash
python -m venv .venv
.venv\\Scripts\\python.exe -m pip install -r requirements.txt
.venv\\Scripts\\python.exe -m pytest -q
cd frontend
npm ci
npm run build
```

Run the API with `..\\.venv\\Scripts\\python.exe -m uvicorn api.main:app --reload` from the repository root, then open the frontend with `npm run dev`. Model use is optional for the simulator; configure `GEMMA_BACKEND`, `GEMMA_FAST_MODEL`, and the local endpoint for Copilot.

## Architecture and trust boundary

```mermaid
flowchart LR
  T[Task / confirmed user spec] --> G[Gemma 4]
  G -->|untrusted assembly, tool args, explanation| A[Assembler]
  A --> S[Strict simulator]
  S --> C[Server-owned deterministic checker]
  C --> V[Pass / fail]
  G -.-> L[Logbook + telemetry]
  X{{TRUST BOUNDARY: model output is untrusted; simulator + checker decide}} -.-> A
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/AUDIT.md](docs/AUDIT.md).

## Measured results

Generated from `eval/results.json` by `python -m scripts.generate_judge_docs`.

### Per ISA

{metric_table("Per-ISA")}

### Per model

{metric_table("Per-model")}

### Ablations

{metric_table("Ablations")}

The complete generated report is [eval/RESULTS.md](eval/RESULTS.md). The current artifact explicitly records when real model backends are unavailable; no unavailable backend is scored as zero.

## Privacy

Local mode sends model requests only to the configured localhost-compatible model endpoint and reports zero off-device bytes. Cloud mode is opt-in and visibly reports off-device telemetry. The simulator/checker remains local and server-owned.

## Limitations

The committed evaluation artifact currently contains mock-model measurements and reference translation gates, not real Gemma measurements. A configured Gemma model is required before claiming real-model pass rates, image transcription accuracy, or live translation success. Runtime sessions are in memory, and the demo GIF/photo assets must be captured locally rather than invented.

## License

Apache-2.0. See [LICENSE](LICENSE).
""")

write("docs/WHY_GEMMA.md", f"""# Why Gemma 4

## Variant policy

Model tags are never hard-coded. `GEMMA_FAST_MODEL` is used for ordinary turns and `GEMMA_HEAVY_MODEL` is optional for harder turns. The generated results currently identify the measured model as `{', '.join(sorted({str(c.get('model')) for c in DATA.get('cells', [])})) or 'none'}`; this is a mock evaluation artifact, so it is not evidence for a particular Gemma checkpoint.

## Why this is a fair small-model test

Each model receives the selected ISA definition in context and must produce assembly or tool arguments. It cannot alter the checker or execute arbitrary code. Success is determined by strict assembly/simulation and expected-state comparison. This isolates instruction learning, planning, and repair from memorization of a conventional ISA.

## Why open weights matter

Offline classrooms and labs can run the model without student code leaving the device. Open weights also make the model tag, prompt, telemetry, seeds, and simulator version inspectable and reproducible.

## What a closed hosted model would break

A hosted-only model would weaken the privacy guarantee, make offline demonstrations impossible, add an external service dependency to the trust boundary, and make latency/cost/model-version comparisons harder to reproduce.

## Measured evidence

The only authoritative measurements are generated in `eval/results.json`; see [eval/RESULTS.md](../eval/RESULTS.md). Do not copy numbers into this document by hand.
""")

write("docs/ARCHITECTURE.md", """# Architecture

1. A task or user-confirmed specification provides natural-language intent, initialization, and expected values.
2. Gemma receives the ISA card and emits only assembly, tool-call arguments, or explanations.
3. The agent validates tool arguments before calling `assemble`, `run`, `inspect`, or `submit`.
4. The assembler produces machine code or structured diagnostics.
5. The strict simulator executes in-process with a cycle cap and optional state-diff trace.
6. A server-owned checker compares declared registers, flags, memory, halt state, or translation observables.
7. Only the checker produces the pass/fail verdict.

```mermaid
flowchart TD
  U[Task / user-confirmed spec] --> P[Prompt + ISA card]
  P --> M[Gemma]
  M -->|untrusted output| V[Schema/tool validation]
  V --> AS[Assembler]
  AS --> SIM[Strict in-process simulator]
  SIM --> CH[Immutable checker]
  CH --> OUT[Verdict + compact feedback]
  SIM --> TR[Per-step trace diffs]
  TR --> EX[Trace explainer with verified citations]
```

The trust boundary is between model output and execution: model output is untrusted; only the simulator and checker decide behavior and correctness.
""")

write("docs/DEMO.md", """# Two-minute demo script

1. **Local privacy (20s).** Start the local model endpoint, open ForgeASM, and show the `LOCAL / model` badge and `Bytes off this device: 0`. Turn Wi-Fi off on camera. This is a live behavior check, not a claim copied from prose.
2. **Stack ISA repair (35s).** Select RISC-1, enter a plain-language arithmetic task, click Generate and verify, and show the first assembler/simulator failure followed by the repair in Copilot Logbook. End on the deterministic pass badge.
3. **Translation (25s).** Open Translate, choose a different ISA, run a source program, and show the per-vector differential table. Explain that only ISA-neutral observables are compared.
4. **Photo pipeline (20s).** If `/api/copilot/capabilities` reports image support, upload a pseudocode/flowchart photo, show the exact downscaled EXIF-stripped image, edit/confirm the structured spec, then run it. If support is false, show the honest disabled explanation.
5. **Results (20s).** Open `eval/RESULTS.md`, show the generated per-ISA/model/ablation tables, and explain that every number is read from `eval/results.json`; current unavailable-real-model limitations are shown rather than hidden.
""")
