# Two-minute demo script

1. **Local privacy (20s).** Start the local model endpoint, open ForgeASM, and show the `LOCAL / model` badge and `Bytes off this device: 0`. Turn Wi-Fi off on camera. This is a live behavior check, not a claim copied from prose.
2. **Stack ISA repair (35s).** Select RISC-1, enter a plain-language arithmetic task, click Generate and verify, and show the first assembler/simulator failure followed by the repair in Copilot Logbook. End on the deterministic pass badge.
3. **Translation (25s).** Open Translate, choose a different ISA, run a source program, and show the per-vector differential table. Explain that only ISA-neutral observables are compared.
4. **Photo pipeline (20s).** If `/api/copilot/capabilities` reports image support, upload a pseudocode/flowchart photo, show the exact downscaled EXIF-stripped image, edit/confirm the structured spec, then run it. If support is false, show the honest disabled explanation.
5. **Results (20s).** Open `eval/RESULTS.md`, show the generated per-ISA/model/ablation tables, and explain that every number is read from `eval/results.json`; current unavailable-real-model limitations are shown rather than hidden.
