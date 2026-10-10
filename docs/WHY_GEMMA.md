# Why Gemma 4

## Variant policy

Model tags are never hard-coded. `GEMMA_FAST_MODEL` is used for ordinary turns and `GEMMA_HEAVY_MODEL` is optional for harder turns. The generated results currently identify the measured model as `mock`; this is a mock evaluation artifact, so it is not evidence for a particular Gemma checkpoint.

## Why this is a fair small-model test

Each model receives the selected ISA definition in context and must produce assembly or tool arguments. It cannot alter the checker or execute arbitrary code. Success is determined by strict assembly/simulation and expected-state comparison. This isolates instruction learning, planning, and repair from memorization of a conventional ISA.

## Why open weights matter

Offline classrooms and labs can run the model without student code leaving the device. Open weights also make the model tag, prompt, telemetry, seeds, and simulator version inspectable and reproducible.

## What a closed hosted model would break

A hosted-only model would weaken the privacy guarantee, make offline demonstrations impossible, add an external service dependency to the trust boundary, and make latency/cost/model-version comparisons harder to reproduce.

## Measured evidence

The only authoritative measurements are generated in `eval/results.json`; see [eval/RESULTS.md](../eval/RESULTS.md). Do not copy numbers into this document by hand.
