# ForgeASM Evaluation Results

Generated from `eval/results.json`; completed cells: 108, skipped cells: 0.

## Per-ISA

| name | n | assemble_ok@1 | pass@1 | pass@repair | mean_repair_turns | tokens | latency_ms | tokens/sec | efficiency_ratio | bytes_off_device |
|---|---|---|---|---|---|---|---|---|---|---|
| cisc | 24 | 1 | 1 | 1 | 0 | 24 | 0.093 | 277777.2789 | 1.0 | 8581 |
| risc1 | 28 | 1 | 1 | 1 | 0 | 24 | 0.0935 | 299227.2212 | 1.0 | 5982.4286 |
| risc2 | 24 | 1 | 1 | 1 | 0 | 24 | 0.0941 | 289318.5804 | 1.0 | 6403 |
| risc3 | 32 | 1 | 0.875 | 0.875 | 0.375 | 33 | 0.1141 | 304994.3231 | 1.0 | 9975.8125 |

## Per-model

| name | n | assemble_ok@1 | pass@1 | pass@repair | mean_repair_turns | tokens | latency_ms | tokens/sec | efficiency_ratio | bytes_off_device |
|---|---|---|---|---|---|---|---|---|---|---|
| mock | 108 | 1 | 0.963 | 0.963 | 0.1111 | 26.6667 | 0.0996 | 293967.4181 | 1.0 | 7836.5741 |

## Ablations

| name | n | assemble_ok@1 | pass@1 | pass@repair | mean_repair_turns | tokens | latency_ms | tokens/sec | efficiency_ratio | bytes_off_device |
|---|---|---|---|---|---|---|---|---|---|---|
| card-no-examples | 27 | 1 | 0.963 | 0.963 | 0.1481 | 27.5556 | 0.1183 | 250133.5778 | 1.0 | 10255.8519 |
| full-card | 27 | 1 | 0.963 | 0.963 | 0.1481 | 27.5556 | 0.1187 | 251945.1791 | 1.0 | 10351.1481 |
| no-card | 27 | 1 | 0.963 | 0.963 | 0.1481 | 27.5556 | 0.072 | 396570.8376 | 1.0 | 1850.4444 |
| no-repair | 27 | 1 | 0.963 | 0.963 | 0 | 24 | 0.0895 | 277220.078 | 1.0 | 8888.8519 |

## Translation

| Pair | Model | Success rate | Mean instruction ratio |
| --- | --- | ---: | ---: |
| cisc->risc1 | reference | 1.0000 | 1.0000 |
| cisc->risc2 | reference | 1.0000 | 1.0000 |
| risc1->cisc | reference | 1.0000 | 1.0000 |
| risc1->risc2 | reference | 1.0000 | 1.0000 |
| risc2->risc1 | reference | 1.0000 | 1.0000 |
| risc2->risc3 | reference | 1.0000 | 1.0000 |
| risc3->cisc | reference | 1.0000 | 1.0000 |
| risc3->risc1 | reference | 1.0000 | 1.0000 |

## Failure taxonomy

```json
{
  "wrong_semantics": 4
}
```

## Findings

- The reference gate validated 25 task/ISA solutions before model scoring.
- The translation reference gate validated 8 ordered ISA pairs.
- 0 cells were skipped because their backend was unavailable; no unavailable backend is scored as zero.
- Completed cells used measured token, latency, throughput, cycle, and off-device-byte fields (108 observations).
- Ablation rows are generated from the same stored cell schema, so replay does not call a model.
- Honest limitation: without configured local/cloud models, this run cannot claim real-model pass rates.
